import os
import sys
import time
from dotenv import load_dotenv

env_path = os.path.join(os.path.dirname(__file__), ".env")
load_dotenv(dotenv_path=env_path)

sys.path.insert(0, os.path.abspath("."))

from src.state import GraphState
from src.nodes.analyzer import jd_analyzer_node
from src.nodes.refiner import resume_refiner_node
from src.utils.loader import load_docx, load_txt

LOG_FILE = os.path.join(os.path.dirname(__file__), "debug_result.txt")


def log(msg):
    print(msg)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(msg + "\n")
        f.flush()


def create_test_jd():
    return """【字节跳动】高级商业化 AI 基础设施架构师

部门：商业化 AI 中台 - 广告召回与排序基础设施组
薪资范围：60k-90k · 15薪 · 期权可谈
工作地点：北京 / 上海

═══════════════════════════════════════
【岗位背景】
═══════════════════════════════════════
字节跳动商业化团队负责抖音、头条、穿山甲等全线产品的广告变现，日均处理千亿级广告请求。
我们正在构建下一代 AI 驱动的广告基础设施，将大模型（LLM）深度融入广告召回、精排、创意生成
和竞价策略的全链路。作为 AI 基础设施架构师，你将：
  - 设计支撑百万 QPS 的 RAG 增强广告检索系统
  - 构建结合向量检索 + 全文检索的混合召回引擎，深度融合大模型的语义理解能力与广告业务特征
  - 搞定极端流量洪峰（春晚/618/双十一等）下的缓存架构与并发控制

═══════════════════════════════════════
【硬性技术要求】
═══════════════════════════════════════
1. 精通 Python 异步编程（asyncio/协程），对 FastAPI/Starlette 底层事件循环有深入理解，
   能诊断和优化 asyncio 事件循环阻塞问题，熟悉 uvicorn 多 worker + Gunicorn 部署模型

2. 向量数据库与 RAG 系统实战：
   - 在百万级以上文档规模下做过向量检索（ChromaDB / Milvus / Pinecone / Weaviate）
   - 熟悉混合检索策略：Dense Retrieval（Embedding + ANN）+ Sparse Retrieval（BM25/SPLADE）
     + RRF（倒数排名融合）/ 学习型融合权重
   - 理解 Query Rewriting（多查询扩写）、HyDE（假设文档嵌入）、Re-ranking 等 RAG 进阶技术
   - 能诊断「答非所问」问题的根因 —— Embedding 漂移？chunk 切分不合理？检索粒度不匹配？

3. 高并发与缓存架构：
   - 深入理解缓存穿透 / 击穿 / 雪崩的根因，并能在业务场景中选择合适策略：
     布隆过滤器、互斥锁、逻辑过期、多级缓存（L1 Local Cache → L2 Redis → L3 DB）
   - 熟悉 Redis Cluster / Codis 架构，能设计支持千万 QPS 的分布式缓存层
   - 有实际处理过「缓存集中过期导致数据库被打爆」的经验，能清晰讲出你的止损措施和长期解法

4. 分布式系统与并发控制：
   - 深入理解 MySQL InnoDB 行锁 / 间隙锁 / 死锁检测机制，能通过 SHOW ENGINE INNODB STATUS
     和慢查询日志分析死锁根因，制定「更新顺序约定」等预防策略
   - 在电商/广告等高并发场景下做过分布式锁设计（Redis RedLock / ZooKeeper / etcd），
     理解锁粒度、锁超时、可重入性、公平性之间的权衡
   - 能区分乐观锁（版本号/CAS）和悲观锁（SELECT FOR UPDATE）的适用场景，
     不会「一把大锁框住整个流程」

5. 数据库性能优化：
   - 能独立完成慢查询定位（EXPLAIN / pt-query-digest）、索引设计（联合索引/覆盖索引/
     索引下推）、SQL 改写、读写分离、分库分表方案设计
   - 理解 MySQL 的 Buffer Pool、Change Buffer、Redo Log 等存储引擎内部机制

6. 工程能力：
   - Docker + Kubernetes 生产级部署经验，能写 Dockerfile 多阶段构建和 K8s HPA 自动扩缩容策略
   - 熟悉至少一种消息队列（Kafka / RocketMQ / Pulsar），用于异步链路削峰填谷
   - 有 Prometheus + Grafana 监控告警体系搭建经验

═══════════════════════════════════════
【加分项】
═══════════════════════════════════════
- 有大模型推理部署经验（vLLM / TensorRT-LLM / SGLang）
- 了解广告系统术语：CTR 预估、eCPM、OCPX、DSP/SSP/ADX
- 开源贡献（GitHub 500+ stars）或技术博客作者
- 有过一线大厂（BAT/TMD）工作经验，适应字节跳动「追求极致」的技术文化
- 熟悉字节跳动内部技术栈：ByteMQ、Ablab、TCE 等

═══════════════════════════════════════
【面试中我们重点考察】
═══════════════════════════════════════
- 你能不能把一个「模糊的 RAG 效果不好」问题拆解成可量化的技术指标？
- 你说你解决过缓存雪崩，那你的方案在 10 倍流量下还成立吗？有没有压测数据？
- 你的分布式锁方案，在 Redis 主从切换的瞬间会不会出现两个 Worker 同时持锁？
- 你对「接口慢」的定义是什么？P50/P99/P999 分别是多少？你优化的是哪个指标？

如果你只会说「我加了缓存」「我用了分布式锁」而没有更深的细节，
那这轮面试可能不适合你。我们要的是能把问题拆到根因、能量化方案的架构师。"""


