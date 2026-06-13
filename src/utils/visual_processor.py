"""
视觉感知处理器 —— 本地 OCR 引擎
================================
v4.1 视觉降级策略：彻底摒弃 DeepSeek `image_url` 直传，
改用本地 easyocr (中文 + 英文) 先提取纯文本，
再将文本作为常规 Prompt 送入 LLM。

easyocr 首用时会自动下载 ~200MB 模型（缓存到 ~/.EasyOCR/model/），
后续调用直接走缓存，无需网络。
"""

import io
import logging
from PIL import Image

import easyocr

logger = logging.getLogger("VisualProcessor")
logging.basicConfig(level=logging.INFO)

# 全局单例：首次调用 init_reader() 加载模型，后续复用
_reader: easyocr.Reader | None = None


def _get_reader() -> easyocr.Reader:
    """获取/初始化 easyocr Reader 单例（中文 + 英文）"""
    global _reader
    if _reader is None:
        logger.info("[视觉感知] 正在初始化本地 OCR 引擎 (easyocr, zh+en)...")
        _reader = easyocr.Reader(["ch_sim", "en"], gpu=False, verbose=False)
        logger.info("[视觉感知] 本地 OCR 引擎就绪。")
    return _reader


def local_ocr_analyze(image_bytes: bytes) -> str:
    """
    对传入的图片字节流执行本地 OCR，返回提取的纯文本。

    Args:
        image_bytes: PNG / JPEG / WebP / BMP 等图片的原始字节

    Returns:
        提取出的纯文本字符串（保持原图阅读顺序，段落以换行分隔）
    """
    reader = _get_reader()

    # PIL 解码图片
    image = Image.open(io.BytesIO(image_bytes))
    # 统一转 RGB（easyocr 要求 numpy array 为 RGB 格式）
    if image.mode not in ("RGB", "L"):
        image = image.convert("RGB")

    logger.info(f"[视觉感知] 开始本地 OCR: {image.size}, mode={image.mode}")

    # easyocr 直接读 PIL Image
    results = reader.readtext(image, detail=0, paragraph=True)

    text = "\n".join(results).strip()
    logger.info(f"[视觉感知] 本地 OCR 解析成功，共提取 {len(text)} 字符")
    return text


def reset_reader() -> None:
    """重置 OCR 引擎（释放显存/内存，下次调用重新加载）"""
    global _reader
    _reader = None
    logger.info("[视觉感知] OCR 引擎已重置。")
