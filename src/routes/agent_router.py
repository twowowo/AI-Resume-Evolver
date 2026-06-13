"""
Agent 模式 SSE 流式长连接端点 — LangGraph ReAct 大脑对外暴露路由

端点:
  POST /api/agent/stream  — SSE 流式推送 ReAct 环路节点变更日志

物理依赖:
  - agent_compiled_graph (src.graphs.agent_graph) — 已编译的大脑图单例
  - SessionLocal (src.database.connection) — MySQL 同步会话工厂
  - UserResume (src.database.models) — 简历底座物理表
"""

import json
import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from langchain_core.messages import HumanMessage
from sqlalchemy import select

from src.graphs.agent_graph import agent_compiled_graph
from src.database.connection import SessionLocal
from src.database.models import UserResume

logger = logging.getLogger("AgentRouter")
logging.basicConfig(level=logging.INFO)

# ── v4.1 全局专用线程池：物理抽离同步 DB I/O，释放 FastAPI 单线程事件循环十万并发带宽 ──
db_executor = ThreadPoolExecutor(max_workers=10)

router = APIRouter(prefix="/api/agent", tags=["AI Agent 中央大脑"])


class AgentChatInput(BaseModel):
    user_query: str
    user_id: str = "zhou_jiankai_001"


def _build_resume_base(resume_record) -> str:
    """将 UserResume 四个章节拼装为完整 Markdown 底座，供 System Prompt 注入。"""
    if resume_record is None:
        return "# 原始简历底座\n## 校园经历\n- 暂无数据"

    parts: list[str] = []
    section_map = {
        "basic": "## 个人基础信息",
        "skills": "## 核心技术栈",
        "projects": "## 项目经历",
        "campus": "## 校园经历",
    }
    for field, heading in section_map.items():
        content = getattr(resume_record, field, None)
        if content and content.strip():
            parts.append(f"{heading}\n{content.strip()}")

    if not parts:
        return "# 原始简历底座\n## 校园经历\n- 暂无数据"

    return "# 原始简历底座\n\n" + "\n\n".join(parts)


@router.post("/stream")
async def stream_agent_brain(payload: AgentChatInput):
    """工业级 SSE 长连接流式端点 —— 将 LangGraph ReAct 环路逐帧催化至前端。"""

    # 1. v4.1 异步隔离：从 MySQL 捞出该用户的最新简历底座（线程池抽离同步阻塞）
    def _fetch_resume_sync(user_id: str):
        with SessionLocal() as session:
            stmt = select(UserResume).where(UserResume.user_id == user_id)
            return session.scalars(stmt).first()

    try:
        resume_record = await asyncio.get_event_loop().run_in_executor(
            db_executor, _fetch_resume_sync, payload.user_id
        )
        current_resume_md = _build_resume_base(resume_record)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"物理存储底座读取故障: {str(e)}")

    logger.info(f"[AgentSSE] 用户 [{payload.user_id}] 发起请求, "
                f"query={len(payload.user_query)} 字符, resume={len(current_resume_md)} 字符")

    # 2. 初始化 LangGraph 状态机快照
    initial_state = {
        "messages": [HumanMessage(content=payload.user_query)],
        "current_resume_markdown": current_resume_md,
    }

    config = {"configurable": {"thread_id": f"sse_session_{payload.user_id}"}}

    # 3. SSE 生成器 — 流式挤出节点变更日志（内嵌流式安全熔断器）
    async def event_generator():
        # ── v4.1 双重栅栏防爆熔断器：字符计数 + 工具调用次数并联 ──
        total_streamed_chars = 0
        tool_call_count = 0
        MAX_CHARS = 12_000
        MAX_TOOL_CALLS = 20
        circuit_breached = False

        try:
            yield ("data: " + json.dumps({
                "event": "START",
                "data": "中央大脑 ReAct 闭环拓扑点火成功..."
            }, ensure_ascii=False) + "\n\n")

            async for event in agent_compiled_graph.astream(initial_state, config):
                if circuit_breached:
                    break

                for node_name, node_output in event.items():
                    payload_data = {
                        "node_name": node_name,
                        "has_messages": "messages" in node_output,
                    }

                    if "messages" in node_output:
                        last_msg = node_output["messages"][-1]
                        payload_data["msg_type"] = type(last_msg).__name__

                        if hasattr(last_msg, "tool_calls") and last_msg.tool_calls:
                            tool_call_count += 1
                            payload_data["tool_calls"] = last_msg.tool_calls
                            payload_data["content"] = (
                                f"大脑决定触发 Function Calling: "
                                f"{last_msg.tool_calls[0]['name']}"
                            )
                        else:
                            content = last_msg.content
                            if isinstance(content, str):
                                payload_data["content"] = content
                                # ── 流式字符计数累加 ──
                                total_streamed_chars += len(content)
                            else:
                                payload_data["content"] = str(content)
                                total_streamed_chars += len(str(content))

                    yield ("data: " + json.dumps({
                        "event": "NODE_CHANGED",
                        "data": payload_data,
                    }, ensure_ascii=False) + "\n\n")
                    await asyncio.sleep(0.05)

                    # ── v4.1 双重栅栏防爆：字符数或工具调用次数任一防线被击穿，立刻物理熔断降级 ──
                    if total_streamed_chars > MAX_CHARS or tool_call_count > MAX_TOOL_CALLS:
                        logger.warning(
                            f"[CIRCUIT BREAKER Triggered] Chars: {total_streamed_chars}, ToolCalls: {tool_call_count}"
                        )
                        circuit_breached = True
                        break

                if circuit_breached:
                    break

            if circuit_breached:
                breach_reason = ""
                if total_streamed_chars > MAX_CHARS and tool_call_count > MAX_TOOL_CALLS:
                    breach_reason = (
                        f"双防线同时击穿！字符累计 {total_streamed_chars}/{MAX_CHARS} + "
                        f"工具调用 {tool_call_count}/{MAX_TOOL_CALLS}"
                    )
                elif total_streamed_chars > MAX_CHARS:
                    breach_reason = (
                        f"字符洪峰防线击穿！累计 {total_streamed_chars}/{MAX_CHARS}"
                    )
                else:
                    breach_reason = (
                        f"工具调用狂潮防线击穿！累计 {tool_call_count}/{MAX_TOOL_CALLS}"
                    )
                yield ("data: " + json.dumps({
                    "event": "NODE_CHANGED",
                    "data": {
                        "node_name": "circuit_breaker",
                        "msg_type": "SystemNotification",
                        "content": (
                            f"\n\n⚠️ [SYSTEM NOTIFICATION: TRIGGERED DUAL-GATE "
                            f"CIRCUIT BREAKER]\n\n"
                            f"{breach_reason}\n"
                            "流式管道已主动熔断，防止模型幻觉死循环无限喷射。"
                            "\n请精简提问或分步执行。"
                        ),
                    },
                }, ensure_ascii=False) + "\n\n")

            yield ("data: " + json.dumps({
                "event": "END",
                "data": "拓扑环路平滑收敛，最新数据已安全冷冻落盘 MySQL。",
            }, ensure_ascii=False) + "\n\n")

        except Exception as e:
            logger.error(f"[AgentSSE] 运行时异常: {str(e)}")
            yield ("data: " + json.dumps({
                "event": "ERROR",
                "data": f"运行时大脑炸裂: {str(e)}",
            }, ensure_ascii=False) + "\n\n")

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
