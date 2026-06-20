"""v2.4 Pydantic 数据契约 —— 简历优化的请求/响应模型"""

from pydantic import BaseModel, Field, field_validator
from enum import Enum
from typing import Optional


# ── 6-3-1 雷达指标结构 ──

class RadarMetrics(BaseModel):
    """6-3-1 死锁权重雷达图指标

    jd_matching_score: 技术栈 JD 匹配度 (0-60)
    star_perf_score:   STAR 业绩完成度 (0-30)
    action_verbs_score: 动词规范与指标质量 (0-10)
    total_score:       该版本总分 (0-100)
    """

    jd_matching_score: int = Field(..., ge=0, le=60, description="技术栈 JD 匹配度 (0-60)")
    star_perf_score: int = Field(..., ge=0, le=30, description="STAR 业绩完成度 (0-30)")
    action_verbs_score: int = Field(..., ge=0, le=10, description="动词规范与指标质量 (0-10)")
    total_score: int = Field(..., ge=0, le=100, description="该版本总分 (0-100)")

    @field_validator("total_score")
    @classmethod
    def check_total_consistency(cls, v, info):
        """校验 total_score 与三维分项之和是否在合理误差范围内"""
        jd = info.data.get("jd_matching_score", 0) if info.data else 0
        star = info.data.get("star_perf_score", 0) if info.data else 0
        verb = info.data.get("action_verbs_score", 0) if info.data else 0
        expected = jd + star + verb
        if abs(v - expected) > 5:
            raise ValueError(
                f"total_score ({v}) 与三维分项之和 ({expected}) 偏差超过 5 分，"
                f"请检查评分一致性"
            )
        return v

    @staticmethod
    def from_dimensions(dims: dict, total: int) -> "RadarMetrics":
        """从 evaluator / pre_evaluator 的 dimension_scores 字典构建"""
        return RadarMetrics(
            jd_matching_score=dims.get("jd_match", 0),
            star_perf_score=dims.get("star_completion", 0),
            action_verbs_score=dims.get("verb_quality", 0),
            total_score=total,
        )


# ── 模式选择枚举 ──

class OptimizeMode(str, Enum):
    """简历优化模式

    ONE_CLICK:   一键生成模式 —— 全自动链路，直接返回优化结果
    INTERACTIVE: 交互模式 —— WebSocket 长连接，多轮博弈（暂未实现）
    """

    ONE_CLICK = "one_click"
    INTERACTIVE = "interactive"


# ── 请求体 ──

class ResumeOptimizeRequest(BaseModel):
    """简历优化统一请求体 —— v4.2 多租户隔离沙箱"""

    resume_text: str = Field(
        ..., max_length=10000,
        description="原始简历文本内容"
    )
    jd_text: str = Field(
        ..., max_length=5000,
        description="目标岗位 JD 文本内容"
    )
    mode: OptimizeMode = Field(
        default=OptimizeMode.ONE_CLICK,
        description="优化模式：one_click 一键生成 / interactive 交互博弈"
    )
    session_id: Optional[str] = Field(
        default=None,
        description="会话 ID (UUID)，用于交互模式断点续传。一键模式可选，服务端未传时自动生成"
    )
    user_id: str = Field(
        default="default_user",
        description="用户全局唯一 ID，贯穿全链路三层漏斗隔离"
    )
    resume_id: str = Field(
        default="default_resume",
        description="当前简历文件唯一 Hash 标识，锁死记忆沙箱边界"
    )


class ChatRequest(BaseModel):
    """交互模式多轮对话请求体 —— 用于 /api/v1/resume/chat"""

    thread_id: str = Field(
        ..., min_length=1, max_length=128,
        description="会话 ID (UUID)，与一键优化接口的 session_id 对应"
    )
    user_message: str = Field(
        ..., min_length=1, max_length=5000,
        description="用户输入的补充信息/修改意见"
    )


# ── 响应体子模型 ──

class StressTestQuestion(BaseModel):
    """MockInterviewer 压测题"""

    question_number: int = Field(..., ge=1, le=10, description="题目序号")
    category: str = Field(..., description="题目类别：技术深度/项目经验/系统设计/行为面试")
    question: str = Field(..., min_length=5, description="面试问题正文")
    expected_points: list[str] = Field(
        default_factory=list,
        description="面试官期望的回答要点"
    )


class OptimizeResponse(BaseModel):
    """一键流优化响应体"""

    success: bool = Field(..., description="优化是否成功完成")
    original_resume_radar: RadarMetrics = Field(..., description="原始简历 6-3-1 雷达指标")
    optimized_resume_radar: Optional[RadarMetrics] = Field(
        None, description="优化后简历 6-3-1 雷达指标（终评结果）"
    )
    optimized_resume_text: str = Field(
        default="", description="优化后的完整简历文本"
    )
    internal_monologue: str = Field(
        default="", description="Agent 内心独白（毒舌批评）"
    )
    stress_test_questions: list[StressTestQuestion] = Field(
        default_factory=list, description="MockInterviewer 生成的压测面试题"
    )
    difficulty_flag: str = Field(
        default="", description="分诊标记：NORMAL / EXTREME_GAP"
    )
    iteration_count: int = Field(
        default=0, description="精修迭代轮次"
    )
    message: str = Field(
        default="", description="附加说明或错误信息"
    )
