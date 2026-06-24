import os
import re
import chromadb
from chromadb.config import Settings
from langchain_chroma import Chroma
from langchain_classic.retrievers.multi_query import MultiQueryRetriever
from langchain_core.documents import Document
from rank_bm25 import BM25Okapi

from src.config import CHROMA_PERSIST_DIR, COLLECTION_NAME, get_vector_db_client

_embedding_model = None
_vector_store = None
_bm25_index = None
_bm25_corpus = None
_enhanced_retriever = None

_HF_CACHE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "models", "huggingface")


def _get_embedding_model():
    global _embedding_model
    if _embedding_model is None:
        os.makedirs(_HF_CACHE_DIR, exist_ok=True)
        os.environ.setdefault("HF_HOME", _HF_CACHE_DIR)
        os.environ.setdefault("HF_HUB_CACHE", _HF_CACHE_DIR)

        from sentence_transformers import SentenceTransformer

        _BGE_QUERY_INSTRUCTION = "为这个句子生成表示以用于检索相关文章："

        class _BGEZhEmbeddingWrapper:
            def __init__(self):
                self._model = SentenceTransformer(
                    "BAAI/bge-large-zh-v1.5",
                    cache_folder=_HF_CACHE_DIR,
                )

            def embed_documents(self, texts):
                return self._model.encode(texts, normalize_embeddings=True).tolist()

            def embed_query(self, text):
                return self._model.encode(
                    _BGE_QUERY_INSTRUCTION + text, normalize_embeddings=True
                ).tolist()

        _embedding_model = _BGEZhEmbeddingWrapper()
        print("[vector_store] BAAI/bge-large-zh-v1.5 (1024d) 已就绪")
    return _embedding_model


def get_vector_store() -> Chroma:
    global _vector_store
    if _vector_store is None:
        client = get_vector_db_client()
        chroma_host = os.getenv("CHROMA_HOST", "")
        if chroma_host:
            print(f"[vector_store] 远程 ChromaDB: http://{chroma_host}:{os.getenv('CHROMA_PORT', '8000')}")
        else:
            print(f"[vector_store] 本地 ChromaDB 持久化路径: {CHROMA_PERSIST_DIR}")

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


def _build_scoped_bm25(metadata_filter: dict):
    """v5.6 为带元数据过滤的查询构建隔离 BM25 索引（不污染全局缓存）。

    返回 (bm25_model, original_texts) 元组。
    original_texts 保持与 BM25 内部索引顺序一致，供 RRF 融合时按位查找原始文档。
    """
    store = get_vector_store()
    try:
        data = store._collection.get(where=metadata_filter, include=["documents"])
    except Exception:
        return None, []
    docs = data.get("documents", [])
    if not docs:
        return None, []
    corpus = [_tokenize(d) for d in docs]
    return BM25Okapi(corpus), docs  # docs 保持原始文本用于 RRF 键匹配


def _bm25_fallback(query: str, bm25_k: int = 10, metadata_filter: dict | None = None) -> list[Document]:
    """v5.9 ChromaDB 不可用时 BM25-only 降级检索，系统不崩"""
    try:
        if metadata_filter:
            bm25, bm25_original_texts = _build_scoped_bm25(metadata_filter)
            bm25_corpus_ref = None
        else:
            bm25 = _get_bm25()
            bm25_corpus_ref = _get_bm25_corpus()
            bm25_original_texts = []
    except Exception:
        return []

    if bm25 is None:
        return []

    query_tokens = _tokenize(query)
    bm25_scores = bm25.get_scores(query_tokens)
    indexed = list(enumerate(bm25_scores))
    indexed.sort(key=lambda x: x[1], reverse=True)

    docs: list[Document] = []
    if metadata_filter:
        for rank, (idx, score) in enumerate(indexed[:bm25_k]):
            if idx < len(bm25_original_texts):
                docs.append(Document(page_content=bm25_original_texts[idx]))
    elif bm25_corpus_ref:
        for rank, (idx, score) in enumerate(indexed[:bm25_k]):
            if idx < len(bm25_corpus_ref):
                docs.append(Document(page_content=bm25_corpus_ref[idx]))

    print(f"[vector_store] BM25-only fallback 完成: {len(docs)} 篇文档")
    return docs


