"""
Phase 3.5 v2.2: 5级梯度简历基准测试（6-3-1 权重 + CS 抽象层级对齐 + 流程锁死）
验证 CRITICAL_LOW_THRESHOLD=40 的边界切分精度
"""
import os, sys, time, json
sys.path.insert(0, os.path.abspath("."))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from dotenv import load_dotenv
load_dotenv()

os.environ["USE_PRO_MODEL"] = "false"

from src.graph import get_graph, PASS_THRESHOLD, CRITICAL_LOW_THRESHOLD, MAX_ITERATIONS
from src.state import AgentState

# ── 固定 JD ────────────────────────────────────────────────────
TARGET_JD = """岗位：高级 Python 后端开发工程师（供应链核心业务组）
技术栈要求：Python, FastAPI, MySQL, Redis, RocketMQ, Docker, WMS/ERP集成
职责特征：强调多系统数据对齐高并发、慢查询优化、消息队列异步解耦，要求简历清晰体现项目成果与量化指标（STAR法则）。"""

# ── 5 份梯度简历 ────────────────────────────────────────────────
RESUMES = {
    "Level 1 (彻底绝望型)": """个人简介：会写Python，听说过一些大厂黑话，想找一份稳定的后端开发工作，听话好管理。
精通技能：Python, Word, Excel, 网页增删改查。
项目经历：
个人博客系统 & 网店管理后台：独立用 Django 框架写了一个网店的后台管理。实现了商品信息的添加、删除、修改、查询功能。前端页面是用 HTML 搓的，能正常跑起来，没有报错。""",

    "Level 2 (勉强挣扎型)": """个人简介：1年多后端经验，自学能力强，做过企业内部管理系统，熟悉关系型数据库。
精通技能：Python, Flask, MySQL, Git, Linux。
项目经历：
某公司内部进销存管理系统：负责后台部分模块的开发。使用 Flask 框架编写了商品入库和出库的 API 接口。在数据库设计中建了商品表和库存表，用 SQL 进行数据关联查询。项目上线后运行稳定，满足了公司内部日常十几个人使用的报表查看需求。""",

    "Level 3 (有拯救空间型)": """个人简介：2年半后端开发经验，主攻 Python 异步 Web 开发，熟悉常用中间件，有 WMS 仓储系统研发经验。
精通技能：Python, FastAPI, MySQL, Redis, RabbitMQ, Docker。
项目经历：
中小型在线仓储（WMS）系统重构：参与了仓储系统从旧框架向 FastAPI 异步框架的切换。负责设计和优化库存核心接口。使用 Redis 缓存了高频读取的商品基础数据，减少了对 MySQL 的直接访问。在订单出库环节，尝试引入 RabbitMQ 异步处理通知，初步实现了业务解耦。""",

    "Level 4 (完全符合型)": """个人简介：3年半硬核后端专家，主导过中型跨境电商供应链平台的核心架构设计，擅长高并发分布式系统调优。
精通技能：Python, FastAPI, MySQL, Redis集群, RocketMQ, 全链路监控。
项目经历：
全球供应链多系统数据协同平台（核心架构）：作为核心开发，主导了 ERP、WMS 与第三方物流系统之间的数据高频对齐模块。面对每日千万级的消息吞吐，基于 FastAPI + Asyncio 编写了高性能异步非阻塞 API。引入 RocketMQ 消息队列承载核心出入库事务，通过多级重试与幂等性校验，将数据对齐延迟从 5秒 降至 200ms 内。针对 MySQL 订单主表进行了联合索引优化与读写分离，成功将大促期间的慢查询率降低了 42%。""",

    "Level 5 (降维打击型)": """个人简介：4年以上前一线大厂高级技术专家。深入 Python 解释器底层源码，主导过多活分布式架构研发，精通大模型 RAG 在企业级落地。
精通技能：Distributed Systems, Python Core, C++, Cloud Native, 混合检索架构。
项目经历：
超大规模供应链全链路数智化底座：从零构建了支撑百亿级 GMV 的分布式多租户协同平台。设计了布隆过滤器 + 多级 Redis 缓存锁的防击穿架构，扛住了每秒 5W+ 的峰值并发。通过定制化优化 RocketMQ 消费端和底层 B-Tree 索引，实现了强一致性的分布式事务控制。此外，创新性地引入了向量数据库混合检索技术对海量货品术语进行动态召回对齐，语义相似度识别准确率达 98.7%。""",
}


