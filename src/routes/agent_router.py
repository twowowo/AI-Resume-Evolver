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

    # 1. 从 MySQL 捞出该用户的最新简历底座
    try:
        with SessionLocal() as session:
            stmt = select(UserResume).where(UserResume.user_id == payload.user_id)
            resume_record = session.scalars(stmt).first()
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

    # 3. SSE 生成器 — 流式挤出节点变更日志
    async def event_generator():
        try:
            yield ("data: " + json.dumps({
                "event": "START",
                "data": "中央大脑 ReAct 闭环拓扑点火成功..."
            }, ensure_ascii=False) + "\n\n")

            async for event in agent_compiled_graph.astream(initial_state, config):
                for node_name, node_output in event.items():
                    payload_data = {
                        "node_name": node_name,
                        "has_messages": "messages" in node_output,
                    }

                    if "messages" in node_output:
                        last_msg = node_output["messages"][-1]
                        payload_data["msg_type"] = type(last_msg).__name__

                        if hasattr(last_msg, "tool_calls") and last_msg.tool_calls:
                            payload_data["tool_calls"] = last_msg.tool_calls
                            payload_data["content"] = (
                                f"大脑决定触发 Function Calling: "
                                f"{last_msg.tool_calls[0]['name']}"
                            )
                        else:
                            content = last_msg.content
                            if isinstance(content, str):
                                payload_data["content"] = content[:800]
                            else:
                                payload_data["content"] = str(content)

                    yield ("data: " + json.dumps({
                        "event": "NODE_CHANGED",
                        "data": payload_data,
                    }, ensure_ascii=False) + "\n\n")
                    await asyncio.sleep(0.05)

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
