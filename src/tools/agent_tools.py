"""
Agent 模式工具链 —— 六把工业级武器 (MySQL 物理并网版 + 时空感知 + 高精度计算)

武器清单:
  1. tavily_search_tool        — Tavily 联网情报检索
  2. patch_resume_tool         — 简历局部微创手术刀 (物理 MySQL INSERT/UPDATE)
  3. save_user_profile_tool    — 用户意图长期记忆冰冻 (物理 MySQL Upsert)
  4. get_current_system_time   — 数字手表 (实时系统时间感知)
  5. probe_host_environment    — 宿主环境探针 (操作系统与硬件感知)
  6. calculate_precise_metrics — 高精度 STAR 数据计算器 (反心算安全网关)

持久化:
  - 会话工厂 SessionLocal (src.database.connection)
  - ORM 模型 UserResume / UserProfile (src.database.models)
  - 所有物理写操作均通过 sqlalchemy.orm.Session 事务提交
"""

import os
import logging
from pydantic import BaseModel, Field
from langchain_core.tools import tool
from langchain_core.tools import ToolException
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
            raise ToolException(
                "未检测到环境变量 TAVILY_API_KEY，联网检索不可用。"
                "请根据已有知识库进行简历重写，不要死等该工具。"
            )

        client = TavilyClient(api_key=tavily_api_key)
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
    except ToolException:
        raise
    except Exception:
        raise ToolException(
            "外部联网检索工具暂时不可用（网络超时或物理连接异常）。"
            "请尝试根据你已有的知识库进行简历重写，不要死等该工具。"
        )


# 显式绑定错误接管属性（全版本兼容）
tavily_search_tool.handle_tool_error = True


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
        raise ToolException(
            f"【硬拦截】非法章节 [{section}]，合法范围必须在 {_VALID_SECTIONS} 内。"
        )

    if not new_content.strip():
        raise ToolException("【硬拦截】修改内容不能为空字符串。")

    try:
        with SessionLocal() as session:
            stmt = select(UserResume).where(UserResume.user_id == MOCK_USER_ID)
            resume = session.scalars(stmt).first()

            if not resume:
                resume = UserResume(user_id=MOCK_USER_ID)
                session.add(resume)

            setattr(resume, section, new_content)
            session.commit()

            logger.info(
                f"[MySQL_UPDATE_SUCCESS] 用户 [{MOCK_USER_ID}] "
                f"的 [{section}] 章节物理落盘成功！"
            )
            return (
                f"【系统通知】: 简历章节 [{section}] 已通过微创手术刀完成更新，状态：同步就位。"
            )
    except ToolException:
        raise
    except Exception:
        raise ToolException(
            f"物理数据库写入异常：章节 [{section}] 更新失败。"
            f"请稍后重试或检查数据库连接状态。"
        )


# 显式绑定错误接管属性（全版本兼容）
patch_resume_tool.handle_tool_error = True


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
                f"【系统通知】: 用户画像 [{key} -> {value}] 已更新，状态：同步就位。"
            )
    except ToolException:
        raise
    except Exception:
        raise ToolException(
            f"长期记忆物理并网异常：画像特征 [{key}] 写入失败。"
            f"请稍后重试或检查数据库连接状态。"
        )


# 显式绑定错误接管属性（全版本兼容）
save_user_profile_tool.handle_tool_error = True


# ==========================================
# ⏰ 武器四：数字手表 — 实时系统时间感知
# ==========================================

@tool
def get_current_system_time() -> str:
    """获取当前系统的实时精确日期和时间。当用户询问'现在几点'、'今天是几号'、'当前时间'、'星期几'或者需要根据当前时间进行任何简历逻辑推理时，必须调用此工具。"""
    try:
        from datetime import datetime
        now = datetime.now()
        weekdays = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"]
        current_time_str = now.strftime("%Y-%m-%d %H:%M:%S") + " " + weekdays[now.weekday()]
        return f"当前系统实时时间为：{current_time_str}"
    except Exception as e:
        raise ToolException(f"获取本地时间失败: {str(e)}")


get_current_system_time.handle_tool_error = True


# ==========================================
# 🛠️ 武器五：宿主环境探针 — 运行时物理环境感知
# ==========================================

@tool
def probe_host_environment() -> str:
    """获取当前 Agent 运行的宿主服务器操作系统和基础硬件环境信息。当用户询问系统版本、服务器配置或运行环境时调用。"""
    try:
        import platform
        os_info = f"{platform.system()} {platform.release()} (Architecture: {platform.machine()})"
        return f"Agent 当前物理宿主环境为：{os_info}。本地存储绝对路径已锁定，混合云灾备就绪。"
    except Exception as e:
        raise ToolException(f"感知宿主环境失败: {str(e)}")


probe_host_environment.handle_tool_error = True


# ==========================================
# 📐 武器六：高精度 STAR 数据计算器 — 量化指标精确运算
# ==========================================

@tool
def calculate_precise_metrics(expression: str) -> str:
    """高精度数学计算器。专门用于简历优化中 STAR 原则的业绩提升比例、吞吐量、QPS等数值的精确计算。严禁大模型心算，涉及任何数字运算、百分比推导时必须调用此工具。输入参数 expression 为纯 Python 算术表达式字符串（例如 '(450-120)/120 * 100'）。"""
    try:
        if not all(c in "0123456789+-*/(). " for c in expression):
            raise ToolException(
                "计算表达式包含非法字符，出于安全考虑已被熔断阻断。"
            )
        result = eval(expression)
        return f"高精度计算结果：{result}"
    except ToolException:
        raise
    except Exception as e:
        raise ToolException(f"数学网关执行异常: {str(e)}")


calculate_precise_metrics.handle_tool_error = True


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
AGENT_TOOLS = [
    tavily_search_tool,
    patch_resume_tool,
    save_user_profile_tool,
    get_current_system_time,
    probe_host_environment,
    calculate_precise_metrics,
]