def hybrid_retrieve(query: str, vector_k: int = 10, bm25_k: int = 10, fusion_k: int = 5, metadata_filter: dict | None = None) -> list[Document]:
    """v5.6 混合检索：向量搜索 + BM25 双路均应用 metadata where 硬过滤。

    当 metadata_filter 为 None（共享种子数据/通用知识库检索）时使用全局缓存 BM25。
    当 metadata_filter 非空（per-user 隔离检索）时，BM25 在过滤后的文档子集上临时构建，
    确保隐私碎片不会通过 BM25 通路泄漏到其他租户的 RRF 融合结果中。
    """
    # ── v5.9 异常沙箱：ChromaDB 网络抖动时优雅降级为 BM25-only ──
    try:
        store = get_vector_store()
    except Exception as e:
        print(f"[vector_store] ChromaDB 不可达: {e}，降级为 BM25-only")
        return _bm25_fallback(query, bm25_k, metadata_filter)

    search_kwargs: dict = {"k": vector_k}
    if metadata_filter:
        search_kwargs["filter"] = metadata_filter

    try:
        vector_results = store.similarity_search_with_score(query, **search_kwargs)
    except Exception as e:
        print(f"[vector_store] 向量检索异常: {e}，降级为 BM25-only")
        return _bm25_fallback(query, bm25_k, metadata_filter)
    vector_ranked: dict[str, float] = {}
    for rank, (doc, score) in enumerate(vector_results):
        vector_ranked[doc.page_content] = rank + 1

    # ── v5.6: BM25 隔离 ──
    if metadata_filter:
        bm25, bm25_original_texts = _build_scoped_bm25(metadata_filter)
        bm25_corpus = None  # scoped 模式无需全局缓存
    else:
        bm25 = _get_bm25()
        bm25_corpus = _get_bm25_corpus()
        bm25_original_texts = []

    bm25_ranked: dict[str, float] = {}

    if bm25 is not None:
        query_tokens = _tokenize(query)
        bm25_scores = bm25.get_scores(query_tokens)
        indexed = list(enumerate(bm25_scores))
        indexed.sort(key=lambda x: x[1], reverse=True)

        if metadata_filter:
            # 使用过滤后文档的原始文本
            for rank, (idx, score) in enumerate(indexed[:bm25_k]):
                if idx < len(bm25_original_texts):
                    bm25_ranked[bm25_original_texts[idx]] = rank + 1
        else:
            # 全局缓存路径：从 ChromaDB 按位取回原始文本
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


def batch_hybrid_retrieve(
    queries: list[str],
    vector_k: int = 15,
    bm25_k: int = 15,
    fusion_k: int = 8,
    metadata_filter: dict | None = None,
) -> list[list[Document]]:
    """v6.2 批量混合检索：一次性编码所有查询，再逐条 RRF 融合

    SentenceTransformer 在 CPU 上批处理远快于 N 次单条编码。
    15 条锚点从 ~285s (15×19s) 降至 ~25s (1×batch_encode + 15×ChromaDB)。
    """
    if not queries:
        return []

    model = _get_embedding_model()
    store = get_vector_store()
    collection = store._collection

    # ── Batch encode all queries ──
    _BGE_INSTRUCTION = "为这个句子生成表示以用于检索相关文章："
    prefixed = [_BGE_INSTRUCTION + q for q in queries]
    print(f"[batch_retrieve] 批量编码 {len(queries)} 条查询...")
    all_embeddings = model._model.encode(prefixed, normalize_embeddings=True)

    # ── BM25 setup ──
    if metadata_filter:
        bm25, bm25_texts = _build_scoped_bm25(metadata_filter)
    else:
        bm25 = _get_bm25()
        bm25_texts = []

    k_rrf = 60
    all_results: list[list[Document]] = []

    for qi, query in enumerate(queries):
        embedding = all_embeddings[qi].tolist()

        # Vector search
        vec_kwargs: dict = {"n_results": vector_k}
        if metadata_filter:
            vec_kwargs["where"] = metadata_filter

        try:
            vec_result = collection.query(query_embeddings=[embedding], **vec_kwargs)
        except Exception as exc:
            print(f"[batch_retrieve] 锚点 [{query[:50]}] 向量检索异常: {exc}")
            vec_result = None

        vector_ranked: dict[str, float] = {}
        if vec_result and vec_result.get("ids") and vec_result["ids"][0]:
            for rank, doc_id in enumerate(vec_result["ids"][0]):
                doc_text = vec_result["documents"][0][rank] if vec_result.get("documents") else ""
                if doc_text:
                    vector_ranked[doc_text] = rank + 1

        # BM25
        bm25_ranked: dict[str, float] = {}
        if bm25 is not None:
            query_tokens = _tokenize(query)
            bm25_scores = bm25.get_scores(query_tokens)
            indexed = list(enumerate(bm25_scores))
            indexed.sort(key=lambda x: x[1], reverse=True)

            if metadata_filter:
                for rank, (idx, _score) in enumerate(indexed[:bm25_k]):
                    if idx < len(bm25_texts):
                        bm25_ranked[bm25_texts[idx]] = rank + 1
            else:
                all_texts = collection.get(include=["documents"]).get("documents", [])
                for rank, (idx, _score) in enumerate(indexed[:bm25_k]):
                    if idx < len(all_texts):
                        bm25_ranked[all_texts[idx]] = rank + 1

        # RRF fusion
        rrf_scores: dict[str, float] = {}
        for content, rank in vector_ranked.items():
            rrf_scores[content] = rrf_scores.get(content, 0) + 1.0 / (k_rrf + rank)
        for content, rank in bm25_ranked.items():
            rrf_scores[content] = rrf_scores.get(content, 0) + 1.0 / (k_rrf + rank)

        sorted_items = sorted(rrf_scores.items(), key=lambda x: x[1], reverse=True)
        fused = [Document(page_content=content) for content, _ in sorted_items[:fusion_k]]
        all_results.append(fused)

    return all_results


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


