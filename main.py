"""
AI-Resume-Evolver v3.0 FastAPI 路由网关

端点:
  GET  /health                           — 健康检查
  POST /api/v1/resume/optimize           — 简历优化（SSE 流式事件推送）
  POST /api/v1/resume/chat               — 多轮对话交互编辑（SSE 流式）

一键生成模式 (ONE_CLICK) — SSE 流式四帧推送:
  Frame 1 (radar_init):   PreEvaluator 完成 → 原始简历 6-3-1 雷达指标，前端渲染初始雷达图
  Frame 2 (resume_stream): Editor 完成 → 精修简历全文，前端打字机渐进显示
  Frame 3 (final):        Evaluator+Interviewer 完成 → 终评雷达 + 3 道面试压测题
  Frame 4 (done):         流结束信号

交互模式 (INTERACTIVE) — SSE 流式三帧推送:
  Frame 1 (status):       chat_editor 增量编辑完成 → 当前节点状态 (复用 resume_stream 帧携带 node_status)
  Frame 2 (resume_stream): 更新后的简历全文 + node_status 状态帧
  Frame 3 (final):        Evaluator+Interviewer 完成 → 终评雷达 + 压测题
  Frame N (done):         流结束信号

v3.0 更新:
  - 引入 MemorySaver 断点续传，全图编译挂载 checkpointer
  - 新增 /api/v1/resume/chat 多轮对话端点，支持 thread_id 会话隔离
  - graph 入口 router 自动分流一键模式 / 交互模式
  - ONE_CLICK 端点对接共享图实例，自动生成 session_id 供后续 chat 续接
"""
#uvicorn main:app --host 127.0.0.1 --port 8001 --reload
#npm run dev
#taskkill /f /im python.exe
#taskkill /f /im node.exe
import json
import os
import sys
import uuid
import asyncio
import traceback
from contextlib import asynccontextmanager
from concurrent.futures import ThreadPoolExecutor

import io
import tempfile
from pathlib import Path

from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from src.schemas.resume import (
    RadarMetrics,
    OptimizeMode,
    ResumeOptimizeRequest,
    ChatRequest,
)
from src.graph import build_graph
from src.routes.agent_router import router as agent_router
from src.nodes.visual_payload import compile_to_visual_payload
from langgraph.checkpoint.memory import MemorySaver

# ── 启动时加载 .env ──
from dotenv import load_dotenv
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__) or ".", ".env"))

# ── v3.0: 应用级共享图实例，挂载 MemorySaver 断点续传 ──
_app_graph = build_graph(checkpointer=MemorySaver())


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


def _safe_list(dims: dict, key: str) -> list[str]:
    """从 dimension_scores 字典安全提取列表字段并转字符串列表"""
    val = dims.get(key, [])
    if isinstance(val, list):
        return [str(v) for v in val]
    if isinstance(val, str):
        return [val] if val else []
    return []


# ── FastAPI 应用工厂 ──

