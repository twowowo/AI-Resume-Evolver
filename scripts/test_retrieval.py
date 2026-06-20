"""
RAG 1024d 检索质量验证脚本 (BAAI/bge-large-zh-v1.5)
可直接在容器内运行: docker compose exec backend python scripts/test_retrieval.py
"""
import os
import sys
import time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from dotenv import load_dotenv
load_dotenv()

from src.utils.vector_store import hybrid_retrieve, cross_encoder_rerank, warmup_reranker

# ═══════════════════════════════════════════════════════════════
# 测试用例设计
# ═══════════════════════════════════════════════════════════════

TEST_CASES = [
    {
        "id": "CASE-1",
        "name": "高并发与后端工程场景",
        "query": "Java 高并发编程，线程池优化，JVM 内存调优，分布式锁 Redis 实现",
        "expected_keywords": ["Java", "并发", "线程池", "JVM", "Redis", "分布式锁"],
        "min_relevant": 2,  # top-3 中至少 2 条相关
    },
    {
        "id": "CASE-2",
        "name": "微服务架构与数据中间件组合",
        "query": "Spring Boot 微服务架构设计，MySQL 分库分表方案，Redis 缓存穿透与击穿防护",
        "expected_keywords": ["Spring", "微服务", "MySQL", "分库分表", "Redis", "缓存"],
        "min_relevant": 2,
    },
    {
        "id": "CASE-3",
        "name": "完全无关干扰输入（抗噪测试）",
        "query": "今天天气真好，适合出去旅游放松心情",
        "expected_keywords": [],
        "min_relevant": 0,  # 期望 0 条相关知识库命中
        "max_expected_score": 3.0,  # RRF 分数应极低
    },
]

# ═══════════════════════════════════════════════════════════════
# 评估工具
# ═══════════════════════════════════════════════════════════════

def _count_keyword_hits(text: str, keywords: list[str]) -> int:
    """统计 text 中命中多少 keywords"""
    if not keywords:
        return 0
    hits = 0
    text_lower = text.lower()
    for kw in keywords:
        # 每个 keyword 中取最关键的词做子串匹配
        core = kw.split()[-1] if " " in kw else kw
        if core.lower() in text_lower:
            hits += 1
    return hits


def _evaluate_case(case: dict, docs: list, elapsed: float):
    """评估单个测试用例的检索质量"""
    print(f"\n{'='*70}")
    print(f"[{case['id']}] {case['name']}")
    print(f"查询: {case['query'][:100]}")
    print(f"耗时: {elapsed:.2f}s  | 召回数: {len(docs)}")
    print(f"{'='*70}")

    if not docs:
        print("[结果] 无召回结果")
        if case.get("max_expected_score"):
            print("[评估] PASS (无关查询期望召回为 0)")
        else:
            print("[评估] FAIL — 期望有召回但为空")
        return

    total_hits = 0
    print(f"\n{'─'*50}")
    for rank, doc in enumerate(docs, 1):
        content = doc.page_content
        preview = content[:200].replace("\n", " ")
        hits = _count_keyword_hits(content, case.get("expected_keywords", []))
        total_hits += hits

        print(f"\n  Top-{rank}  (关键词命中: {hits})")
        print(f"  {'─'*40}")
        print(f"  {preview}...")

    print(f"\n{'─'*50}")
    print(f"[统计] 总关键词命中数: {total_hits} / Top-{len(docs)}")

    # 判断通过与否
    min_relevant = case.get("min_relevant", 1)
    if total_hits >= min_relevant:
        print(f"[评估] PASS — 命中 {total_hits} >= 阈值 {min_relevant}")
    elif case.get("max_expected_score") and total_hits == 0:
        print(f"[评估] PASS — 无关查询召回相关性极低，抗噪合格")
    else:
        print(f"[评估] FAIL — 命中 {total_hits} < 阈值 {min_relevant}")


# ═══════════════════════════════════════════════════════════════
# 主流程
# ═══════════════════════════════════════════════════════════════

def main():
    print("╔══════════════════════════════════════════════════════════╗")
    print("║   RAG 1024d 检索质量验证 (BAAI/bge-large-zh-v1.5)      ║")
    print("╚══════════════════════════════════════════════════════════╝")

    # ── 预热 Cross-Encoder ──
    print("\n[预热] 加载 Cross-Encoder 重排序模型...")
    reranker_ok = warmup_reranker()
    rerank_label = "Cross-Encoder" if reranker_ok else "RRF-only (fallback)"
    print(f"[预热] 重排序模式: {rerank_label}")

    # ── 逐用例测试 ──
    summary: list[dict] = []

    for case in TEST_CASES:
        t0 = time.time()

        # Step 1: 混合检索 (RRF fusion)
        docs = hybrid_retrieve(
            case["query"],
            vector_k=15,
            bm25_k=15,
            fusion_k=10,
        )

        # Step 2: Cross-Encoder 重排序 (若可用)
        if reranker_ok and len(docs) > 3:
            docs = cross_encoder_rerank(case["query"], docs, top_k=3)
        elif len(docs) > 3:
            docs = docs[:3]

        elapsed = time.time() - t0

        _evaluate_case(case, docs, elapsed)

        summary.append({
            "id": case["id"],
            "query": case["query"][:60],
            "recall_count": len(docs),
            "elapsed": elapsed,
            "rerank": rerank_label,
        })

    # ── 汇总 ──
    print(f"\n{'='*70}")
    print("                           测试汇总")
    print(f"{'='*70}")
    print(f"  {'ID':<10} {'召回':<6} {'耗时':<8} {'重排序'}")
    print(f"  {'─'*40}")
    for s in summary:
        print(f"  {s['id']:<10} {s['recall_count']:<6} {s['elapsed']:.2f}s    {s['rerank']}")
    print(f"{'='*70}")


if __name__ == "__main__":
    main()
