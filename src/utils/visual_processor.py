"""
Qwen-OCR 视觉前哨注入系统 (百炼 DashScope)
===========================================
v4.5 特种模型升级：锁定 qwen-vl-ocr-latest (Qwen3-VL 架构)，
通过百炼 DashScope 兼容模式直连，将简历图片编码为 Base64 送入 OCR 特种模型。
仅 0.3元/百万 Token，文字提取 + 表格解析 + 倾斜排版表现恐怖。

架构优势：
  - 零本地模型依赖（无需下载 ~200MB EasyOCR 模型）
  - 异步非阻塞 I/O，释放 FastAPI 事件循环
  - Qwen3-VL 自带技术名词自动校准（React, Python, LangGraph 零错漏）
  - 复杂排版自适应（双栏/表格/下划线/倾斜文本）
  - temperature=0.1 锁死高确定性输出
  - 成本仅为通用多模态模型的 ~1/10
"""

import base64
import io
import logging
import os
from pathlib import Path

from dotenv import load_dotenv
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
)

# ── 模块级安全加载 .env（与 main.py 互不冲突，幂等操作）──
_ENV_PATH = Path(__file__).resolve().parent.parent.parent / ".env"
load_dotenv(dotenv_path=_ENV_PATH)

logger = logging.getLogger("VisualProcessor")
logging.basicConfig(level=logging.INFO)

# ── 全局 AsyncOpenAI 单例 ──
_async_client = None


def _get_async_client():
    """获取/初始化 AsyncOpenAI 单例（复用连接池）—— v4.5 锁定百炼 DashScope

    安全约束：
      - 绝不硬编码任何 API Key，全部从 .env 动态加载
      - QWEN_API_KEY 缺失时立即熔断，防止空 Key 裸奔请求
      - QWEN_BASE_URL 可选，默认指向百炼 DashScope 兼容端点
    """
    global _async_client
    if _async_client is None:
        from openai import AsyncOpenAI

        api_key = os.getenv("QWEN_API_KEY")
        if not api_key:
            raise ValueError(
                "[视觉引擎安全熔断] 未在环境变量中检测到有效的 QWEN_API_KEY，"
                "请检查根目录 .env 文件中是否已配置该变量！"
            )

        base_url = os.getenv("QWEN_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1")

        _async_client = AsyncOpenAI(
            api_key=api_key,
            base_url=base_url,
            timeout=120.0,
            max_retries=3,
        )
        logger.info("[Qwen-OCR] AsyncOpenAI 客户端已就绪 (百炼 DashScope 兼容模式, timeout=120s)。")
    return _async_client


# ═══════════════════════════════════════════════════════════════
# v4.5 Qwen-OCR 视觉结构化解析 Prompt 守卫
# ═══════════════════════════════════════════════════════════════

_VISION_PROMPT = (
    "请仔细阅读这张简历图片，完整、结构化地提取出所有文字，"
    "将解析结果规整为自带高价值语义、格式极其精美的标准 Markdown 文本输出。"
    "请直接输出 Markdown，不要包含任何前导废话。"
)


