"""
agent_tools.py 工业级孤立单元验证

验证范围:
  1. patch_resume_tool  — section 枚举硬拦截 + 合法路径
  2. save_user_profile_tool — 内存画像句柄字典状态变更
  3. tavily_search_tool — 真实联网调用（若 TAVILY_API_KEY 存在）/ 优雅跳过
"""

import os
import sys
import pytest

# 确保项目根目录在 sys.path 中
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _PROJECT_ROOT)

# 加载 .env 注入 API Keys（对齐 main.py 启动逻辑）
from dotenv import load_dotenv
load_dotenv(dotenv_path=os.path.join(_PROJECT_ROOT, ".env"))

from src.tools.agent_tools import (
    patch_resume_tool,
    save_user_profile_tool,
    tavily_search_tool,
    clear_user_profile,
    get_user_profile,
    _VALID_SECTIONS,
)


# ═══════════════════════════════════════
# 夹具
# ═══════════════════════════════════════

@pytest.fixture(autouse=True)
def _reset_memory():
    """每个测试用例执行前清空内存画像，保证隔离性。"""
    clear_user_profile()
    yield
    clear_user_profile()


# ═══════════════════════════════════════
# 🔪 武器二：patch_resume_tool
# ═══════════════════════════════════════

class TestPatchResumeTool:
    """简历局部微创手术刀 —— 枚举硬拦截 + 合法替换"""

    INVALID_INPUTS = [
        "cheating",
        "hobby",
        "random",
        "",
        "BASIC",
        "Skills",
    ]

    @pytest.mark.parametrize("bad_section", INVALID_INPUTS)
    def test_invalid_section_rejected_hard(self, bad_section):
        """非法章节 100% 被 _VALID_SECTIONS 拦截，响应体以 '错误' 开头。"""
        result = patch_resume_tool.invoke({
            "section": bad_section,
            "new_content": "任意伪造内容",
        })

        assert isinstance(result, str), f"返回类型应为 str，实际为 {type(result)}"
        assert result.startswith("【硬拦截】"), (
            f"非法章节 [{bad_section}] 未被拦截！返回: {result[:80]}..."
        )
        assert any(sec in result for sec in _VALID_SECTIONS), (
            f"拦截信息应包含合法枚举值，实际: {result[:80]}..."
        )

    @pytest.mark.parametrize("valid_section", list(_VALID_SECTIONS))
    def test_valid_section_accepted(self, valid_section):
        """四个合法章节均返回成功签名。"""
        result = patch_resume_tool.invoke({
            "section": valid_section,
            "new_content": f"## {valid_section}\n\n合法内容",
        })

        assert isinstance(result, str)
        assert result.startswith("【系统通知】"), (
            f"合法章节 [{valid_section}] 响应异常: {result[:80]}..."
        )
        assert valid_section in result, (
            f"响应应包含章节名 [{valid_section}]，实际: {result[:80]}..."
        )

    def test_missing_field_raises(self):
        """缺少必填字段 section → pydantic ValidationError。"""
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            patch_resume_tool.invoke({"new_content": "没有 section"})


# ═══════════════════════════════════════
# 🧊 武器三：save_user_profile_tool
# ═══════════════════════════════════════

