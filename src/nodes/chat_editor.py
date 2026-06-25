"""
v3.0 Chat Editor 节点 —— 交互模式增量编辑 + XML 物理隔离

核心逻辑:
  - 接收用户在多轮对话中输入的补充信息 (user_supplement)
  - 将其优雅、专业地融入当前简历半成品
  - <clean_resume>...</clean_resume> 物理隔离，A4 纸渲染专用
  - 严禁篡改无关章节，锁定原有排版逻辑
"""

import os
import re
from src.state import AgentState
from src.utils.llm import get_flash_client, get_pro_client

_CLEAN_RESUME_RE = re.compile(
    r"<clean_resume>\s*([\s\S]*?)\s*</clean_resume>",
    re.IGNORECASE,
)

CHAT_EDITOR_SYSTEM_PROMPT = """你是一位精通大模型工程化与简历重构的首席全栈专家。
现在，用户正在针对当前的简历半成品提出进一步的修改意见或信息补充。

【历史会话断点备忘录】
{conversation_summary}

【目标岗位 JD】
{jd}

【当前的精修简历半成品】
{current_resume}

{instruction_block}

【硬核执行铁律】
1. 增量修改：请紧扣用户补充信息，将其优雅、专业地融入到简历对应章节中。
2. 保持稳定：严禁篡改无关章节，锁定原本的 A4 排版逻辑。已有的优质 STAR 描述不得降级。
3. 物理隔离：必须将最终 Markdown 简历放置在 <clean_resume>...</clean_resume> 标签内。
4. 三竖线拦截：任何新增或修改的经历头部，必须严格遵循 `时间段 | 机构名称 | 身份` 的格式。
5. 量化优先：所有补充的新经历，必须包含可量化的指标或成果数据，严禁空洞描述。
6. 全量输出 + 空模块跳过：输出完整简历全文，但若某模块完全没有实质内容（正文为空或仅"无/暂无"字样），直接跳过该模块，不输出标题和占位文本。
7. 断点续传：请优先参考【历史会话断点备忘录】中的雷区限制与分数轨迹，避免重复踩坑。
8. 【绝对输出禁语令】绝对禁止在输出中附带任何形式的寒暄问候（"好的"、"以下是"、"希望这份简历能帮到您"、祝福语）、Markdown 代码块包裹（``` 标记）、角色扮演评论、署名结语。只输出 <clean_resume> 标签包裹的纯净简历正文。
"""

CHAT_EDITOR_REFINE_PROMPT = """你是一位精通大模型工程化与简历重构的首席全栈专家。
评审团刚刚对当前简历给出了评分和反馈，你需要根据反馈进行针对性打磨。

【历史会话断点备忘录】
{conversation_summary}

【目标岗位 JD】
{jd}

【当前的精修简历半成品】
{current_resume}

【评审团反馈】
{feedback}

【硬核执行铁律】
1. 精准打磨：仅针对评审团反馈中指出的问题进行修改，其他章节保持原样。
2. 物理隔离：必须将最终 Markdown 简历放置在 <clean_resume>...</clean_resume> 标签内。
3. 三竖线拦截：任何修改的经历头部，必须严格遵循 `时间段 | 机构名称 | 身份` 的格式。
4. 全量输出 + 空模块跳过：输出完整简历全文，但若某模块完全没有实质内容（正文为空或仅"无/暂无"字样），直接跳过该模块，不输出标题和占位文本。
5. 断点续传：请优先参考【历史会话断点备忘录】中的雷区限制与分数轨迹，避免重复踩坑。
6. 【绝对输出禁语令】绝对禁止在输出中附带任何形式的寒暄问候、Markdown 代码块包裹（``` 标记）、角色扮演评论、署名结语。只输出 <clean_resume> 标签包裹的纯净简历正文。
"""