def run_single_test(label: str, resume_text: str):
    """对单份简历跑全链路，捕获 pre_evaluator 分诊 + 最终路由"""
    app = get_graph()
    initial: AgentState = {
        "resume": resume_text,
        "jd": TARGET_JD,
        "rag_context": "",
        "revised_resume": "",
        "internal_monologue": "",
        "tool_outputs": [],
        "score": 0,
        "evaluation_feedback": "",
        "iteration_count": 0,
        "difficulty_flag": "",
        "node_status": "",
    }

    print(f"\n{'─' * 55}")
    print(f"  [{label}]")
    print(f"  原始简历: {len(resume_text)} 字符")
    print(f"{'─' * 55}")

    t0 = time.time()
    node_seq = []
    pre_eval_score = None
    pre_eval_dims = {}
    pre_eval_flag = ""
    pre_eval_tiers = ""
    final_eval_score = None
    final_eval_dims = {}
    routing_path = ""

    for output in app.stream(initial, stream_mode="updates"):
        for node_name, node_output in output.items():
            node_seq.append(node_name)
            ts = time.time() - t0

            info = f"  [{ts:5.1f}s] {node_name}"

            if node_name == "pre_evaluator":
                s = node_output.get("score", 0)
                pre_eval_score = s
                pre_eval_dims = {}
                pre_eval_flag = node_output.get("difficulty_flag", "")
                node_status = node_output.get("node_status", "")
                pre_eval_tiers = node_status[:60] if node_status else ""
                info += f" -> raw_score={s}/100 (6-3-1)"
                if pre_eval_flag == "EXTREME_GAP":
                    info += f" [{pre_eval_flag}]"
                else:
                    info += f" [NORMAL]"

            elif node_name == "editor":
                out_len = len(str(node_output.get("revised_resume", "")))
                info += f" -> output {out_len} chars"

            elif node_name == "evaluator":
                s = node_output.get("score", 0)
                final_eval_score = s
                fb = node_output.get("evaluation_feedback", "")
                dims = {}
                for pat, key in [("jd_match", "JD"), ("star_completion", "STAR"), ("verb_quality", "动词")]:
                    m = __import__("re").search(rf'{key}[:\s]*(\d+)', str(fb)[:500])
                    if m:
                        dims[pat] = int(m.group(1))
                final_eval_dims = dims
                info += f" -> score={s}/100"
                if s >= PASS_THRESHOLD:
                    info += " [PASS]"
                else:
                    info += " [NEEDS_WORK]"

            elif node_name == "polisher":
                info += f" (round {node_output.get('iteration_count', '?')})"

            if "difficulty_flag" in node_output:
                df = node_output.get("difficulty_flag", "")
                if df:
                    info += f" flag={df}"

            print(info)

    final_state = app.invoke(initial)
    elapsed = time.time() - t0

    difficulty = final_state.get("difficulty_flag", "")
    final_score = final_state.get("score", 0)
    iteration = final_state.get("iteration_count", 0)

    # ── 路由判定 ──
    if difficulty == "EXTREME_GAP":
        routing_path = "PreEval熔断 -> Editor(防幻觉骨架) -> Evaluator -> END"
    elif final_score >= PASS_THRESHOLD:
        routing_path = "闪电通关: Editor -> Evaluator -> END"
    elif final_score >= CRITICAL_LOW_THRESHOLD:
        if iteration > 1:
            routing_path = f"精细博弈: Editor -> Evaluator <-> Polisher ({iteration}轮) -> END"
        else:
            routing_path = "Editor -> Evaluator -> END (未触发博弈)"
    else:
        routing_path = "安全网: Polisher 硬核重组 -> END"

    revised = final_state.get("revised_resume", "")
    placeholder_count = revised.count("[请") if revised else 0

    return {
        "label": label,
        "resume_len": len(resume_text),
        "pre_eval_score": pre_eval_score,
        "pre_eval_flag": pre_eval_flag,
        "pre_eval_tiers": pre_eval_tiers,
        "final_eval_score": final_eval_score if final_eval_score else final_score,
        "final_dims": final_eval_dims,
        "routing_path": routing_path,
        "elapsed": elapsed,
        "node_seq": " -> ".join(node_seq),
        "output_len": len(revised),
        "placeholder_count": placeholder_count,
        "iteration": iteration,
    }


