import os
from langchain_openai import ChatOpenAI


def _get_env_or_raise(key: str) -> str:
    value = os.getenv(key)
    if not value:
        raise ValueError(f"环境变量 {key} 未设置，请在 .env 中配置")
    return value


def get_flash_client() -> ChatOpenAI:
    return ChatOpenAI(
        model=os.getenv("MODEL_FLASH", "deepseek-v4-flash"),
        api_key=_get_env_or_raise("DEEPSEEK_API_KEY"),
        base_url=_get_env_or_raise("DEEPSEEK_BASE_URL"),
        temperature=0.1,
    )


def get_pro_client() -> ChatOpenAI:
    return ChatOpenAI(
        model=os.getenv("MODEL_PRO", "deepseek-v4-pro"),
        api_key=_get_env_or_raise("DEEPSEEK_API_KEY"),
        base_url=_get_env_or_raise("DEEPSEEK_BASE_URL"),
        temperature=0.7,
        extra_body={"thinking": True},
    )
