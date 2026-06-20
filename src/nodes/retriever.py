"""
v6.1 15路并发锚点检索引擎 — 容器启动预热模式

升级:
  - RetrieverNode 类: __init__ 触发 Cross-Encoder 预热
  - 容错降级: 预热失败自动回退到纯 RRF 融合模式
  - 明确预热日志: 供 docker logs 状态追踪
  - 向后兼容: 模块级 retriever_node 单例 = RetrieverNode()
"""

import time
from src.utils.vector_store import hybrid_retrieve, cross_encoder_rerank, warmup_reranker
from src.utils.llm import get_flash_client
from src.state import AgentState

ANCHOR_EXTRACTION_PROMPT = """你是一位精通技术岗位分析的资深猎头。请从以下 JD 中提取 15 个【核心技术锚点】。

规则:
1. 每个锚点是一个具体的技术关键词或短语，如 "Spring Boot 微服务"、"Redis 缓存优化"、"LangGraph 状态机"
2. 锚点应覆盖: 编程语言/框架、数据库/中间件、架构设计、性能优化、工程方法论
3. 优先提取 JD 中反复出现或权重最高的技术词
4. 如果 JD 较短或技术词不足 15 个，用相关技术场景做合理泛化补足到 15 个
5. 输出格式: 每行一个锚点，纯文本，无编号无符号

【目标岗位 JD】:
{jd}

现在请输出 15 个核心技术锚点（每行一个）:"""


def _extract_jd_anchors(jd_text: str) -> list[str]:
    """从 JD 中提取 15 个核心技术锚点，用于多路并发检索"""
    if not jd_text or not jd_text.strip():
        return []

    prompt = ANCHOR_EXTRACTION_PROMPT.format(jd=jd_text[:4000])

    try:
        llm = get_flash_client()
        response = llm.invoke(prompt)
        text = response.content if hasattr(response, "content") else str(response)
        text = text.strip()
    except Exception as e:
        print(f"[retriever] 锚点提取失败: {e}")
        return [jd_text[:200]]

    anchors = [line.strip() for line in text.split("\n") if line.strip()]
    anchors = [a.lstrip("0123456789.、-•·) ") for a in anchors]
    anchors = [a for a in anchors if len(a) >= 4]

    if len(anchors) > 15:
        anchors = anchors[:15]

    print(f"[retriever] JD 锚点提取完成: {len(anchors)} 个锚点")
    for i, a in enumerate(anchors, 1):
        print(f"  {i:2d}. {a}")

    return anchors


def _dedup_by_prefix(docs: list, prefix_len: int = 50) -> list:
    """按 page_content 前 N 字符去重，保留先出现的"""
    seen: set[str] = set()
    unique: list = []
    for doc in docs:
        key = doc.page_content[:prefix_len].strip()
        if key and key not in seen:
            seen.add(key)
            unique.append(doc)
    return unique