def reset_vector_store():
    """删除并重建 ChromaDB Collection — Embedding 模型升级时维度对齐

    当切换 Embedding 模型导致向量维度变化时（如 384d → 1024d），
    旧 collection 中的向量记录与新模型维度不匹配，ChromaDB 会拒绝写入。
    此函数清除旧 collection 并创建新的空 collection。
    """
    client = get_vector_db_client()
    try:
        client.delete_collection(name=COLLECTION_NAME)
        print(f"[vector_store] 已删除旧 Collection '{COLLECTION_NAME}' (维度变更: 384d → 1024d)")
    except Exception:
        print(f"[vector_store] Collection '{COLLECTION_NAME}' 不存在，跳过删除")

    client.get_or_create_collection(name=COLLECTION_NAME)
    print(f"[vector_store] 已创建新 Collection '{COLLECTION_NAME}' (BAAI/bge-large-zh-v1.5, 1024d)")


# ═══════════════════════════════════════════════════════════════
# v6.0 Cross-Encoder 重排序 — BAAI/bge-reranker-large
# ═══════════════════════════════════════════════════════════════

_reranker_model = None
_RERANKER_MODEL_NAME = os.getenv("RERANKER_MODEL", "BAAI/bge-reranker-large")


def _get_reranker():
    """懒加载 BAAI/bge-reranker-large Cross-Encoder，全进程单例

    模型缓存路径: <项目根>/models/huggingface/
    设置 HF_HOME 环境变量确保 sentence_transformers / huggingface_hub
    将模型下载到项目本地目录而非系统默认 ~/.cache/huggingface。
    首次运行自动下载，后续复用缓存。
    """
    global _reranker_model
    if _reranker_model is None:
        os.makedirs(_HF_CACHE_DIR, exist_ok=True)
        os.environ.setdefault("HF_HOME", _HF_CACHE_DIR)
        os.environ.setdefault("HF_HUB_CACHE", _HF_CACHE_DIR)

        from sentence_transformers import CrossEncoder

        print(f"[vector_store] 加载 Cross-Encoder: {_RERANKER_MODEL_NAME}")
        print(f"[vector_store] HF_HOME={os.environ['HF_HOME']}")
        _reranker_model = CrossEncoder(
            _RERANKER_MODEL_NAME,
            max_length=512,
        )
        print(f"[vector_store] Cross-Encoder 已就绪")
    return _reranker_model


def cross_encoder_rerank(
    query: str,
    documents: list[Document],
    top_k: int = 10,
) -> list[Document]:
    """Cross-Encoder 成对打分重排序 — BAAI/bge-reranker-large

    对每个 (query, doc.page_content) 做 Cross-Attention 推理，
    按相关性分数降序排列，取 top_k。

    防御:
      - 文档数不足 top_k 时直接返回原始顺序
      - 空列表直接返回 []
      - 单文档跳过推理直接返回
    """
    if not documents:
        return []
    if len(documents) <= top_k:
        return documents

    reranker = _get_reranker()

    # 截断过长文本，单篇最多 400 字符提速
    doc_texts = [doc.page_content[:400] for doc in documents]

    # 构建 (query, document) 对
    pairs = [(query[:512], text) for text in doc_texts]

    scores = reranker.predict(pairs, show_progress_bar=False)

    # 按分数降序排列
    scored = list(zip(documents, scores))
    scored.sort(key=lambda x: x[1], reverse=True)

    return [doc for doc, _ in scored[:top_k]]


def warmup_reranker() -> bool:
    """容器启动预热: 强制加载 Cross-Encoder 模型到内存

    供 RetrieverNode.__init__ 或 FastAPI lifespan 调用，
    将模型首次加载延迟从"首个请求"转移到"启动阶段"。

    Returns:
        True  预热成功，后续 cross_encoder_rerank() 调用即时可用
        False 预热失败，系统应自动回退到纯 RRF 融合模式
    """
    try:
        _get_reranker()
        return True
    except Exception as e:
        print(f"[vector_store] Cross-Encoder 预热失败: {type(e).__name__}: {e}")
        return False
