"""
AI-Resume-Evolver  v2.6 FastAPI 路由网关

端点:
  GET  /health                           — 健康检查
  POST /api/v1/resume/optimize           — 简历优化（SSE 流式事件推送）

一键生成模式 (ONE_CLICK) — SSE 流式三帧推送:
  Frame 1 (radar_init):   PreEvaluator 完成 → 原始简历 6-3-1 雷达指标，前端渲染初始雷达图
  Frame 2 (resume_stream): Editor 完成 → 精修简历全文，前端打字机渐进显示
  Frame 3 (final):        Evaluator+Interviewer 完成 → 终评雷达 + 3 道面试压测题
  Frame 4 (done):         流结束信号

交互模式 (INTERACTIVE):
  暂未实现，返回 501 Not Implemented。

v2.6 更新:
  - ONE_CLICK 端点全面升级为 SSE StreamingResponse，用户可实时看到阶段性进度
  - 同步 LangGraph 调用通过 ThreadPoolExecutor + asyncio.Queue 隔离，不影响事件循环
  - 保留 run_in_threadpool + timeout_keep_alive=300 弹性配置
"""

import json
import os
import sys
import asyncio
import traceback
from contextlib import asynccontextmanager
from concurrent.futures import ThreadPoolExecutor

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from src.schemas.resume import (
    RadarMetrics,
    OptimizeMode,
    ResumeOptimizeRequest,
)
from src.graph import build_graph

# ── 启动时加载 .env ──
from dotenv import load_dotenv
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__) or ".", ".env"))


# ── SSE 工具函数 ──

def _sse_event(event: str, data: dict) -> str:
    """构建一条 SSE (Server-Sent Event) 消息帧"""
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def _build_radar(dims: dict, declared_score: int) -> "RadarMetrics | None":
    """从维度分数字典构建 RadarMetrics，含分项一致性校验"""
    if not dims:
        return None
    dims_sum = dims.get("jd_match", 0) + dims.get("star_completion", 0) + dims.get("verb_quality", 0)
    if declared_score > 0 and abs(declared_score - dims_sum) <= 3:
        total = declared_score
    elif dims_sum > 0:
        total = dims_sum
    else:
        total = declared_score
    return RadarMetrics.from_dimensions(dims, total)


def _build_stress_questions(raw_questions: list) -> list[dict]:
    """将 interviewer 节点返回的原始压测题转为前端可用的字典列表"""
    result = []
    for q in raw_questions:
        try:
            result.append({
                "question_number": q.get("question_number", len(result) + 1),
                "category": q.get("category", "技术深度"),
                "question": q.get("question", ""),
                "expected_points": q.get("expected_points", []),
            })
        except Exception as e:
            print(f"[api] 压测题解析失败: {e}")
    return result


# ── FastAPI 应用工厂 ──

