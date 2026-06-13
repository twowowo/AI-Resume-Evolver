"""
4.1 大模型供给器状态面板 —— 云端主线 + 本地备胎健康监控

核心降级逻辑在 src.utils.llm.get_resilient_llm() 中实现。
本模块提供：状态查询、健康探测、强制本地模式、状态重置。
"""

import os
import logging
from src.utils.llm import get_resilient_llm as _get_resilient_core

logger = logging.getLogger("LLMProvider")
logging.basicConfig(level=logging.INFO)

_LOCAL_MODEL = "gemma3:1b"
_LOCAL_BASE_URL = "http://localhost:11434"
_CLOUD_TIMEOUT = 30.0

_primary_available = None  # None=未探测, True=主线正常, False=已降级


def get_resilient_llm(
    temperature: float = 0.3,
    max_tokens: int = 4096,
    force_local: bool = False,
):
    """
    获取具有自动降级能力的大模型客户端。

    首次调用自动探测云端健康度，后续调用使用缓存状态。
    force_local=True 跳过探测直接使用本地备胎。
    """
    global _primary_available

    if force_local:
        logger.info("[LLMProvider] 强制本地模式，跳过云端探测")
        return _get_resilient_core(temperature=temperature, max_tokens=max_tokens)

    if _primary_available is None:
        logger.info("[LLMProvider] 首次启动，探测云端主线健康度...")
        try:
            client = _get_resilient_core(temperature=0.0, max_tokens=1)
            client.invoke("ping")
            _primary_available = True
            logger.info("[LLMProvider] 云端主线 DeepSeek 健康，正常服役。")
        except Exception:
            _primary_available = False
            logger.warning(
                "[FAILOVER ACTIVATED] 云端 DeepSeek 主线不可达（超时/网络异常），"
                f"已无缝激活本地 {_LOCAL_MODEL} 防线！"
                "后续请求将走本地备胎通道。"
            )
            logger.warning(
                "[STRATEGY] 本地备胎不具备工具调用能力，"
                "已自动启动纯知识库离线简历优化方案！"
            )

    return _get_resilient_core(temperature=temperature, max_tokens=max_tokens)


def reset_provider_state() -> None:
    """重置供给器状态，下次调用时重新探测云端。"""
    global _primary_available
    _primary_available = None
    logger.info("[LLMProvider] 供给器状态已重置，下次调用将重新探测云端。")


def get_provider_status() -> dict:
    """返回当前供给器状态，供健康检查端点使用"""
    status = (
        "cloud" if _primary_available
        else ("local" if _primary_available is False else "unknown")
    )
    return {
        "primary_model": os.getenv("MODEL_FLASH", "deepseek-v4-flash"),
        "fallback_model": _LOCAL_MODEL,
        "status": status,
        "cloud_timeout_s": _CLOUD_TIMEOUT,
    }