async def parse_resume_image_via_vlm(image_bytes: bytes) -> str:
    """
    使用 Qwen-OCR 特种模型 (qwen-vl-ocr-latest) 解析简历图片，返回结构化 Markdown。

    Args:
        image_bytes: PNG / JPEG / WebP / BMP 等图片的原始字节

    Returns:
        提取并规整后的 Markdown 文本
    """
    client = _get_async_client()

    # ── 图片物理编码为 Base64 Data URL ──
    image = _detect_and_convert(image_bytes)
    buffered = io.BytesIO()
    # 统一输出为 JPEG 以控制体积（百炼 Vision 限制单图 < 20MB）
    save_format = "JPEG" if image.mode != "RGBA" else "PNG"
    image.save(buffered, format=save_format, quality=85)
    encoded = base64.b64encode(buffered.getvalue()).decode("utf-8")
    mime = "image/jpeg" if save_format == "JPEG" else "image/png"
    data_url = f"data:{mime};base64,{encoded}"

    logger.info(
        f"[Qwen-OCR] 图片已编码: {image.size[0]}x{image.size[1]}, "
        f"Base64 长度={len(encoded)} 字符, 格式={save_format}"
    )

    # ── v4.5 调用 Qwen-OCR 特种模型 (百炼 DashScope 兼容模式) ──
    # 格式准则：
    #   1. text 必须排在 image_url 之前（标准 VLM 协议要求）
    #   2. content 数组严格遵循 OpenAI Vision 标准
    #   3. temperature=0.1 锁死低随机性，Qwen3-VL 自带技术名词自动校准
    #   4. tenacity 异步重试：瞬时网络抖动自动恢复 (最大 3 次, 指数退避 1s→2s→4s)

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=8),
        retry=retry_if_exception_type((IOError, TimeoutError, ConnectionError)),
        reraise=True,
    )
    async def _call_ocr_api():
        return await client.chat.completions.create(
            model="qwen-vl-ocr-latest",
            temperature=0.1,
            max_tokens=4096,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": _VISION_PROMPT},
                        {
                            "type": "image_url",
                            "image_url": {"url": data_url},
                        },
                    ],
                }
            ],
        )

    try:
        response = await _call_ocr_api()
    except Exception as e:
        err_msg = str(e)
        logger.error(f"[Qwen-OCR] API 调用失败 (含重试): {type(e).__name__}: {err_msg[:300]}")

        # ── 权限/端点兜底检测（不可重试错误，直接熔断）──
        if "401" in err_msg or "403" in err_msg:
            raise RuntimeError(
                "[视觉引擎] 百炼 DashScope API Key 鉴权失败，"
                "请确认 DASHSCOPE_API_KEY 环境变量已正确设置且未过期。"
            )
        if "image_url" in err_msg or "variant" in err_msg:
            raise RuntimeError(
                "[视觉引擎] 百炼端点不支持 image_url 多模态格式，"
                "请确认 qwen-vl-ocr-latest 模型已开通视觉权限。"
            )
        if "model" in err_msg.lower() or "not found" in err_msg.lower():
            raise RuntimeError(
                "[视觉引擎] qwen-vl-ocr-latest 模型不可用，"
                "请前往百炼控制台确认模型已开通。"
            )
        raise

    # ── 提取响应 ──
    markdown_text = ""
    if response.choices and response.choices[0].message.content:
        markdown_text = response.choices[0].message.content.strip()

    if not markdown_text:
        raise RuntimeError("Qwen-OCR 返回空内容，图片可能无文字或格式不支持")

    logger.info(
        f"[Qwen-OCR 视觉前哨注入成功] 已通过 qwen-vl-ocr-latest "
        f"将简历图片转为结构化 Markdown，字符数: {len(markdown_text)}"
    )

    return markdown_text


def _detect_and_convert(image_bytes: bytes):
    """
    解码图片并统一转 RGB，确保 Qwen-OCR Vision 兼容性。

    PIL 解码支持 PNG / JPEG / WebP / BMP / GIF。
    RGBA 图片保留原样（转为 PNG Base64），其余统一转 RGB JPEG。
    """
    from PIL import Image

    image = Image.open(io.BytesIO(image_bytes))

    # GIF 动图 → 取首帧
    if getattr(image, "is_animated", False):
        image.seek(0)

    # CMYK / P / RGBA → RGB（纯色底），RGBA 保留
    if image.mode == "CMYK":
        image = image.convert("RGB")
    elif image.mode == "P":
        image = image.convert("RGBA" if "transparency" in image.info else "RGB")
    elif image.mode == "L":
        image = image.convert("RGB")
    elif image.mode == "RGBA":
        pass  # 保留透明通道，输出为 PNG
    elif image.mode not in ("RGB",):
        image = image.convert("RGB")

    return image


def local_ocr_analyze(image_bytes: bytes) -> str:
    """
    v4.4 同步兼容层：内部调用异步 Vision 解析函数。

    保留此函数签名为向后兼容（main.py 同步调用路径）。
    在 async 端点中请直接使用 await parse_resume_image_via_vlm()。
    """
    import asyncio

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        # 无运行中的事件循环 → 新建
        return asyncio.run(parse_resume_image_via_vlm(image_bytes))

    # 有运行中的事件循环 → 在独立线程中跑（避免嵌套事件循环冲突）
    import concurrent.futures

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(asyncio.run, parse_resume_image_via_vlm(image_bytes))
        return future.result()


def reset_reader() -> None:
    """
    v4.4 无操作保留（EasyOCR 已物理移除）。
    保留此函数签名为向后兼容。
    """
    global _async_client
    _async_client = None
    logger.info("[Qwen-OCR] AsyncOpenAI 客户端已重置。")
