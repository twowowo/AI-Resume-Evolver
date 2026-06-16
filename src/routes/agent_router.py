"""
Agent 模式 SSE 流式长连接端点 — LangGraph ReAct 大脑对外暴露路由
v4.2 三层漏斗隔离沙箱：user_id + resume_id 动态复合钥匙
v4.3 后台异步影子审计：Ragas Faithfulness + Answer Relevance 零延迟评估

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
from langchain_core.messages import HumanMessage, AIMessage, ToolMessage
from sqlalchemy import select

from src.graphs.agent_graph import agent_compiled_graph
from src.database.connection import SessionLocal
from src.database.models import UserResume
from src.utils.llm import get_flash_client

logger = logging.getLogger("AgentRouter")
logging.basicConfig(level=logging.INFO)

# ── v4.1 全局专用线程池：物理抽离同步 DB I/O，释放 FastAPI 单线程事件循环十万并发带宽 ──
db_executor = ThreadPoolExecutor(max_workers=10)

router = APIRouter(prefix="/api/agent", tags=["AI Agent 中央大脑"])


class AgentPayload(BaseModel):
    """v4.2 三层漏斗隔离沙箱请求体 —— user_id + resume_id 动态复合钥匙"""
    user_query: str
    user_id: str = "default_user"
    resume_id: str = "default_resume"


# ═══════════════════════════════════════════════════════════════
# v4.3 Ragas 影子审计：裁判 System Prompt
# ═══════════════════════════════════════════════════════════════

_RAGAS_JUDGE_SYSTEM = """你是一个严格的 Ragas 评估裁判。你的任务是根据提供的上下文，评估 AI 助手回答的质量。

你需要评估两个维度并给出 0-1 之间的分数：

## 1. 忠实度（Faithfulness）
检查 AI 回答中的每一个事实断言是否都能在【提供的上下文】中找到明确依据。
- 如果有任何编造、幻觉或无法从上下文验证的陈述 → 严格扣分
- 如果回答中包含上下文中完全没有提及的数据、人名、技术细节 → 大幅扣分
- 满分条件：回答中所有断言 100% 可在上下文中逐条对账

## 2. 回答相关性（Answer Relevance）
检查 AI 回答是否直接、完整、精确地回应用户的问题。
- 如果回答偏离主题、答非所问 → 严格扣分
- 如果回答遗漏了用户问题中的关键诉求 → 扣分
- 如果回答包含大量与问题无关的冗余信息 → 扣分
- 满分条件：回答精准命中问题的每一个核心诉求，无冗余无遗漏

你必须严格返回 JSON 格式，不要包含任何其他文字、解释或 markdown 代码块标记：
{"faithfulness_score": <0到1的浮点数>, "faithfulness_reason": "<扣分原因，满分则写：所有断言均有上下文支撑>", "answer_relevance_score": <0到1的浮点数>, "answer_relevance_reason": "<扣分原因，满分则写：完美响应了用户问题>"}"""


async def _run_ragas_shadow_eval(
    query: str,
    contexts: list[str],
    output: str,
    user_id: str,
    resume_id: str,
    step_count: int,
    total_tokens: int,
) -> None:
    """
    v4.3 后台异步影子审计 —— 流式传输完全结束后以 asyncio.create_task 点火，
    对用户前台延迟贡献为 0ms。

    使用 DeepSeek 作为裁判大模型（temperature=0.1），评估：
      - 忠实度（Faithfulness）：Output 是否 100% 来源于 Context
      - 回答相关性（Answer Relevance）：Output 是否完美契合 Query

    结果通过 Uvicorn 日志输出，不做任何前台阻塞。
    """
    try:
        # ── 构建评估上下文 ──
        ctx_text = "\n---\n".join(
            f"[上下文片段 {i+1}] {c[:500]}" for i, c in enumerate(contexts)
        ) if contexts else "(本次对话未检索外部上下文，回答基于模型自身知识)"

        output_snapshot = output[:3000]  # 截断防爆

        judge_input = f"""## 用户问题
{query}

## 提供的上下文
{ctx_text}