@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期：启动时预热 ChromaDB + MemorySaver，关闭时清理"""
    print("[server] AI-Resume-Evolver v4.1 启动中...")
    print("[server] MemorySaver 断点续传已挂载到共享图实例")
    print("[server] 预热 ChromaDB 连接 + 种子数据守卫...")
    try:
        from src.config import get_vector_db_client, get_collection_name, ensure_seed_data
        # ── v4.1 种子数据守卫：空库自动灌入金牌案例 ──
        seeded = ensure_seed_data()
        if seeded > 0:
            print(f"[server] 🛡️ 种子数据守卫已激活：自动灌入 {seeded} 条金牌案例")
        # 二次确认库状态
        client = get_vector_db_client()
        collection = client.get_or_create_collection(name=get_collection_name())
        count = collection.count()
        print(f"[server] ChromaDB 就绪，Collection '{get_collection_name()}' 共 {count} 条向量")
    except Exception as e:
        print(f"[server] ChromaDB 预热失败（非致命）: {e}")
    print("[server] 服务已就绪，接受请求。")
    yield
    print("[server] 服务关闭。")


app = FastAPI(
    title="AI-Resume-Evolver API",
    description="AI 简历智能优化引擎 —— 一键生成 + 多智能体博弈 + MockInterviewer 压测 + 多轮交互",
    version="3.0.0",
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
    return {"status": "ok", "version": "3.0.0", "service": "AI-Resume-Evolver"}


# ── SSE 流式管道 ──

async def _stream_pipeline(initial_state: dict, thread_id: str = ""):
    """
    SSE 事件流生成器 —— 在 ThreadPoolExecutor 中运行 LangGraph 全链路，
    通过 asyncio.Queue 桥接同步图执行与异步 SSE 推送。

    使用应用级共享图 _app_graph，通过 thread_id 启用 MemorySaver 断点续传。
    一键模式初始 user_supplement 为空，entry_router 自动走 retriever 全链路。

    事件序列:
      1. radar_init:   初筛完成 → 原始简历 6-3-1 雷达指标
      2. resume_stream: Editor 完成 → 精修简历全文
      3. final:         Evaluator + Interviewer 完成 → 终评雷达 + 压测题
      4. done:          流结束
      5. error:         异常（如有）
    """
    loop = asyncio.get_running_loop()
    queue: asyncio.Queue = asyncio.Queue()
    config = {"configurable": {"thread_id": thread_id}} if thread_id else {}

    def _run_graph():
        """在子线程中同步执行 LangGraph stream，将每次状态快照推入队列"""
        try:
            for state in _app_graph.stream(initial_state, config=config, stream_mode="values"):
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

            # ── 里程碑 1: PreEvaluator 完成 → 推送原始简历雷达 + 诊断原文 ──
            if not yielded_radar and state.get("pre_eval_dimensions"):
                yielded_radar = True
                dims = state["pre_eval_dimensions"]
                pre_total = dims.get("jd_match", 0) + dims.get("star_completion", 0) + dims.get("verb_quality", 0)
                if pre_total == 0:
                    pre_total = state.get("score", 0)
                radar = RadarMetrics.from_dimensions(dims, pre_total)

                # ── v4.6 诊断原文：从 pre_eval_dimensions 提取结构化诊断数据 ──
                diagnosis = {
                    "feedback": state.get("evaluation_feedback", ""),
                    "core_tool_overlap": state.get("node_status", ""),
                    "matched_skills": _safe_list(dims, "matched_skills"),
                    "missing_skills": _safe_list(dims, "missing_skills"),
                    "star_strengths": _safe_list(dims, "star_strengths"),
                    "star_weaknesses": _safe_list(dims, "star_weaknesses"),
                    "weak_verbs": _safe_list(dims, "weak_verbs"),
                }

                yield _sse_event("radar_init", {
                    "original_resume_radar": {
                        "jd_matching_score": radar.jd_matching_score,
                        "star_perf_score": radar.star_perf_score,
                        "action_verbs_score": radar.action_verbs_score,
                        "total_score": radar.total_score,
                    },
                    "diagnosis": diagnosis,
                })
                print(f"[sse] 分帧1 radar_init: 原始雷达 {pre_total}/100 "
                      f"(JD: {radar.jd_matching_score}/60, STAR: {radar.star_perf_score}/30, "
                      f"Verb: {radar.action_verbs_score}/10) | "
                      f"覆盖技能: {len(diagnosis['matched_skills'])}项, "
                      f"缺失: {len(diagnosis['missing_skills'])}项")

            # ── 里程碑 2: Editor 完成 → 推送精修简历文本 + 混合解耦载荷 ──
            if not yielded_resume and state.get("revised_resume"):
                yielded_resume = True
                revised = state["revised_resume"]
                opt_summary = state.get("optimization_summary", "")
                clean_json = state.get("clean_resume_json", {})
                vp = compile_to_visual_payload(revised)
                yield _sse_event("resume_stream", {
                    "optimized_resume_text": revised,
                    "text_length": len(revised),
                    "optimization_summary": opt_summary,
                    "clean_resume_json": clean_json,
                    "visual_payload": vp,
                })
                print(f"[sse] 分帧2 resume_stream: 精修文本 {len(revised)} 字符, "
                      f"skills={len(vp.get('skills', []))}项, "
                      f"summary {len(opt_summary)} 字符, json_keys {list(clean_json.keys()) if clean_json else '[]'}")

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

            is_extreme_gap = final_state.get("difficulty_flag", "") == "EXTREME_GAP"
            revised_final = final_state.get("revised_resume", "")
            vp_final = compile_to_visual_payload(revised_final) if revised_final else {}

            yield _sse_event("final", {
                "optimized_resume_radar": {
                    "jd_matching_score": opt_radar.jd_matching_score if opt_radar else 0,
                    "star_perf_score": opt_radar.star_perf_score if opt_radar else 0,
                    "action_verbs_score": opt_radar.action_verbs_score if opt_radar else 0,
                    "total_score": opt_radar.total_score if opt_radar else eval_score,
                },
                "optimized_resume_text": revised_final,
                "stress_test_questions": questions,
                "difficulty_flag": final_state.get("difficulty_flag", ""),
                "is_extreme_gap": is_extreme_gap,
                "iteration_count": final_state.get("iteration_count", 0),
                "score_improvement": eval_score - pre_total if pre_total > 0 else 0,
                "internal_monologue": final_state.get("internal_monologue", ""),
                "evaluation_feedback": final_state.get("evaluation_feedback", ""),
                "pre_eval_dimensions": pre_eval_dims,
                "eval_dimensions": eval_dims,
                "optimization_summary": final_state.get("optimization_summary", ""),
                "clean_resume_json": final_state.get("clean_resume_json", {}),
                "visual_payload": vp_final,
                "session_id": thread_id,
            })
            print(f"[sse] 分帧3 final: 终评 {eval_score}/100, 压测题 {len(questions)} 道, "
                  f"提升 +{eval_score - pre_total if pre_total > 0 else 'N/A'} 分")

        yield _sse_event("done", {})
        print(f"[sse] 流式推送完成 (4/4 帧已全部发送), thread_id={thread_id}")


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
    | `final` | Evaluator+Interviewer 完成 | `optimized_resume_radar`: 终评雷达, `stress_test_questions`: 3 道面试压测题, `score_improvement`: 提升分, `internal_monologue`: 毒舌批评, `session_id`: 会话 ID 供后续 chat 续接 |
    | `done` | 流正常结束 | 空 JSON `{}`，前端关闭 EventSource |
    | `error` | 异常中断 | `error`: 异常信息，随后推送 `done` 关闭流 |

    **INTERACTIVE 模式**: 已并网！前端应在拿到 session_id 后，通过 /api/v1/resume/chat 发起多轮补充。
    此端点返回的 final 帧中包含 session_id，前端需保存该 ID 用于后续 chat 调用。
    """
    # ── v4.2 三层漏斗 Layer 1: 动态复合钥匙 f"{user_id}_{resume_id}" ──
    user_id = request.user_id
    resume_id = request.resume_id
    thread_id = f"{user_id}::{resume_id}"
    print(f"[记忆沙箱点火] 线程已锁定: {thread_id}")

    print(f"\n[api] 收到优化请求 [{request.mode.value}]: 简历 {len(request.resume_text)} 字符, "
          f"JD {len(request.jd_text)} 字符, thread_id={thread_id}")

    initial_state = {
        "user_id": user_id,
        "resume_id": resume_id,
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
        "optimization_summary": "",
        "clean_resume_json": {},
        "chat_history": [],
        "user_supplement": "",
        "session_id": "",      # 一键模式不注入 session_id，eval_condition 走正常分诊
        "turn_count": 0,
        "step_count": 0,
        "total_tokens": 0,
    }

    return StreamingResponse(
        _stream_pipeline(initial_state, thread_id=thread_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# ── 交互模式 SSE 流式管道 ──

async def _stream_chat_pipeline(thread_id: str, user_message: str):
    """
    交互模式 SSE 事件流生成器 —— 接收用户补充信息，通过共享图 _app_graph
    在已有 session 的 checkpoint 上续跑，走 chat_editor → evaluator 闭环。

    事件序列:
      1. status:       chat_editor 完成 → node_status 状态帧
      2. resume_stream: 更新后的简历全文 (含 node_status)
      3. final:         Evaluator 评分 + Interviewer 压测题
      4. done:          流结束
      5. error:         异常（如有）
    """
    loop = asyncio.get_running_loop()
    queue: asyncio.Queue = asyncio.Queue()
    config = {"configurable": {"thread_id": thread_id}}

    initial_input = {
        "user_supplement": user_message,
        "session_id": thread_id,  # 注入 session_id 以激活交互模式路由
        # v4.2: 从复合钥匙中解包身份标识，注入状态机供 retriever 元数据过滤
        "user_id": thread_id.split("::")[0] if "::" in thread_id else "default_user",
        "resume_id": thread_id.split("::")[1] if "::" in thread_id else "default_resume",
        "step_count": 0,
        "total_tokens": 0,
    }

    print(f"[记忆沙箱点火] 线程已锁定: {thread_id}")
    print(f"[chat_sse] 启动交互流: thread_id={thread_id}, "
          f"user_message={len(user_message)} 字符")

    def _run_graph():
        try:
            for state in _app_graph.stream(initial_input, config=config, stream_mode="values"):
                loop.call_soon_threadsafe(queue.put_nowait, ("state", state))
            loop.call_soon_threadsafe(queue.put_nowait, ("done", None))
        except Exception as e:
            loop.call_soon_threadsafe(queue.put_nowait, ("error", e))

    final_state = None
    last_resume_len = 0

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

            state = value
            final_state = state

            # ── 帧: node_status 状态推送 (对齐前端 status case) ──
            node_status = state.get("node_status", "")
            if node_status:
                yield _sse_event("status", {
                    "node_status": node_status,
                    "turn_count": state.get("turn_count", 0),
                })
                print(f"[chat_sse] status: {node_status[:80]}...")

            # ── 帧: 简历文本变更推送 (对齐前端 resume_stream case) ──
            revised = state.get("revised_resume", "")
            if revised and len(revised) != last_resume_len:
                last_resume_len = len(revised)
                vp = compile_to_visual_payload(revised)
                yield _sse_event("resume_stream", {
                    "optimized_resume_text": revised,
                    "text_length": len(revised),
                    "turn_count": state.get("turn_count", 0),
                    "node_status": node_status or "",
                    "visual_payload": vp,
                })
                print(f"[chat_sse] resume_stream: {len(revised)} 字符, "
                      f"skills={len(vp.get('skills', []))}项")

        # ── 终帧: 评分 + 压测题 + 混合解耦载荷 ──
        if final_state:
            eval_dims = final_state.get("eval_dimensions", {})
            eval_score = final_state.get("score", 0)
            opt_radar = _build_radar(eval_dims, eval_score)

            questions = _build_stress_questions(
                final_state.get("stress_test_questions", [])
            )

            revised_final = final_state.get("revised_resume", "")
            vp_final = compile_to_visual_payload(revised_final) if revised_final else {}

            yield _sse_event("final", {
                "optimized_resume_radar": {
                    "jd_matching_score": opt_radar.jd_matching_score if opt_radar else 0,
                    "star_perf_score": opt_radar.star_perf_score if opt_radar else 0,
                    "action_verbs_score": opt_radar.action_verbs_score if opt_radar else 0,
                    "total_score": opt_radar.total_score if opt_radar else eval_score,
                },
                "optimized_resume_text": revised_final,
                "stress_test_questions": questions,
                "difficulty_flag": final_state.get("difficulty_flag", ""),
                "turn_count": final_state.get("turn_count", 0),
                "internal_monologue": final_state.get("internal_monologue", ""),
                "visual_payload": vp_final,
                "session_id": thread_id,
            })
            print(f"[chat_sse] final: 终评 {eval_score}/100, "
                  f"skills={len(vp_final.get('skills', []))}项, "
                  f"轮次 {final_state.get('turn_count', 0)}, 压测题 {len(questions)} 道")

        yield _sse_event("done", {})
        print(f"[chat_sse] 交互流推送完成, thread_id={thread_id}")


# ── 交互模式路由：多轮对话 ──

@app.post("/api/v1/resume/chat")
async def chat_resume(request: ChatRequest):
    """
    多轮对话交互编辑接口 —— SSE 流式事件推送。

    前端需先通过 /api/v1/resume/optimize 获取 session_id，
    再将该 session_id 作为 thread_id 传入本端点进行多轮补充。

    **事件帧序列**:

    | 事件名 | 触发时机 | data 负载 |
    |--------|----------|-----------|
    | `status` | 节点状态变更 | `node_status`: 当前阶段描述, `turn_count`: 当前轮次 |
    | `resume_stream` | chat_editor 完成增量编辑 | `optimized_resume_text`: 更新后简历全文, `text_length`: 字符数, `node_status`: 状态信息 |
    | `final` | Evaluator+Interviewer 完成 | `optimized_resume_radar`: 终评雷达, `stress_test_questions`: 压测题, `turn_count`: 总轮次 |
    | `done` | 流正常结束 | 空 JSON `{}` |
    | `error` | 异常中断 | `error`: 异常信息 |
    """
    print(f"\n[api] 收到交互补充请求: thread_id={request.thread_id}, "
          f"message={len(request.user_message)} 字符")

    return StreamingResponse(
        _stream_chat_pipeline(request.thread_id, request.user_message),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )

# ── 多模态文件上传解析端点 ──

@app.post("/api/v1/upload/parse")
async def upload_and_parse(file: UploadFile = File(...)):
    """
    文件/截屏上传解析端点 —— 支持 PDF/DOCX/TXT 文件物理去噪 + 图片多模态 Vision OCR。

    **支持的文件类型**:
    - `.pdf`  → pypdf 逐页提取文本
    - `.docx` → docx2txt 结构化文本提取
    - `.txt` / `.md` → 直接 UTF-8 读取
    - `.png` / `.jpg` / `.jpeg` / `.webp` / `.gif` / `.bmp` → DeepSeek 多模态视觉解析

    **响应体**:
    ```json
    {"success": true, "text": "提取的纯文本", "file_type": "pdf|docx|txt|image", "filename": "原始文件名"}
    ```
    """
    filename = file.filename or "unknown"
    ext = Path(filename).suffix.lower()

    # 文件大小安全校验：上限 20MB
    MAX_SIZE = 20 * 1024 * 1024
    raw_bytes = await file.read()
    if len(raw_bytes) > MAX_SIZE:
        raise HTTPException(status_code=413, detail="文件过大，请上传 20MB 以内的文件")
    if len(raw_bytes) == 0:
        raise HTTPException(status_code=400, detail="文件为空，请重新选择文件")

    print(f"[upload] 收到上传文件: {filename} ({len(raw_bytes)} bytes, type={ext})")

    try:
        # ── 纯文本类 ──
        if ext in (".txt", ".md"):
            text = raw_bytes.decode("utf-8").strip()
            print(f"[upload] TXT 解析完成: {len(text)} 字符")
            return {"success": True, "text": text, "file_type": "txt", "filename": filename}

        # ── PDF ──
        if ext == ".pdf":
            from pypdf import PdfReader

            reader = PdfReader(io.BytesIO(raw_bytes))
            pages: list[str] = []
            for page in reader.pages:
                page_text = page.extract_text()
                if page_text:
                    pages.append(page_text)
            text = "\n".join(pages).strip()
            if not text:
                raise HTTPException(status_code=422, detail="PDF 无法提取文本，可能是扫描件或图片型 PDF，请尝试截图后用图片上传")
            print(f"[upload] PDF 解析完成: {len(text)} 字符, {len(pages)} 页")
            return {"success": True, "text": text, "file_type": "pdf", "filename": filename}

        # ── DOCX ──
        if ext == ".docx":
            import docx2txt

            with tempfile.NamedTemporaryFile(suffix=".docx", delete=False) as tmp:
                tmp.write(raw_bytes)
                tmp_path = tmp.name
            try:
                text = docx2txt.process(tmp_path)
                text = (text or "").strip()
            finally:
                os.unlink(tmp_path)
            if not text:
                raise HTTPException(status_code=422, detail="DOCX 文件无法提取文本，请检查文件内容")
            print(f"[upload] DOCX 解析完成: {len(text)} 字符")
            return {"success": True, "text": text, "file_type": "docx", "filename": filename}

        # ── 图片 / 截屏（v4.4：DeepSeek 多模态视觉 Context 注入，彻底淘汰 EasyOCR）──
        if ext in (".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp"):
            from src.utils.visual_processor import parse_resume_image_via_vlm

            print(f"[upload] 启动 DeepSeek 多模态视觉解析: {filename} ({len(raw_bytes)} bytes)")
            text = await parse_resume_image_via_vlm(raw_bytes)
            text = (text or "").strip()
            if not text:
                raise HTTPException(status_code=422, detail="图片中未识别到文字内容，请确认图片包含清晰的简历或 JD 文字")
            print(f"[upload] DeepSeek 视觉解析完成: {len(text)} 字符")
            return {"success": True, "text": text, "file_type": "image", "filename": filename}

        # ── 不支持的类型 ──
        raise HTTPException(
            status_code=400,
            detail=f"不支持的文件类型 ({ext})，请上传 PDF、DOCX、TXT 或图片（PNG/JPG/WEBP/BMP）",
        )

    except HTTPException:
        raise
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"文件解析失败: {str(e)[:200]}")


# ── Agent 模式路由：LangGraph ReAct 中央大脑 SSE 流式端点 ──
app.include_router(agent_router)

if __name__ == "__main__":
    import uvicorn
    print("启动 AI-Resume-Evolver FastAPI 服务 v3.0 (双模拓扑 + MemorySaver)...")
    uvicorn.run(
        "main:app",
        host="127.0.0.1",       # v2.6: 死锁 127.0.0.1，根除 Windows 0.0.0.0 解析冲突
        port=8001,
        reload=False,
        log_level="info",
        timeout_keep_alive=300,  # 长连接保活 5 分钟（覆盖串行 LLM 调用的完整链路）
        timeout_graceful_shutdown=30,
    )