def main():
    print("=" * 65)
    print("  Phase 3.5 v2.2: 5级梯度简历基准测试 (6-3-1 + CS 层级对齐)")
    print(f"  PASS_THRESHOLD={PASS_THRESHOLD}, CRITICAL_LOW={CRITICAL_LOW_THRESHOLD}")
    print(f"  流程锁死: 所有简历必经 Editor -> Evaluator")
    print(f"  JD: 高级 Python 后端开发工程师 (供应链)")
    print("=" * 65)

    results = []
    for label, resume in RESUMES.items():
        result = run_single_test(label, resume)
        results.append(result)

    # ── 汇总表格 ──
    print("\n")
    print("=" * 110)
    print("  基准测试汇总 (v2.2: 6-3-1 权重 + CS 抽象层级对齐 + 流程锁死)")
    print("=" * 110)
    header = (f"{'Level':<24s} {'字数':>5s} {'PreEval':>7s} "
              f"{'分诊':>12s} {'抽象层级':>20s} {'终评':>7s} {'占位':>5s} {'路由路径'}")
    print(header)
    print("-" * 110)

    for r in results:
        pre_score_str = f"{r['pre_eval_score']}/100" if r['pre_eval_score'] is not None else "N/A"
        flag_str = "EXTREME_GAP" if r['pre_eval_flag'] == "EXTREME_GAP" else "NORMAL"
        tiers_str = r.get('pre_eval_tiers', '')[:20]
        final_str = f"{r['final_eval_score']}/100" if r['final_eval_score'] else "N/A"
        ph_str = str(r['placeholder_count']) if r['placeholder_count'] > 0 else "-"

        print(f"{r['label']:<24s} {r['resume_len']:>5d} {pre_score_str:>7s} "
              f"{flag_str:>12s} {tiers_str:>20s} {final_str:>7s} {ph_str:>5s} {r['routing_path']}")

    print("-" * 110)
    print(f"\n权重模型: 6-3-1 (JD匹配 60分 | STAR 30分 | 动词 10分)")
    print(f"阈值线: PASS={PASS_THRESHOLD}, CRITICAL_LOW={CRITICAL_LOW_THRESHOLD}")
    print(f"模型: DeepSeek-V4-Flash + CS 抽象层级对齐框架")
    print(f"拓扑约束: PreEvaluator 仅标记 difficulty_flag, 不退出; 所有简历必经 Editor")

    # ── 边界分析 ──
    print("\n[边界切分分析 (6-3-1 权重 + 抽象层级对齐)]")

    for r in results:
        ps = r['pre_eval_score']
        if ps is None:
            continue
        label = r['label']
        flag = r['pre_eval_flag']
        tiers = r.get('pre_eval_tiers', '')
        if flag == "EXTREME_GAP":
            zone = f"绝望区 (score={ps} < {CRITICAL_LOW_THRESHOLD}) -> 防幻觉骨架"
        else:
            zone = f"正常区 (score={ps} >= {CRITICAL_LOW_THRESHOLD}) -> 正常精修"
        print(f"  {label}: PreEval={ps}/100 -> {zone}")
        if tiers:
            print(f"         层级: {tiers}")

    # ── 阈值合理性评估 ──
    l1_pe = next((r['pre_eval_score'] for r in results if "Level 1" in r['label']), None)
    l2_pe = next((r['pre_eval_score'] for r in results if "Level 2" in r['label']), None)
    l3_pe = next((r['pre_eval_score'] for r in results if "Level 3" in r['label']), None)
    l4_pe = next((r['pre_eval_score'] for r in results if "Level 4" in r['label']), None)
    l5_pe = next((r['pre_eval_score'] for r in results if "Level 5" in r['label']), None)

    print(f"\n[阈值合理性评估]")
    print(f"  PreEvaluator (6-3-1): L1={l1_pe} | L2={l2_pe} | L3={l3_pe} | L4={l4_pe} | L5={l5_pe}")
    print(f"  当前熔断线: {CRITICAL_LOW_THRESHOLD}")

    if l2_pe is not None and l3_pe is not None:
        if l2_pe < CRITICAL_LOW_THRESHOLD and l3_pe >= CRITICAL_LOW_THRESHOLD:
            print(f"  >> 阈值 {CRITICAL_LOW_THRESHOLD} 精准切分 L2({l2_pe}) 和 L3({l3_pe})！无需调整。")
        elif l2_pe >= CRITICAL_LOW_THRESHOLD:
            print(f"  >> L2({l2_pe}) >= 阈值({CRITICAL_LOW_THRESHOLD})，L2 未被熔断。")
            print(f"     建议: 微调 CRITICAL_LOW_THRESHOLD 至 {l2_pe + 5} 以确保 L1/L2 进熔断")
        elif l3_pe < CRITICAL_LOW_THRESHOLD:
            print(f"  >> L3({l3_pe}) < 阈值({CRITICAL_LOW_THRESHOLD})，L3 被误熔断。")
            print(f"     建议: 降低 CRITICAL_LOW_THRESHOLD 至 {max(l3_pe - 5, 20)} 以给 L3 博弈机会")

    # ── L5 层级对齐验证 ──
    if l5_pe is not None:
        print(f"\n[L5 层级对齐验证]")
        l5_flag = next((r['pre_eval_flag'] for r in results if "Level 5" in r['label']), "")
        l5_tiers = next((r.get('pre_eval_tiers', '') for r in results if "Level 5" in r['label']), "")
        if l5_flag == "EXTREME_GAP":
            print(f"  >> 警告: L5(降维打击型) 仍被标记为 EXTREME_GAP (score={l5_pe})")
            print(f"     层级判定: {l5_tiers}")
            print(f"     CS 抽象层级对齐框架可能尚未完全解决专家型简历被低估的问题")
        else:
            print(f"  >> L5(降维打击型) 标记为 NORMAL (score={l5_pe} >= {CRITICAL_LOW_THRESHOLD})")
            print(f"     层级判定: {l5_tiers}")
            print(f"     CS 抽象层级对齐框架成功识别专家型简历的高层级语义")

    # ── 防幻觉验证 ──
    print(f"\n[防幻觉骨架效果]")
    for r in results:
        if r['pre_eval_flag'] == "EXTREME_GAP":
            print(f"  {r['label']}: 占位符 {r['placeholder_count']} 处, 输出 {r['output_len']} 字符")
        else:
            print(f"  {r['label']}: NORMAL 正常模式, 输出 {r['output_len']} 字符")

    # ── 导出 JSON ──
    json_safe = []
    for r in results:
        jr = dict(r)
        jr['final_dims'] = str(jr.get('final_dims', {}))
        json_safe.append(jr)

    os.makedirs("output", exist_ok=True)
    with open("output/benchmark_results_v2.2.json", "w", encoding="utf-8") as f:
        json.dump(json_safe, f, ensure_ascii=False, indent=2)
    print(f"\n[JSON] 完整结果 -> output/benchmark_results_v2.2.json")

    print("\n" + "=" * 65)
    print("  v2.2 基准测试完成")
    print("=" * 65)


if __name__ == "__main__":
    main()