## AI 助手的回答
{output_snapshot}"""

        # ── 调用裁判模型（flash 默认 temperature=0.1，低随机性适合评估）──
        judge_llm = get_flash_client()
        judge_response = judge_llm.invoke([
            {"role": "system", "content": _RAGAS_JUDGE_SYSTEM},
            {"role": "user", "content": judge_input},
        ])

        raw = judge_response.content if hasattr(judge_response, "content") else str(judge_response)
        raw = raw.strip()

        # ── 解析裁判 JSON（防御非标输出）──
        # 尝试提取 JSON 块（处理模型可能包裹 ```json ... ``` 的情况）
        if "```json" in raw:
            raw = raw.split("```json")[1].split("```")[0].strip()
        elif "```" in raw:
            raw = raw.split("```")[1].split("```")[0].strip()

        result = json.loads(raw)
        f_score = float(result.get("faithfulness_score", 0))
        r_score = float(result.get("answer_relevance_score", 0))
        f_reason = result.get("faithfulness_reason", "N/A")
        r_reason = result.get("answer_relevance_reason", "N/A")

        # ── v4.6 静默日志模式：审计结果仅写入 INFO 级别，不触发 WARNING ──
        logger.info(
            f"[Ragas 影子审计] 用户: {user_id} | "
            f"忠实度: {f_score:.2f} | 相关性: {r_score:.2f} | "
            f"迭代步数: {step_count} | Token: {total_tokens} | "
            f"忠实度备注: {f_reason[:80]} | 相关性备注: {r_reason[:80]}"
        )

    except json.JSONDecodeError as e:
        logger.error(f"[Ragas 影子审计失败] JSON 解析异常: {e} | 原始输出: {raw[:200]}")
    except Exception as e:
        logger.error(f"[Ragas 影子审计失败] 评估管线异常: {type(e).__name__}: {str(e)[:200]}")


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
async def stream_agent_brain(payload: AgentPayload):
    """工业级 SSE 长连接流式端点 —— 将 LangGraph ReAct 环路逐帧催化至前端。

    v4.2 三层漏斗隔离沙箱：
      Layer 1: thread_id = f"{user_id}::{resume_id}" → MemorySaver 内存沙箱
      Layer 2: ChromaDB where 元数据硬过滤 → 向量检索隔离
      Layer 3: MySQL 按 user_id 捞取专属简历底座

    v4.3 后台异步影子审计：
      流结束后 asyncio.create_task(_run_ragas_shadow_eval) 点火，
      前台延迟增加 0ms。评估忠实度 + 回答相关性并输出审计日志。
    """

    # ── v4.2 Layer 3: 动态复合钥匙 ──
    thread_id = f"{payload.user_id}::{payload.resume_id}"
    logger.info(f"[记忆沙箱点火] 线程已锁定: {thread_id}")

    # 1. 异步隔离：从 MySQL 捞出该用户的最新简历底座（线程池抽离同步阻塞）
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

    logger.info(f"[AgentSSE] 用户 [{payload.user_id}] 简历 [{payload.resume_id}] 发起请求, "
                f"query={len(payload.user_query)} 字符, resume={len(current_resume_md)} 字符")

    # 2. 初始化 LangGraph 状态机快照（注入沙箱身份标识 + 提效计数器）
    initial_state = {
        "messages": [HumanMessage(content=payload.user_query)],
        "current_resume_markdown": current_resume_md,
        "user_id": payload.user_id,
        "resume_id": payload.resume_id,
        "step_count": 0,
        "total_tokens": 0,
    }

    config = {"configurable": {"thread_id": thread_id}}

    # 3. SSE 生成器 — 流式挤出节点变更日志（内嵌 v4.3 影子审计数据收集）
    async def event_generator():
        # ── v4.1 双重栅栏防爆熔断器 ──
        total_streamed_chars = 0
        tool_call_count = 0
        MAX_CHARS = 12_000
        MAX_TOOL_CALLS = 20
        circuit_breached = False

        # ── v4.3 影子审计数据收集缓冲区 ──
        step_count = 0
        collected_outputs: list[str] = []
        collected_contexts: list[str] = []

        try:
            yield ("data: " + json.dumps({
                "event": "START",
                "data": f"中央大脑 ReAct 闭环拓扑点火成功... [沙箱: {thread_id}]"
            }, ensure_ascii=False) + "\n\n")

            async for event in agent_compiled_graph.astream(initial_state, config):
                if circuit_breached:
                    break

                for node_name, node_output in event.items():
                    # ── v4.3: 每个节点完成 → 步数累加 ──
                    step_count += 1

                    payload_data = {
                        "node_name": node_name,
                        "has_messages": "messages" in node_output,
                    }

                    if "messages" in node_output:
                        last_msg = node_output["messages"][-1]
                        msg_type = type(last_msg).__name__
                        payload_data["msg_type"] = msg_type

                        if hasattr(last_msg, "tool_calls") and last_msg.tool_calls:
                            tool_call_count += 1
                            # ── v4.5 脱敏：Tool 调用详情写入服务器日志，前端仅收精简业务帧 ──
                            tc_names = [tc["name"] for tc in last_msg.tool_calls]
                            logger.info(
                                f"[Agent Tool Call] 沙箱 [{thread_id}] 触发工具: {tc_names}, "
                                f"参数摘要: {[(tc['name'], {k: str(v)[:80] for k, v in tc.get('args', {}).items()}) for tc in last_msg.tool_calls]}"
                            )
                            # 前端仍保留 tool_calls 结构（AgentCanvas 需要 patch_resume_tool 数据）
                            payload_data["tool_calls"] = last_msg.tool_calls
                            payload_data["content"] = ""
                            # 不累加字符计数（工具调用帧不占前端带宽）
                        else:
                            content = last_msg.content
                            if isinstance(content, str):
                                # ── v4.5 脱敏：ToolMessage 仅写日志，不下发前端 ──
                                if msg_type == "ToolMessage":
                                    logger.info(
                                        f"[Agent Tool Result] 沙箱 [{thread_id}] "
                                        f"工具回执: {content[:200]}..."
                                    )
                                    payload_data["content"] = ""
                                    collected_contexts.append(content)
                                else:
                                    payload_data["content"] = content
                                    total_streamed_chars += len(content)
                                    if msg_type == "AIMessage":
                                        collected_outputs.append(content)
                            else:
                                payload_data["content"] = str(content)
                                total_streamed_chars += len(str(content))

                    yield ("data: " + json.dumps({
                        "event": "NODE_CHANGED",
                        "data": payload_data,
                    }, ensure_ascii=False) + "\n\n")
                    await asyncio.sleep(0.05)

                    # ── v4.1 双重栅栏防爆 ──
                    if total_streamed_chars > MAX_CHARS or tool_call_count > MAX_TOOL_CALLS:
                        logger.warning(
                            f"[CIRCUIT BREAKER Triggered] Chars: {total_streamed_chars}, "
                            f"ToolCalls: {tool_call_count}"
                        )
                        circuit_breached = True
                        break

                if circuit_breached:
                    break

            # ── 熔断通知帧 ──
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

            # ── 流结束帧 ──
            yield ("data: " + json.dumps({
                "event": "END",
                "data": f"拓扑环路平滑收敛，最新数据已安全冷冻落盘 MySQL。[沙箱: {thread_id}]",
            }, ensure_ascii=False) + "\n\n")

            # ═══════════════════════════════════════════════════════
            # v4.3 后台异步影子审计：流结束后零延迟点火
            # 前台 SSE 已全部发送完毕，此任务不增加任何用户等待时间
            # ═══════════════════════════════════════════════════════
            final_output = "\n".join(collected_outputs[-5:]) if collected_outputs else "(无输出)"
            estimated_tokens = int(total_streamed_chars * 0.6)

            asyncio.create_task(
                _run_ragas_shadow_eval(
                    query=payload.user_query,
                    contexts=collected_contexts[-8:],
                    output=final_output,
                    user_id=payload.user_id,
                    resume_id=payload.resume_id,
                    step_count=step_count,
                    total_tokens=estimated_tokens,
                )
            )
            logger.info(
                f"[影子审计点火] 沙箱 [{thread_id}] 后台评估任务已入队，"
                f"步数={step_count}, Token≈{estimated_tokens}"
            )

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
