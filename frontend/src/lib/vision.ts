/**
 * 视觉感知 API 层 —— 对接后端 POST /api/v1/upload/parse
 *
 * 支持：PDF / DOCX / TXT 文件物理去噪 + 图片多模态 Vision OCR
 * 后端使用 DeepSeek Vision 模型进行 OCR/视觉推理
 */

const VISION_API = "http://127.0.0.1:8001/api/v1/upload/parse";

const MAX_IMAGE_DIMENSION = 2000;
const MAX_IMAGE_SIZE_MB = 2;
const UPLOAD_TIMEOUT_MS = 120000; // 对齐后端 Qwen-OCR 120s 超时 + tenacity 重试窗口

/**
 * 客户端图片压缩 —— 超大图片缩放 + JPEG 转换，防止击穿后端请求上限
 */
export function compressImage(file: File): Promise<File> {
  return new Promise((resolve) => {
    if (!file.type.startsWith("image/")) {
      resolve(file);
      return;
    }

    const needsCompress =
      file.size > MAX_IMAGE_SIZE_MB * 1024 * 1024;

    if (!needsCompress) {
      // 小图仍需检查尺寸
      const img = new Image();
      const url = URL.createObjectURL(file);
      img.onload = () => {
        URL.revokeObjectURL(url);
        if (img.width <= MAX_IMAGE_DIMENSION && img.height <= MAX_IMAGE_DIMENSION) {
          resolve(file);
          return;
        }
        resizeImage(img, file.name, resolve);
      };
      img.onerror = () => resolve(file);
      img.src = url;
      return;
    }

    const img = new Image();
    const url = URL.createObjectURL(file);
    img.onload = () => {
      URL.revokeObjectURL(url);
      resizeImage(img, file.name, resolve);
    };
    img.onerror = () => resolve(file);
    img.src = url;
  });
}

function resizeImage(
  img: HTMLImageElement,
  fileName: string,
  resolve: (file: File) => void
) {
  let { width, height } = img;
  if (width > MAX_IMAGE_DIMENSION || height > MAX_IMAGE_DIMENSION) {
    const ratio = Math.min(
      MAX_IMAGE_DIMENSION / width,
      MAX_IMAGE_DIMENSION / height
    );
    width = Math.round(width * ratio);
    height = Math.round(height * ratio);
  }

  const canvas = document.createElement("canvas");
  canvas.width = width;
  canvas.height = height;
  const ctx = canvas.getContext("2d")!;
  ctx.drawImage(img, 0, 0, width, height);

  canvas.toBlob(
    (blob) => {
      if (blob) {
        resolve(new File([blob], fileName.replace(/\.[^.]+$/, ".jpg"), { type: "image/jpeg" }));
      } else {
        resolve(new File([], fileName));
      }
    },
    "image/jpeg",
    0.85
  );
}

/**
 * 调用后端多模态解析端点，返回提取的纯文本。
 * 支持图片 (Vision OCR)、PDF、DOCX、TXT。
 */
export async function analyzeFileToText(file: File): Promise<string> {
  const formData = new FormData();
  formData.append("file", file);

  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), UPLOAD_TIMEOUT_MS);

  try {
    const response = await fetch(VISION_API, {
      method: "POST",
      body: formData,
      signal: controller.signal,
    });

    if (!response.ok) {
      let detail = `服务器返回 ${response.status}`;
      try {
        const err = await response.json();
        if (err.detail) detail = err.detail;
      } catch {
        // ignore parse error, use default
      }
      throw new Error(detail);
    }

    const data = await response.json();
    if (!data.success || !data.text) {
      throw new Error("后端返回数据异常，未提取到有效文本");
    }
    return data.text as string;
  } catch (err: unknown) {
    if (err instanceof DOMException && err.name === "AbortError") {
      throw new Error("视觉推理超时（120s），请稍后重试或检查后端 Qwen-OCR 服务状态");
    }
    throw err instanceof Error ? err : new Error("未知视觉推理异常");
  } finally {
    clearTimeout(timeoutId);
  }
}
