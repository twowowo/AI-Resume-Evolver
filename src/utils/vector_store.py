import os
import chromadb
from chromadb.config import Settings
from chromadb.utils import embedding_functions
from langchain_chroma import Chroma
from langchain_classic.retrievers.multi_query import MultiQueryRetriever

COLLECTION_NAME = "resume_evolution_v1"

_embedding_model = None
_vector_store = None
_enhanced_retriever = None


def _get_chroma_config():
    host = os.getenv("CHROMA_SERVER_HOST", "localhost")
    port = int(os.getenv("CHROMA_SERVER_PORT", "8001"))
    return host, port


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
        host, port = _get_chroma_config()
        print(f"[vector_store] 连接 ChromaDB Docker: {host}:{port}")

        http_client = chromadb.HttpClient(
            host=host,
            port=port,
            settings=Settings(anonymized_telemetry=False),
        )

        _vector_store = Chroma(
            client=http_client,
            collection_name=COLLECTION_NAME,
            embedding_function=_get_embedding_model(),
        )
        print(f"[vector_store] Collection '{COLLECTION_NAME}' 已就绪")
    return _vector_store


def _build_base_retriever():
    store = get_vector_store()
    return store.as_retriever(search_kwargs={"k": 10})


def _build_multi_query_retriever():
    from src.utils.llm import get_flash_client

    base_retriever = _build_base_retriever()
    llm = get_flash_client()

    mq_retriever = MultiQueryRetriever.from_llm(
        retriever=base_retriever,
        llm=llm,
        include_original=True,
    )
    print("[vector_store] MultiQueryRetriever 已装配 (扩写 3 个查询变体)")
    return mq_retriever


def get_retriever():
    global _enhanced_retriever
    if _enhanced_retriever is None:
        try:
            _enhanced_retriever = _build_multi_query_retriever()
            print("[vector_store] RAG 管线就绪: MultiQuery -> Top-10 粗筛 (k=10, 无 Rerank)")
        except Exception as e:
            print(f"[vector_store] MultiQuery 构建失败 ({e})，回退到基础检索器")
            _enhanced_retriever = _build_base_retriever()

    return _enhanced_retriever


def add_terms(terms: list[str]):
    if not terms:
        return
    store = get_vector_store()
    store.add_texts(terms)
    print(f"[vector_store] 已写入 {len(terms)} 条术语到 '{COLLECTION_NAME}'")
