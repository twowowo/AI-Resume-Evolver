import os
import re
import chromadb
from chromadb.config import Settings
from chromadb.utils import embedding_functions
from langchain_chroma import Chroma
from langchain_classic.retrievers.multi_query import MultiQueryRetriever
from langchain_core.documents import Document
from rank_bm25 import BM25Okapi

from src.config import CHROMA_PERSIST_DIR, COLLECTION_NAME

_embedding_model = None
_vector_store = None
_bm25_index = None
_bm25_corpus = None
_enhanced_retriever = None


def _get_embedding_model():
    global _embedding_model
    if _embedding_model is None:
        _chroma_ef = embedding_functions.DefaultEmbeddingFunction()

        class _ChromaEmbeddingWrapper:
            def embed_documents(self, texts):
                return _chroma_ef(texts)

            def embed_query(self, text):
                return _chroma_ef([text])[0]

        _embedding_model = _ChromaEmbeddingWrapper()
        print("[vector_store] ONNX Embedding (all-MiniLM-L6-v2, 384d) 已就绪")
    return _embedding_model


def get_vector_store() -> Chroma:
    global _vector_store
    if _vector_store is None:
        os.makedirs(CHROMA_PERSIST_DIR, exist_ok=True)
        print(f"[vector_store] 本地 ChromaDB 持久化路径 (来自 config 锁): {CHROMA_PERSIST_DIR}")

        client = chromadb.PersistentClient(
            path=CHROMA_PERSIST_DIR,
            settings=Settings(anonymized_telemetry=False),
        )

        # v4.1: 始终使用 get_or_create 确保 collection 物理存在
        client.get_or_create_collection(name=COLLECTION_NAME)

        _vector_store = Chroma(
            client=client,
            collection_name=COLLECTION_NAME,
            embedding_function=_get_embedding_model(),
        )
        print(f"[vector_store] Collection '{COLLECTION_NAME}' 已就绪")
    return _vector_store


_CJK_RE = re.compile(r"[\u4e00-\u9fff\uff00-\uffef]+")


def _tokenize(text: str) -> list[str]:
    tokens: list[str] = []
    current_word = ""
    for ch in text.lower():
        if _CJK_RE.match(ch):
            if current_word:
                tokens.append(current_word)
                current_word = ""
            tokens.append(ch)
        elif ch.isalnum():
            current_word += ch
        else:
            if current_word:
                tokens.append(current_word)
                current_word = ""
    if current_word:
        tokens.append(current_word)
    return [t for t in tokens if len(t) >= 2]


def _build_bm25():
    global _bm25_index, _bm25_corpus
    store = get_vector_store()
    try:
        data = store._collection.get(include=["documents"])
    except Exception:
        _bm25_index = None
        _bm25_corpus = []
        return

    docs = data.get("documents", [])
    if not docs:
        _bm25_index = None
        _bm25_corpus = []
        return

    _bm25_corpus = [_tokenize(d) for d in docs]
    _bm25_index = BM25Okapi(_bm25_corpus)
    print(f"[vector_store] BM25 索引已构建 ({len(docs)} 篇文档)")


def _get_bm25():
    global _bm25_index
    if _bm25_index is None:
        _build_bm25()
    return _bm25_index


def _get_bm25_corpus():
    global _bm25_corpus
    if _bm25_corpus is None:
        _build_bm25()
    return _bm25_corpus or []


def hybrid_retrieve(query: str, vector_k: int = 10, bm25_k: int = 10, fusion_k: int = 5) -> list[Document]:
    store = get_vector_store()

    vector_results = store.similarity_search_with_score(query, k=vector_k)
    vector_ranked: dict[str, float] = {}
    for rank, (doc, score) in enumerate(vector_results):
        vector_ranked[doc.page_content] = rank + 1

    bm25 = _get_bm25()
    bm25_corpus = _get_bm25_corpus()
    bm25_ranked: dict[str, float] = {}

    if bm25 is not None and bm25_corpus:
        query_tokens = _tokenize(query)
        bm25_scores = bm25.get_scores(query_tokens)
        indexed = list(enumerate(bm25_scores))
        indexed.sort(key=lambda x: x[1], reverse=True)
        all_docs = store._collection.get(include=["documents"])
        all_texts = all_docs.get("documents", [])
        for rank, (idx, score) in enumerate(indexed[:bm25_k]):
            if idx < len(all_texts):
                bm25_ranked[all_texts[idx]] = rank + 1

    rrf_scores: dict[str, float] = {}
    k = 60

    for content, rank in vector_ranked.items():
        rrf_scores[content] = rrf_scores.get(content, 0) + 1.0 / (k + rank)

    for content, rank in bm25_ranked.items():
        rrf_scores[content] = rrf_scores.get(content, 0) + 1.0 / (k + rank)

    sorted_items = sorted(rrf_scores.items(), key=lambda x: x[1], reverse=True)

    fused_docs: list[Document] = []
    for content, score in sorted_items[:fusion_k]:
        fused_docs.append(Document(page_content=content))

    return fused_docs


def get_retriever():
    global _enhanced_retriever
    if _enhanced_retriever is None:
        from src.utils.llm import get_flash_client

        store = get_vector_store()
        base_retriever = store.as_retriever(search_kwargs={"k": 10})
        llm = get_flash_client()

        try:
            _enhanced_retriever = MultiQueryRetriever.from_llm(
                retriever=base_retriever,
                llm=llm,
                include_original=True,
            )
            print("[vector_store] MultiQueryRetriever 已装配 (扩写 3 个查询变体)")
        except Exception as e:
            print(f"[vector_store] MultiQuery 构建失败 ({e})，回退到基础检索器")
            _enhanced_retriever = base_retriever

    return _enhanced_retriever


def add_terms(terms: list[str], metadatas: list[dict] | None = None):
    if not terms:
        return
    store = get_vector_store()
    if metadatas and len(metadatas) == len(terms):
        store.add_texts(terms, metadatas=metadatas)
    else:
        store.add_texts(terms)
    print(f"[vector_store] 已写入 {len(terms)} 条术语到 '{COLLECTION_NAME}'")
    global _bm25_index, _bm25_corpus
    _bm25_index = None
    _bm25_corpus = None
    print("[vector_store] BM25 索引已标记为待重建")


def rebuild_bm25():
    global _bm25_index, _bm25_corpus
    _bm25_index = None
    _bm25_corpus = None
    _build_bm25()