class TestSaveUserProfileTool:
    """用户画像冰冻 —— 内存句柄沉淀 + get/clear 全链路"""

    def test_single_key_value_persisted(self):
        """单键写入 → get_user_profile() 精确匹配。"""
        result = save_user_profile_tool.invoke({
            "key": "target_company",
            "value": "字节跳动大模型团队",
        })

        assert result.startswith("【系统通知】")
        assert "target_company" in result
        assert "字节跳动大模型团队" in result

        profile = get_user_profile()
        assert profile == {"target_company": "字节跳动大模型团队"}

    def test_multi_key_accumulates(self):
        """连续写入多条 → 字典累加不覆盖。"""
        pairs = {
            "target_company": "阿里巴巴",
            "preferred_tech_stack": "Go + LangGraph + Kubernetes",
            "career_objective": "后端架构师 (P7+)",
        }

        for k, v in pairs.items():
            result = save_user_profile_tool.invoke({"key": k, "value": v})
            assert result.startswith("【系统通知】")

        profile = get_user_profile()
        assert profile == pairs
        assert len(profile) == 3

    def test_overwrite_existing_key(self):
        """重复键覆写：后写入的值覆盖前者。"""
        save_user_profile_tool.invoke({
            "key": "target_company",
            "value": "腾讯",
        })
        save_user_profile_tool.invoke({
            "key": "target_company",
            "value": "华为",
        })

        profile = get_user_profile()
        assert profile == {"target_company": "华为"}
        assert len(profile) == 1

    def test_clear_resets_store(self):
        """clear_user_profile() 彻底清空物理画像。"""
        save_user_profile_tool.invoke({
            "key": "target_company",
            "value": "字节跳动",
        })
        before = get_user_profile()
        assert len(before) == 1

        clear_user_profile()
        after = get_user_profile()
        assert after == {}

    def test_missing_key_raises(self):
        """缺少 key → pydantic ValidationError。"""
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            save_user_profile_tool.invoke({"value": "没有 key"})


# ═══════════════════════════════════════
# 🛡️ 武器一：tavily_search_tool
# ═══════════════════════════════════════

class TestTavilySearchTool:
    """Tavily 联网检索 — 有 API key 做真实调用，无 key 优雅跳过"""

    @pytest.fixture
    def has_api_key(self):
        return bool(os.getenv("TAVILY_API_KEY", "").strip())

    def test_invoke_returns_str(self, has_api_key):
        """无论有无 key，invoke 必须返回 str（不抛未处理异常）。"""
        result = tavily_search_tool.invoke({
            "query": "字节跳动2026核心业务",
        })

        assert isinstance(result, str), f"返回类型应为 str，实际 {type(result)}"
        assert len(result) > 0, "返回字符串不应为空"

    @pytest.mark.skipif(
        not os.getenv("TAVILY_API_KEY", "").strip(),
        reason="未配置 TAVILY_API_KEY，跳过真实联网调用",
    )
    def test_live_search_returns_structured(self):
        """真实联网调用 — 验证返回结构含 '标题' + '内容' 或 '强相关'。"""
        result = tavily_search_tool.invoke({
            "query": "字节跳动2026核心业务",
        })

        # 正常响应要么有搜索结果，要么提示未找到
        has_results = "标题:" in result and "内容:" in result
        has_noise = "强相关" in result or "未找到" in result
        has_error = result.startswith("工具执行期间发生物理崩溃")

        assert has_results or has_noise or has_error, (
            f"联网响应结构异常: {result[:200]}..."
        )

        # 搜索结果不应为空壳
        if has_results:
            assert "---" in result, "搜索结果片段间应有分隔符"

    @pytest.mark.skipif(
        not os.getenv("TAVILY_API_KEY", "").strip(),
        reason="未配置 TAVILY_API_KEY，跳过真实联网调用",
    )
    def test_live_search_result_count(self):
        """验证 max_results=2 的 token 管控。"""
        result = tavily_search_tool.invoke({
            "query": "Python FastAPI 技术栈 2026",
        })

        if "标题:" in result:
            title_count = result.count("标题:")
            assert title_count <= 2, (
                f"预期最多 2 条结果，实际 {title_count} 条"
            )


# ═══════════════════════════════════════
# 全武器清单完整性
# ═══════════════════════════════════════

def test_agent_tools_count():
    """确保 AGENT_TOOLS 始终包含 3 把武器。"""
    from src.tools.agent_tools import AGENT_TOOLS

    assert len(AGENT_TOOLS) == 3

    names = {t.name for t in AGENT_TOOLS}
    expected = {"tavily_search_tool", "patch_resume_tool", "save_user_profile_tool"}
    assert names == expected, f"工具清单漂移: {names} != {expected}"