@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期：启动时预热 ChromaDB，关闭时清理"""
    print("[server] AI-Resume-Evolver v2.6 启动中...")
    print("[server] 预热 ChromaDB 连接...")
    try:
        from src.config import get_vector_db_client, get_collection_name
        client = get_vector_db_client()
        collection = client.get_collection(name=get_collection_name())
        count = collection.count()
        print(f"[server] ChromaDB 就绪，共 {count} 条向量")
    except Exception as e:
        print(f"[server] ChromaDB 预热失败（非致命）: {e}")
    print("[server] 服务已就绪，接受请求。")
    yield
    print("[server] 服务关闭。")


app = FastAPI(
    title="AI-Resume-Evolver API",
    description="AI 简历智能优化引擎 —— 一键生成 + 多智能体博弈 + MockInterviewer 压测",
    version="2.6.0",
    lifespan=lifespan,
)

# ── CORS 跨域 ──
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── 健康检查 ──

@app.get("/health")
async def health_check():
    return {"status": "ok", "version": "2.6.0", "service": "AI-Resume-Evolver"}


# ── SSE 流式管道 ──

async def _stream_pipeline(initial_state: dict):
    """
    SSE 事件流生成器 —— 在 ThreadPoolExecutor 中运行 LangGraph 全链路，
    通过 asyncio.Queue 桥接同步图执行与异步 SSE 推送。

    事件序列:
      1. radar_init:   初筛完成 → 原始简历 6-3-1 雷达指标
      2. resume_stream: Editor 完成 → 精修简历全文
      3. final:         Evaluator + Interviewer 完成 → 终评雷达 + 压测题
      4. done:          流结束
      5. error:         异常（如有）
    """
    app_graph = build_graph()
    loop = asyncio.get_running_loop()
    queue: asyncio.Queue = asyncio.Queue()

    def _run_graph():
        """在子线程中同步执行 LangGraph stream，将每次状态快照推入队列"""
        try:
            for state in app_graph.stream(initial_state, stream_mode="values"):
                loop.call_soon_threadsafe(queue.put_nowait, ("state", state))
            loop.call_soon_threadsafe(queue.put_nowait, ("done", None))
        except Exception as e:
            loop.call_soon_threadsafe(queue.put_nowait, ("error", e))

    yielded_radar = False
    yielded_resume = False
    final_state = None

    with ThreadPoolExecutor(max_workers=1) as pool:
        pool.submit(_run_graph)

        while True:
            status, value = await queue.get()

            if status == "error":
                traceback.print_exc()
                yield _sse_event("error", {
                    "error": f"{type(value).__name__}: {str(value)[:200]}"
                })
                yield _sse_event("done", {})
                return

            if status == "done":
                break

            # status == "state": 处理每次节点完成后的全量状态快照
            state = value
            final_state = state

            # ── 里程碑 1: PreEvaluator 完成 → 推送原始简历雷达 ──
            if not yielded_radar and state.get("pre_eval_dimensions"):
                yielded_radar = True
                dims = state["pre_eval_dimensions"]
                pre_total = dims.get("jd_match", 0) + dims.get("star_completion", 0) + dims.get("verb_quality", 0)
                if pre_total == 0:
                    pre_total = state.get("score", 0)
                radar = RadarMetrics.from_dimensions(dims, pre_total)
                yield _sse_event("radar_init", {
                    "original_resume_radar": {
                        "jd_matching_score": radar.jd_matching_score,
                        "star_perf_score": radar.star_perf_score,
                        "action_verbs_score": radar.action_verbs_score,
                        "total_score": radar.total_score,
                    }
                })
                print(f"[sse] 分帧1 radar_init: 原始雷达 {pre_total}/100 "
                      f"(JD: {radar.jd_matching_score}/60, STAR: {radar.star_perf_score}/30, "
                      f"Verb: {radar.action_verbs_score}/10)")

            # ── 里程碑 2: Editor 完成 → 推送精修简历文本 ──
            if not yielded_resume and state.get("revised_resume"):
                yielded_resume = True
                revised = state["revised_resume"]
                yield _sse_event("resume_stream", {
                    "optimized_resume_text": revised,
                    "text_length": len(revised),
                })
                print(f"[sse] 分帧2 resume_stream: 精修文本 {len(revised)} 字符")

        # ── 里程碑 3: 全链路完成 → 推送终评雷达 + 压测题 ──
        if final_state:
            eval_dims = final_state.get("eval_dimensions", {})
            eval_score = final_state.get("score", 0)
            opt_radar = _build_radar(eval_dims, eval_score)

            questions = _build_stress_questions(
                final_state.get("stress_test_questions", [])
            )

            pre_eval_dims = final_state.get("pre_eval_dimensions", {})
            pre_total = (pre_eval_dims.get("jd_match", 0) +
                         pre_eval_dims.get("star_completion", 0) +
                         pre_eval_dims.get("verb_quality", 0))

            yield _sse_event("final", {
                "optimized_resume_radar": {
                    "jd_matching_score": opt_radar.jd_matching_score if opt_radar else 0,
                    "star_perf_score": opt_radar.star_perf_score if opt_radar else 0,
                    "action_verbs_score": opt_radar.action_verbs_score if opt_radar else 0,
                    "total_score": opt_radar.total_score if opt_radar else eval_score,
                },
                "optimized_resume_text": final_state.get("revised_resume", ""),
                "stress_test_questions": questions,
                "difficulty_flag": final_state.get("difficulty_flag", ""),
                "iteration_count": final_state.get("iteration_count", 0),
                "score_improvement": eval_score - pre_total if pre_total > 0 else 0,
                "internal_monologue": final_state.get("internal_monologue", ""),
            })
            print(f"[sse] 分帧3 final: 终评 {eval_score}/100, 压测题 {len(questions)} 道, "
                  f"提升 +{eval_score - pre_total if pre_total > 0 else 'N/A'} 分")

        yield _sse_event("done", {})
        print("[sse] 流式推送完成 (4/4 帧已全部发送)")


# ── 核心路由：简历优化 ──

@app.post("/api/v1/resume/optimize")
async def optimize_resume(request: ResumeOptimizeRequest):
    """
    简历优化接口 —— SSE 流式事件推送。

    **ONE_CLICK 模式** (StreamingResponse, text/event-stream):
    依次推送 4 帧 SSE 事件，前端可实时渲染阶段性进度：

    | 事件名 | 触发时机 | data 负载 |
    |--------|----------|-----------|
    | `radar_init` | PreEvaluator 初筛完成 | `original_resume_radar`: 原始简历 6-3-1 雷达指标，前端渲染初始雷达图 |
    | `resume_stream` | Editor 精修完成 | `optimized_resume_text`: 精修后完整简历文本，前端打字机渐进显示 |
    | `final` | Evaluator+Interviewer 完成 | `optimized_resume_radar`: 终评雷达, `stress_test_questions`: 3 道面试压测题, `score_improvement`: 提升分, `internal_monologue`: 毒舌批评 |
    | `done` | 流正常结束 | 空 JSON `{}`，前端关闭 EventSource |
    | `error` | 异常中断 | `error`: 异常信息，随后推送 `done` 关闭流 |

    **INTERACTIVE 模式**: 返回 HTTP 501 Not Implemented。
    """
    # ── 交互模式预留 ──
    if request.mode == OptimizeMode.INTERACTIVE:
        raise HTTPException(
            status_code=501,
            detail="对话式深度访谈模式正在研发中，当前请使用一键极速优化模式（one_click）。"
        )

    # ── 一键生成模式 (SSE 流式) ──
    print(f"\n[api] 收到一键优化请求: 简历 {len(request.resume_text)} 字符, "
          f"JD {len(request.jd_text)} 字符")

    initial_state = {
        "resume": request.resume_text,
        "jd": request.jd_text,
        "rag_context": "",
        "revised_resume": "",
        "internal_monologue": "",
        "tool_outputs": [],
        "score": 0,
        "evaluation_feedback": "",
        "iteration_count": 0,
        "difficulty_flag": "",
        "node_status": "",
        "pre_eval_dimensions": {},
        "eval_dimensions": {},
        "stress_test_questions": [],
    }

    return StreamingResponse(
        _stream_pipeline(initial_state),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# ── 直接启动入口 ──

if __name__ == "__main__":
    import uvicorn
    print("启动 AI-Resume-Evolver FastAPI 服务...")
    uvicorn.run(
        "main:app",
        host="127.0.0.1",       # v2.6: 死锁 127.0.0.1，根除 Windows 0.0.0.0 解析冲突
        port=8000,
        reload=False,
        log_level="info",
        timeout_keep_alive=300,  # 长连接保活 5 分钟（覆盖串行 LLM 调用的完整链路）
        timeout_graceful_shutdown=30,
    )
