"""
Agent 模式工具链 —— 三把工业级武器 (MySQL 物理并网版)

武器清单:
  1. tavily_search_tool     — Tavily 联网情报检索
  2. patch_resume_tool      — 简历局部微创手术刀 (物理 MySQL INSERT/UPDATE)
  3. save_user_profile_tool — 用户意图长期记忆冰冻 (物理 MySQL Upsert)

持久化:
  - 会话工厂 SessionLocal (src.database.connection)
  - ORM 模型 UserResume / UserProfile (src.database.models)
  - 所有物理写操作均通过 sqlalchemy.orm.Session 事务提交
"""

import os
import logging
from pydantic import BaseModel, Field
from langchain_core.tools import tool
from tavily import TavilyClient
from sqlalchemy import select

# 导入物理数据库并网核心组件
from src.database.connection import SessionLocal
from src.database.models import UserResume, UserProfile

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("AgentTools")

_VALID_SECTIONS = ["basic", "skills", "projects", "campus"]

# 固定全局 mock 用户 ID（后续 4.0 端点中会从系统 Session 动态获取）
MOCK_USER_ID = "zhou_jiankai_001"


# ==========================================
# 🛡️ 武器一：Tavily 联网情报检索工具
# ==========================================

class TavilySearchInput(BaseModel):
    query: str = Field(
        ...,
        description=(
            "针对目标公司背景、技术栈、招聘黑话或特定行业名词进行联网搜索的精准查询词"
        ),
    )


@tool(args_schema=TavilySearchInput)
def tavily_search_tool(query: str) -> str:
    """
    当用户提到特定的公司名称、想了解该公司背景、团队文化、技术栈或行业最新黑话时，
    主动调用此工具进行全网实时情报检索。
    """
    try:
        tavily_api_key = os.getenv("TAVILY_API_KEY")
        if not tavily_api_key:
            return "错误：未检测到环境变量 TAVILY_API_KEY，联网检索失败。"

        client = TavilyClient(api_key=tavily_api_key)
        # 工业级上下文工程：控制 token 长度，防止长文本中间迷失
        response = client.search(query=query, max_results=2, include_raw_content=False)

        results = []
        for result in response.get("results", []):
            results.append(
                f"标题: {result['title']}\n内容: {result['content']}\n---"
            )

        return (
            "\n".join(results)
            if results
            else "全网搜索完成，但未找到相关强相关信息。"
        )
    except Exception as e:
        return f"工具执行期间发生物理崩溃: {str(e)}"


# ==========================================
# 🔪 武器二：简历局部微创手术刀工具 (MySQL 物理版)
# ==========================================

class PatchResumeInput(BaseModel):
    section: str = Field(
        ...,
        description=(
            "目标修改的简历章节，必须是以下枚举之一: "
            "'basic', 'skills', 'projects', 'campus'"
        ),
    )
    new_content: str = Field(
        ...,
        description=(
            "经过大模型根据用户意见重组、包装后的该章节完整 Markdown 文本"
        ),
    )


@tool(args_schema=PatchResumeInput)
def patch_resume_tool(section: str, new_content: str) -> str:
    """
    当用户明确发出指令，要求修改、润色、或补充简历的某个特定部分时调用。
    严禁重写整份简历！只对目标 section 实施微创手术替换。
    """
    if section not in _VALID_SECTIONS:
        return (
            f"【硬拦截】错误：非法章节 [{section}]。"
            f"合法范围必须在 {_VALID_SECTIONS} 内。"
        )

    if not new_content.strip():
        return "【硬拦截】错误：修改内容不能为空字符串。"

    try:
        # 开启物理数据库事务流
        with SessionLocal() as session:
            stmt = select(UserResume).where(UserResume.user_id == MOCK_USER_ID)
            resume = session.scalars(stmt).first()

            if not resume:
                # 没有该用户的简历底座 → 物理初始化一行
                resume = UserResume(user_id=MOCK_USER_ID)
                session.add(resume)

            # 动态微创定位更新对应的 Markdown 章节
            setattr(resume, section, new_content)
            session.commit()

            logger.info(
                f"[MySQL_UPDATE_SUCCESS] 用户 [{MOCK_USER_ID}] "
                f"的 [{section}] 章节物理落盘成功！"
            )
            return (
                f"【系统通知】: 简历章节 [{section}] 已经过高精度物理手术刀落盘替换成功。"
            )
    except Exception as e:
        return f"物理数据库写入崩溃: {str(e)}"


# ==========================================
# 🧊 武器三：用户意图与长期记忆冰冻工具 (MySQL Upsert 版)
# ==========================================

class SaveProfileInput(BaseModel):
    key: str = Field(
        ...,
        description=(
            "记忆的特征标签，例如 'target_company', "
            "'preferred_tech_stack', 'career_objective'"
        ),
    )
    value: str = Field(
        ...,
        description=(
            "从对话中提炼出的核心记忆事实，例如 '字节跳动大模型团队', "
            "'重度使用Go与LangGraph'"
        ),
    )


@tool(args_schema=SaveProfileInput)
def save_user_profile_tool(key: str, value: str) -> str:
    """
    在多轮拉锯聊天中，当大模型敏锐地捕捉到用户的核心求职倾向、心仪大厂、
    或者个人不经意间吐露出的关键高光技术栈时，
    主动调用此工具将核心画像特征冰冻沉淀。
    """
    try:
        with SessionLocal() as session:
            # 大厂级幂等 Upsert 逻辑：先查后插/改
            stmt = select(UserProfile).where(
                UserProfile.user_id == MOCK_USER_ID,
                UserProfile.profile_key == key,
            )
            profile = session.scalars(stmt).first()

            if profile:
                profile.profile_value = value
            else:
                profile = UserProfile(
                    user_id=MOCK_USER_ID, profile_key=key, profile_value=value
                )
                session.add(profile)

            session.commit()
            logger.info(
                f"[MySQL_UPSERT_SUCCESS] 画像特征 [{key} -> {value}] "
                f"成功并网用户长期记忆库！"
            )
            return (
                f"【系统通知】: 成功提取用户长期记忆快照 [{key} -> {value}]，"
                f"已安全异步冷冻至物理资产库。"
            )
    except Exception as e:
        return f"长期记忆物理并网崩溃: {str(e)}"


def get_user_profile() -> dict[str, str]:
    """获取当前用户的物理记忆字典，用于控制台及调试审计。"""
    try:
        with SessionLocal() as session:
            stmt = select(UserProfile).where(UserProfile.user_id == MOCK_USER_ID)
            profiles = session.scalars(stmt).all()
            return {p.profile_key: p.profile_value for p in profiles}
    except Exception:
        return {}


def clear_user_profile() -> None:
    """一键清空该用户的物理画像长期记忆。"""
    try:
        with SessionLocal() as session:
            stmt = select(UserProfile).where(UserProfile.user_id == MOCK_USER_ID)
            profiles = session.scalars(stmt).all()
            for p in profiles:
                session.delete(p)
            session.commit()
            logger.info(
                f"[MySQL_DELETE_SUCCESS] 用户 [{MOCK_USER_ID}] "
                f"的物理长期记忆库执行了彻底擦除"
            )
    except Exception as e:
        logger.error(f"清空长期记忆物理故障: {str(e)}")


# ── 工具清单导出（供 graph.py / run_app.py 通过 ToolNode 直接绑定）──
AGENT_TOOLS = [tavily_search_tool, patch_resume_tool, save_user_profile_tool]