def chat_editor_node(state: AgentState) -> dict:
    """v4.5 交互模式增量编辑节点 —— 将用户补充信息融入简历半成品，或基于评审反馈自 refine

    新增: conversation_summary 注入，使编辑器具备跨轮次断点续传能力
    """
    current_resume = state.get("revised_resume") or state.get("resume") or ""
    user_input = state.get("user_supplement") or ""
    jd = state.get("jd") or ""
    eval_feedback = state.get("evaluation_feedback") or ""
    conversation_summary = state.get("conversation_summary") or "（首次编辑，暂无历史断点）"

    # ── v7.0 跨管道上下文桥接：如果自己的 checkpoint 没有备忘录，去 MySQL 读管道D 留下的 ──
    if conversation_summary == "（首次编辑，暂无历史断点）":
        user_id = state.get("user_id") or ""
        resume_id = state.get("resume_id") or ""
        if user_id and resume_id:
            try:
                from src.database.connection import get_session
                from src.database.models import UserSession
                from sqlalchemy import select
                with get_session() as s:
                    stmt = select(UserSession).where(
                        UserSession.user_id == user_id,
                        UserSession.resume_id == resume_id,
                    )
                    row = s.scalars(stmt).first()
                    if row and row.conversation_summary:
                        conversation_summary = (
                            "【跨管道断点备忘录 —— Agent 模式遗留的会话总结】\n"
                            + row.conversation_summary
                        )
                        print(f"[chat_editor] 跨管道桥接: 已加载管道D备忘录, "
                              f"user={user_id}, resume={resume_id}, "
                              f"{len(row.conversation_summary)} 字符")
            except Exception as e:
                print(f"[chat_editor] 跨管道桥接读取失败 (非致命): {e}")

    # ── 无任何输入 → 直接通过 ──
    if not user_input.strip() and not eval_feedback.strip():
        return {
            "node_status": "当前无需编辑，已保持简历不变。",
            "turn_count": state.get("turn_count", 0),
        }

    if not current_resume.strip():
        return {
            "node_status": "当前无可编辑简历，请先执行一键优化生成初稿。",
            "turn_count": state.get("turn_count", 0),
        }

    # ── 构建 prompt: 有用户输入走增量编辑，否则走反馈 refine ──
    if user_input.strip():
        instruction_block = f'【用户刚刚输入的补充信息/修改意见】\n👉 "{user_input}"'
        prompt = CHAT_EDITOR_SYSTEM_PROMPT.format(
            conversation_summary=conversation_summary,
            jd=jd,
            current_resume=current_resume,
            instruction_block=instruction_block,
        )
        mode_label = "增量编辑"
    else:
        prompt = CHAT_EDITOR_REFINE_PROMPT.format(
            conversation_summary=conversation_summary,
            jd=jd,
            current_resume=current_resume,
            feedback=eval_feedback,
        )
        mode_label = "反馈 refine"

    print(f"[chat_editor] {mode_label}: user_input={len(user_input)} 字符, "
          f"feedback={len(eval_feedback)} 字符, resume={len(current_resume)} 字符")

    try:
        use_pro = os.getenv("USE_PRO_MODEL", "false").lower() == "true"
        model_label = "DeepSeek-V4-Pro" if use_pro else "DeepSeek-V4-Flash"
        print(f"[chat_editor] 调用 {model_label} ({mode_label})...")
        llm = get_pro_client() if use_pro else get_flash_client()
        response = llm.invoke(prompt)
        response_text = response.content if hasattr(response, "content") else str(response)
        response_text = response_text.strip()
    except Exception as e:
        print(f"[chat_editor] LLM 调用失败: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        return {
            "revised_resume": current_resume,
            "node_status": f"模型调用异常 ({type(e).__name__})，已回退当前简历。",
            "chat_history": (state.get("chat_history") or [] + [
                {"role": "user", "content": user_input},
                {"role": "assistant", "content": f"编辑引擎暂时过热，已保留上一版本。错误: {type(e).__name__}"},
            ]) if user_input.strip() else state.get("chat_history") or [],
            "turn_count": (state.get("turn_count") or 0) + 1,
            "user_supplement": "",  # 清除已处理的输入
        }

    match = _CLEAN_RESUME_RE.search(response_text)
    if match:
        updated_resume = match.group(1).strip()
        print(f"[chat_editor] 成功提取 <clean_resume>, 输出 {len(updated_resume)} 字符")
    else:
        updated_resume = current_resume
        print(f"[chat_editor] 未找到 <clean_resume> 标签, 回退为当前简历 "
              f"(响应前200字符: {response_text[:200]})")

    # ── 仅在有用户输入时追加对话历史 ──
    existing_history = state.get("chat_history") or []
    if user_input.strip():
        existing_history = existing_history + [
            {"role": "user", "content": user_input},
            {"role": "assistant", "content": f"已根据您的要求完成增量编辑。"
                                             f"简历从 {len(current_resume)} 字符调整为 {len(updated_resume)} 字符。"},
        ]

    return {
        "revised_resume": updated_resume,
        "node_status": f"A4 画布重组完毕 ({mode_label})，正在移交评委进行二次指标准确度打分...",
        "chat_history": existing_history,
        "turn_count": state.get("turn_count", 0) + 1,
        "user_supplement": "",  # 清除已处理的输入，防止回环时重复消费
    }
