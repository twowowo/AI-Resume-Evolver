import os
import logging
from langchain_openai import ChatOpenAI

logger = logging.getLogger("LLM")
logging.basicConfig(level=logging.INFO)

# ── v4.1 本地备胎配置 ──
_LOCAL_MODEL = "gemma3:1b"
_LOCAL_BASE_URL = "http://localhost:11434"


def get_flash_client():
    return ChatOpenAI(
        model=os.getenv("MODEL_FLASH", "deepseek-v4-flash"),
        api_key=os.getenv("DEEPSEEK_API_KEY"),
        base_url=os.getenv("DEEPSEEK_BASE_URL"),
        temperature=0.1,
        timeout=60,
        max_retries=3,
        streaming=False,
        default_headers={"Connection": "close"},
    )


def get_pro_client():
    return ChatOpenAI(
        model=os.getenv("MODEL_PRO", "deepseek-v4-pro"),
        api_key=os.getenv("DEEPSEEK_API_KEY"),
        base_url=os.getenv("DEEPSEEK_BASE_URL"),
        temperature=0.7,
        extra_body={"thinking": {"type": "enabled"}},
        timeout=120,
        max_retries=3,
        streaming=False,
        default_headers={"Connection": "close"},
    )


def _create_local_fallback(temperature: float = 0.3, max_tokens: int = 2048) -> ChatOpenAI:
    """
    本地 Ollama 备胎 —— gemma3:1b 约 700MB，在 2.5GB 可用内存的安全缝隙内运行。

    通过 ChatOpenAI 兼容接口连接 Ollama。
    """
    return ChatOpenAI(
        model=_LOCAL_MODEL,
        api_key="ollama",
        base_url=f"{_LOCAL_BASE_URL}/v1",
        temperature=temperature,
        max_tokens=max_tokens,
        timeout=60,
        max_retries=1,
    )


def get_resilient_llm(
    temperature: float = 0.3,
    max_tokens: int = 4096,
) -> ChatOpenAI:
    """
    v4.1 双模供给器：云端 DeepSeek 主线 (timeout=30s) + 本地 gemma3:1b 备胎防线。

    先尝试用 timeout=30s 的云端客户端探测，失败则自动降级到本地纯文本模型。
    本地备胎不具备 Function Calling 能力，调用方需通过 _is_fallback 属性判断。
    """
    try:
        client = ChatOpenAI(
            model=os.getenv("MODEL_FLASH", "deepseek-v4-flash"),
            api_key=os.getenv("DEEPSEEK_API_KEY"),
            base_url=os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
            temperature=temperature,
            max_tokens=max_tokens,
            timeout=30.0,  # v4.1：30s 超时，给 LangGraph 多轮 ReAct 留足吐字时间
            max_retries=1,
        )
        client.invoke("ping")
        client._is_fallback = False
        logger.info("[LLM] 云端主线 DeepSeek 正常服役 (timeout=30s)。")
        return client
    except Exception:
        logger.warning(
            "[FAILOVER ACTIVATED] 云端 DeepSeek 主线抖动（超时/网络异常），"
            f"已无缝激活本地 {_LOCAL_MODEL} 防线！"
        )
        logger.warning(
            "[STRATEGY] 本地备胎不具备工具调用能力，"
            "已自动启动纯知识库离线简历优化方案！"
        )
        fallback = _create_local_fallback(temperature=temperature, max_tokens=max_tokens)
        fallback._is_fallback = True
        return fallback
