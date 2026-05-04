import os
from langchain_openai import ChatOpenAI


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
