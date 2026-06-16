/**
 * useOCRParser — 多模态图片粘贴/上传 → OCR 解析共享 Hook
 *
 * 供 AgentConsole 和 PipelineInput 复用，封装：
 *   1. 客户端图片压缩 (compressImage)
 *   2. 后端 OCR 调用 (analyzeFileToText)
 *   3. 加载/成功/错误状态管理
 *   4. 剪贴板图片提取 (handlePaste)
 */

"use client";

import { useState, useCallback, type ClipboardEvent, type ChangeEvent } from "react";
import { analyzeFileToText, compressImage } from "@/lib/vision";

export interface OCRStatus {
  type: "loading" | "success" | "error";
  message: string;
}

export function useOCRParser() {
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [status, setStatus] = useState<OCRStatus | null>(null);

  /** 核心管道：压缩 → OCR → 返回文本 */
  const processImage = useCallback(async (file: File): Promise<string | null> => {
    setIsAnalyzing(true);
    setStatus({ type: "loading", message: "正在识别中..." });

    try {
      const compressed = await compressImage(file);
      const text = await analyzeFileToText(compressed);

      if (!text?.trim()) {
        setStatus({ type: "error", message: "OCR 未识别到有效文字内容" });
        return null;
      }

      setStatus({
        type: "success",
        message: `✅ 识别成功 · ${text.length.toLocaleString()} 字符`,
      });
      return text;
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "未知 OCR 异常";
      setStatus({ type: "error", message: `❌ ${msg}` });
      return null;
    } finally {
      setIsAnalyzing(false);
    }
  }, []);

  /** 从剪贴板事件中提取图片 File（无图片时返回 null） */
  const extractImageFromPaste = useCallback(
    (e: ClipboardEvent): File | null => {
      const items = e.clipboardData.items;
      for (let i = 0; i < items.length; i++) {
        if (items[i].type.indexOf("image") !== -1) {
          e.preventDefault();
          const file = items[i].getAsFile();
          if (file) return file;
        }
      }
      return null;
    },
    []
  );

  /** 粘贴即 OCR：图片 → 解析 → 回调注入文本（无图片时返回 null 走默认行为） */
  const handlePaste = useCallback(
    async (e: ClipboardEvent): Promise<string | null> => {
      const file = extractImageFromPaste(e);
      if (!file) return null;
      return processImage(file);
    },
    [extractImageFromPaste, processImage]
  );

  /** 文件选择即 OCR */
  const handleFileSelect = useCallback(
    async (e: ChangeEvent<HTMLInputElement>): Promise<{ file: File; text: string | null } | null> => {
      const file = e.target.files?.[0];
      if (!file) return null;
      // 重置 input 以允许重复选择同一文件
      e.target.value = "";
      const text = await processImage(file);
      return { file, text };
    },
    [processImage]
  );

  const resetStatus = useCallback(() => setStatus(null), []);

  return { isAnalyzing, status, processImage, handlePaste, handleFileSelect, resetStatus };
}
