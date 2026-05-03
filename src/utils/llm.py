import os
from langchain_openai import ChatOpenAI


def _get_env_or_raise(key: str, hint: str = "") -> str:
    value = os.getenv(key)
    if not value:
        msg = f"环境变量 {key} 未设置，请在 .env 中配置"
        if hint:
            msg += f"\n  提示：{hint}"
        raise ValueError(msg)
    return value


def get_flash_client() -> ChatOpenAI:
    return ChatOpenAI(
        model=os.getenv("MODEL_FLASH", "deepseek-v4-flash"),
        api_key=_get_env_or_raise(
            "DEEPSEEK_API_KEY",
            hint="从 https://platform.deepseek.com 获取 API Key",
        ),
        base_url=_get_env_or_raise(
            "DEEPSEEK_BASE_URL",
            hint="DeepSeek 官方地址: https://api.deepseek.com",
        ),
        temperature=0.1,
    )


def get_pro_client() -> ChatOpenAI:
    return ChatOpenAI(
        model=os.getenv("MODEL_PRO", "deepseek-v4-pro"),
        api_key=_get_env_or_raise(
            "DEEPSEEK_API_KEY",
            hint="从 https://platform.deepseek.com 获取 API Key",
        ),
        base_url=_get_env_or_raise(
            "DEEPSEEK_BASE_URL",
            hint="DeepSeek 官方地址: https://api.deepseek.com",
        ),
        temperature=0.7,
        extra_body={"thinking": True},
    )