class RetrieverNode:
    """v6.1 容器启动预热模式 — 15路并发锚点检索引擎

    预热策略:
      - __init__ 阶段强制加载 Cross-Encoder 模型
      - 预热成功 → 首次请求即刻享受完整重排序
      - 预热失败 → 自动降级为纯 RRF 融合，系统不崩

    用法:
      retriever_node = RetrieverNode()   # 触发预热
      result = retriever_node(state)     # LangGraph 节点调用
    """

    def __init__(self):
        self.reranker_available = False

        print("[System] ═══════════════════════════════════════")
        print("[System] 正在进行模型预热 (Container Warmup)...")
        print("[System] ═══════════════════════════════════════")
        print("[System] [1/1] Cross-Encoder 重排序模型 (BAAI/bge-reranker-large)")

        try:
            self.reranker_available = warmup_reranker()
        except Exception as exc:
            print(f"[System]   [FAIL] 预热异常: {type(exc).__name__}: {exc}")
            self.reranker_available = False

        if self.reranker_available:
            print("[System]   [OK] 预热完成 — 首次请求重排序延迟将降至 1-2s")
        else:
            print("[System]   [WARN] 预热失败 — 回退到纯 RRF 融合模式 (BM25 + Vector)")
            print("[System]   [WARN] 系统正常运行，重排序阶段将被跳过")

        print("[System] ═══════════════════════════════════════")
        print("[System] 模型预热流程结束 — RetrieverNode 就绪")
        print("[System] ═══════════════════════════════════════")

    def __call__(self, state: AgentState):
        """
        v6.1 15路并发锚点检索 + Cross-Encoder 重排序

        流水线:
          1. LLM 从 JD 提取 15 个技术锚点
          2. 每锚点独立 hybrid_retrieve (vector_k=15, bm25_k=15, fusion_k=8)
          3. 全局 hash 去重 (前50字符)
          4. Cross-Encoder 重排序 → top 10 (若预热成功)
          5. 格式化输出 + 遥测日志
        """
        t0 = time.time()
        print("--- [retriever] 15路并发锚点检索 (v6.1) ---")

        user_id = state.get("user_id") or ""
        resume_id = state.get("resume_id") or ""
        jd = state.get("jd") or ""
        resume = state.get("resume") or ""

        metadata_filter = None
        if user_id and resume_id:
            metadata_filter = {
                "$or": [
                    {"$and": [{"user_id": user_id}, {"resume_id": resume_id}]},
                    {"source": "seed_data"},
                ]
            }
            print(f"[retriever] 三层漏斗 Layer 2 已激活: user_id={user_id}, resume_id={resume_id} (含公共种子库通路)")

        # ── Step 1: 提取 15 个技术锚点 ──
        t_anchor_start = time.time()
        anchors = _extract_jd_anchors(jd)
        t_anchor = time.time() - t_anchor_start

        if not anchors:
            anchors = [f"{jd[:200]} {resume[:200]}"]

        jd_keywords = "\n".join(f"  {i}. {a}" for i, a in enumerate(anchors, 1))

        # ── Step 2: 15路独立检索 ──
        t_retrieve_start = time.time()
        all_docs: list = []
        for anchor in anchors:
            docs = hybrid_retrieve(
                anchor,
                vector_k=15,
                bm25_k=15,
                fusion_k=8,
                metadata_filter=metadata_filter,
            )
            all_docs.extend(docs)
        t_retrieve = time.time() - t_retrieve_start

        total_before_dedup = len(all_docs)

        # ── Step 3: 全局 hash 去重 ──
        all_docs = _dedup_by_prefix(all_docs, prefix_len=50)
        after_dedup = len(all_docs)
        print(f"[retriever] 去重: {total_before_dedup} → {after_dedup}")

        # ── Step 4: Cross-Encoder 重排序 (带降级) ──
        t_rerank_start = time.time()
        rerank_applied = False
        if self.reranker_available and len(all_docs) > 10:
            query_text = f"{jd[:512]} {resume[:256]}"
            all_docs = cross_encoder_rerank(query_text, all_docs, top_k=10)
            rerank_applied = True
        elif len(all_docs) > 10:
            # 降级: 取前 10 篇 RRF 融合结果
            all_docs = all_docs[:10]
            print("[retriever] Cross-Encoder 不可用，使用 RRF Top-10 降级输出")
        t_rerank = time.time() - t_rerank_start

        final_count = len(all_docs)

        # ── Step 5: 格式化输出 ──
        retrieved_docs: list[str] = []
        for doc in all_docs:
            tag = doc.metadata.get("tag", "通用") if doc.metadata else "通用"
            retrieved_docs.append(f"[{tag}] 案例内容：\n{doc.page_content}")

        context = "\n\n".join(retrieved_docs) if retrieved_docs else "(未命中沙箱内案例，以通用知识库兜底)"

        total_time = time.time() - t0

        # ── 遥测日志 ──
        if final_count >= 8:
            intensity = "HIGH (90%)"
            intensity_pct = 90
        elif final_count >= 5:
            intensity = "MEDIUM (60%)"
            intensity_pct = 60
        elif final_count >= 1:
            intensity = "LOW (30%)"
            intensity_pct = 30
        else:
            intensity = "VACUUM (0%)"
            intensity_pct = 0

        rerank_tag = "Cross-Encoder" if rerank_applied else "RRF-fallback"

        metrics = (
            f"[RAG Metrics v6.1] "
            f"anchors={len(anchors)} | "
            f"anchor_extract={t_anchor:.2f}s | "
            f"retrieve={t_retrieve:.2f}s | "
            f"rerank={t_rerank:.2f}s ({rerank_tag}) | "
            f"total={total_time:.2f}s | "
            f"raw={total_before_dedup} | "
            f"dedup={after_dedup} | "
            f"final={final_count} | "
            f"intensity={intensity}"
        )
        print(f"[retriever] {metrics}")

        return {
            "rag_context": context,
            "jd_keywords": jd_keywords,
            "retriever_metrics": metrics,
            "internal_monologue": (
                f"[沙箱: {user_id}/{resume_id}] "
                f"v6.1 15路锚点检索完成: {len(anchors)} 锚点 → "
                f"{total_before_dedup} raw → {after_dedup} dedup → "
                f"{final_count} {rerank_tag}. "
                f"知识干预强度: {intensity_pct}%, 总耗时 {total_time:.1f}s"
            ),
        }


# ── 模块级单例: import 时触发预热 ──
retriever_node = RetrieverNode()
