import os
import chromadb
from chromadb.config import Settings

COLLECTION_NAME = "resume_evolution_v1"

# ── v4.1 持久化路径物理锁死：永不因进程重置或路径漂移导致空库 ──
_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
CHROMA_PERSIST_DIR = os.path.join(_PROJECT_ROOT, "chroma_db")

_client = None


def get_chroma_persist_dir() -> str:
    """返回锁死的 ChromaDB 持久化绝对路径"""
    return CHROMA_PERSIST_DIR


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
        print(f"[config] 本地 ChromaDB 持久化路径 (已锁死): {CHROMA_PERSIST_DIR}")
        _client = chromadb.PersistentClient(
            path=CHROMA_PERSIST_DIR,
            settings=Settings(anonymized_telemetry=False),
        )

    return _client


def get_collection_name() -> str:
    return os.getenv("CHROMA_COLLECTION", COLLECTION_NAME)


# ── v4.1 种子数据守卫：确保空库冷启动时自动灌入金牌案例 ──

def ensure_seed_data() -> int:
    """
    启动时调用：检查 collection 是否为空，空库则自动灌入种子数据。

    返回:
        int — 本次灌入的文档数（0 表示库非空，无需灌入）
    """
    client = get_vector_db_client()
    name = get_collection_name()

    # 使用 get_or_create 确保 collection 物理存在
    collection = client.get_or_create_collection(name=name)
    count = collection.count()

    if count > 0:
        print(f"[seed_guard] Collection '{name}' 已有 {count} 条文档，跳过种子灌入。")
        return 0

    print(f"[seed_guard] 检测到空库冷启动！开始自动灌入金牌种子案例...")

    from src.seed_data import SEED_TERMS

    if not SEED_TERMS:
        print("[seed_guard] 种子数据为空，跳过灌入。")
        return 0

    # 批量写入：每批 10 条，逐批 add 并打印进度
    batch_size = 10
    total = len(SEED_TERMS)
    ingested = 0

    for i in range(0, total, batch_size):
        batch = SEED_TERMS[i:i + batch_size]
        ids = [f"seed_{i + j:04d}" for j in range(len(batch))]
        metadatas = [{"source": "seed_data", "index": i + j} for j in range(len(batch))]
        try:
            collection.add(documents=batch, ids=ids, metadatas=metadatas)
            ingested += len(batch)
        except Exception as e:
            print(f"[seed_guard] 批次 [{i}:{i+batch_size}] 写入失败: {e}")

    # 验证
    final_count = collection.count()
    print(f"[seed_guard] 种子灌入完成！本次写入 {ingested} 条，库内总计 {final_count} 条文档。")

    # 触发 BM25 索引重建
    try:
        from src.utils.vector_store import rebuild_bm25
        rebuild_bm25()
        print("[seed_guard] BM25 索引已同步重建。")
    except Exception as e:
        print(f"[seed_guard] BM25 索引重建失败 (非致命): {e}")

    return ingested
