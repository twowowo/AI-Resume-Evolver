import os
import chromadb
from chromadb.config import Settings

COLLECTION_NAME = "resume_evolution_v1"
CHROMA_PERSIST_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "chroma_db")
)

_client = None


def get_vector_db_client() -> chromadb.ClientAPI:
    global _client
    if _client is not None:
        return _client

    chroma_host = os.getenv("CHROMA_HOST", "").strip()

    if chroma_host:
        host = chroma_host
        port = int(os.getenv("CHROMA_PORT", "8000"))
        print(f"[config] 连接远程 ChromaDB: http://{host}:{port}")
        _client = chromadb.HttpClient(
            host=host,
            port=port,
            settings=Settings(anonymized_telemetry=False),
        )
    else:
        os.makedirs(CHROMA_PERSIST_DIR, exist_ok=True)
        print(f"[config] 本地 ChromaDB 模式: {CHROMA_PERSIST_DIR}")
        _client = chromadb.PersistentClient(
            path=CHROMA_PERSIST_DIR,
            settings=Settings(anonymized_telemetry=False),
        )

    return _client


def get_collection_name() -> str:
    return os.getenv("CHROMA_COLLECTION", COLLECTION_NAME)