def _extract_project_section(text: str, max_chars: int = 600) -> str:
    lines = text.split("\n")
    project_lines = []
    in_project = False
    for line in lines:
        lower = line.strip().lower()
        if any(kw in lower for kw in ["项目", "project", "经历", "experience", "工作", "背景", "职责", "痛点"]):
            in_project = True
        if in_project:
            project_lines.append(line)
            if sum(len(l) for l in project_lines) > max_chars:
                break
    if not project_lines:
        return text[:max_chars] + "..."
    return "\n".join(project_lines)


def main():
    with open(LOG_FILE, "w", encoding="utf-8") as f:
        f.write("")

    log(">>> AI-Resume-Evolver v1.0 全链路压力测试")
    log("   测试场景: 张大壮 3年Python后端 → 字节跳动 AI基础设施架构师")
    log("=" * 60)

    log("\n[STEP 1] 加载测试材料...")

    resume_path = os.path.join("mock_resume.md")
    if os.path.exists(resume_path):
        raw_resume = load_txt(resume_path)
        log(f"[OK] 简历加载成功: {resume_path} ({len(raw_resume)} 字符)")
    else:
        raw_resume = "测试简历内容 - 张三，3年Python开发经验，熟悉FastAPI和数据库优化"
        log("[WARN] mock_resume.md 不存在，使用模拟数据")

    target_jd = create_test_jd()
    log(f"[OK] JD 已就绪: 字节跳动 高级商业化AI基础设施架构师 ({len(target_jd)} 字符)")

    state = GraphState(
        raw_resume=raw_resume,
        target_jd=target_jd,
        gap_list=[],
        rich_context_list=[],
        rag_context="",
        refined_resume="",
        feedback="",
        revision_count=0,
    )

    log("\n[STEP 2] 初始化 GraphState:")
    log(f"   - raw_resume: {len(state['raw_resume'])} 字符")
    log(f"   - target_jd: {len(state['target_jd'])} 字符")
    log(f"   - gap_list: {len(state['gap_list'])} 项 (待填充)")

    log("\n[STEP 3] ===== JD 分析节点 (jd_analyzer_node) =====")
    log("   任务: 提取 JD 关键词 + RAG 混合检索金牌案例")
    start_time = time.time()

    try:
        state = jd_analyzer_node(state)
        analyzer_time = time.time() - start_time
        log(f"\n[TIME] 分析节点耗时: {analyzer_time:.2f} 秒")

        log("\n[STEP 4] 分析结果:")
        log(f"   - gap_list 关键词总数: {len(state['gap_list'])}")

        if state["gap_list"]:
            log("\n[GAP_LIST] 提取的关键词 (前 20 项):")
            for i, term in enumerate(state["gap_list"][:20], 1):
                log(f"   {i:2d}. {term}")

        if state.get("rag_context"):
            log(f"\n[RAG_CONTEXT] 金牌案例召回 ({len(state['rag_context'])} 字符):")
            log(state["rag_context"][:800])
        else:
            log("\n[RAG_CONTEXT] (未召回案例，使用通用标准)")

        log("\n[STEP 5] ===== 简历优化节点 (resume_refiner_node) =====")
        log("   任务: DeepSeek-V4 重构简历 —— STAR法则 + 动词升级 + 量化注入")
        refiner_start = time.time()

        state = resume_refiner_node(state)
        refiner_time = time.time() - refiner_start
        log(f"\n[TIME] 优化节点耗时: {refiner_time:.2f} 秒")

        log("\n[STEP 6] 优化结果:")
        log(f"   - refined_resume 长度: {len(state['refined_resume'])} 字符")
        log(f"   - revision_count: {state['revision_count']}")

        log("\n" + "=" * 60)
        log("[COMPARE] 优化前后关键片段对比")
        log("=" * 60)

        before_snippet = _extract_project_section(state["raw_resume"])
        after_snippet = _extract_project_section(state["refined_resume"], max_chars=1000)

        log("\n--- 优化前 (原始简历项目片段) ---")
        log(before_snippet)

        log("\n--- 优化后 (重构简历项目片段) ---")
        log(after_snippet)

        log("\n" + "=" * 60)
        log(f"[总耗时] {analyzer_time + refiner_time:.2f} 秒 "
            f"(分析: {analyzer_time:.2f}s | 优化: {refiner_time:.2f}s)")
        log("[FINISH] 全链路压力测试完成 —— 请查看上方输出对比")
        log("=" * 60)

    except Exception as e:
        log(f"\n[FATAL] 测试失败: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            traceback.print_exc(file=f)


if __name__ == "__main__":
    main()
