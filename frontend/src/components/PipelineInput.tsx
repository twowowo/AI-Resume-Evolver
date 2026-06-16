"use client";

import { useState, useRef, useCallback, type FormEvent, type ChangeEvent, type ClipboardEvent } from "react";
import { useOCRParser } from "@/hooks/useOCRParser";

interface PipelineInputProps {
  onSubmit: (resume: string, jd: string) => void;
  isStreaming: boolean;
}

type VisionTarget = "resume" | "jd";

export default function PipelineInput({ onSubmit, isStreaming }: PipelineInputProps) {
  const [resumeText, setResumeText] = useState("");
  const [jdText, setJdText] = useState("");

  // ── 共享 OCR Hook ──
  const resumeOCR = useOCRParser();
  const jdOCR = useOCRParser();

  const isAnalyzing = resumeOCR.isAnalyzing || jdOCR.isAnalyzing;

  // 隐藏文件输入 refs
  const resumeFileRef = useRef<HTMLInputElement>(null);
  const jdFileRef = useRef<HTMLInputElement>(null);

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault();
    if (!resumeText.trim() || !jdText.trim() || isStreaming || isAnalyzing) return;
    onSubmit(resumeText.trim(), jdText.trim());
  };

  // ── 📋 Ctrl+V 粘贴拦截：图片 → OCR → 回填文本 ──
  const handleResumePaste = useCallback(
    async (e: ClipboardEvent<HTMLTextAreaElement>) => {
      const text = await resumeOCR.handlePaste(e);
      if (text) setResumeText(text);
    },
    [resumeOCR]
  );

  const handleJDPaste = useCallback(
    async (e: ClipboardEvent<HTMLTextAreaElement>) => {
      const text = await jdOCR.handlePaste(e);
      if (text) setJdText(text);
    },
    [jdOCR]
  );

  // ── 📎 文件上传通道 ──
  const handleResumeFile = useCallback(
    async (e: ChangeEvent<HTMLInputElement>) => {
      const result = await resumeOCR.handleFileSelect(e);
      if (result?.text) setResumeText(result.text);
    },
    [resumeOCR]
  );

  const handleJDFile = useCallback(
    async (e: ChangeEvent<HTMLInputElement>) => {
      const result = await jdOCR.handleFileSelect(e);
      if (result?.text) setJdText(result.text);
    },
    [jdOCR]
  );

  // 合并状态 Toast（优先显示活跃的）
  const activeStatus = resumeOCR.status ?? jdOCR.status;

  return (
    <div className="flex flex-col h-full bg-zinc-50 dark:bg-zinc-950">
      {/* 标题栏 */}
      <div className="px-4 py-3 border-b border-zinc-200 dark:border-zinc-800 bg-white dark:bg-black">
        <h2 className="text-sm font-bold tracking-wide text-zinc-800 dark:text-zinc-100">
          ⚡ 一键流水线
        </h2>
        <p className="text-xs text-zinc-500 mt-0.5">
          粘贴或上传简历与 JD，AI 全链路自动精修
        </p>
      </div>

      {/* ── 视觉感知状态条 ── */}
      {activeStatus && (
        <div
          className={`mx-4 mt-3 px-3 py-2 rounded-lg text-xs font-medium flex items-center justify-between gap-2 transition-all ${
            activeStatus.type === "loading"
              ? "bg-blue-50 dark:bg-blue-950/30 border border-blue-200 dark:border-blue-700 text-blue-700 dark:text-blue-300"
              : activeStatus.type === "success"
              ? "bg-emerald-50 dark:bg-emerald-950/30 border border-emerald-200 dark:border-emerald-700 text-emerald-700 dark:text-emerald-300"
              : "bg-red-50 dark:bg-red-950/30 border border-red-200 dark:border-red-700 text-red-700 dark:text-red-300"
          }`}
        >
          <span className="flex items-center gap-2">
            {activeStatus.type === "loading" && (
              <span className="flex gap-0.5">
                <span className="w-1.5 h-1.5 bg-blue-500 rounded-full animate-bounce [animation-delay:0ms]" />
                <span className="w-1.5 h-1.5 bg-blue-500 rounded-full animate-bounce [animation-delay:150ms]" />
                <span className="w-1.5 h-1.5 bg-blue-500 rounded-full animate-bounce [animation-delay:300ms]" />
              </span>
            )}
            {activeStatus.message}
          </span>
          {activeStatus.type === "error" && (
            <button
              onClick={() => { resumeOCR.resetStatus(); jdOCR.resetStatus(); }}
              className="text-red-400 hover:text-red-600 dark:hover:text-red-200 transition-colors shrink-0"
            >
              ✕
            </button>
          )}
        </div>
      )}

      {/* 输入表单 */}
      <form onSubmit={handleSubmit} className="flex-1 flex flex-col p-4 gap-4 overflow-y-auto">
        {/* ── 简历输入 ── */}
        <div className="flex flex-col gap-1.5">
          <div className="flex items-center justify-between">
            <label className="text-xs font-semibold text-zinc-600 dark:text-zinc-400">
              📄 原始简历
            </label>
            <button
              type="button"
              onClick={() => resumeFileRef.current?.click()}
              disabled={isStreaming || isAnalyzing}
              className={`inline-flex items-center gap-1 text-[11px] font-medium rounded-md px-2 py-0.5 transition-colors ${
                resumeOCR.isAnalyzing
                  ? "bg-blue-100 dark:bg-blue-900/30 text-blue-600 dark:text-blue-400"
                  : "text-zinc-500 hover:text-blue-600 dark:text-zinc-400 dark:hover:text-blue-400 hover:bg-blue-50 dark:hover:bg-blue-950/30"
              } disabled:opacity-40`}
            >
              {resumeOCR.isAnalyzing ? (
                <>
                  <span className="w-2.5 h-2.5 border-2 border-blue-500 border-t-transparent rounded-full animate-spin" />
                  解析中...
                </>
              ) : (
                <>
                  📎 上传文件/截图
                </>
              )}
            </button>
            <input
              ref={resumeFileRef}
              type="file"
              accept=".pdf,.docx,.txt,.md,.png,.jpg,.jpeg,.webp,.gif,.bmp"
              onChange={handleResumeFile}
              className="hidden"
            />
          </div>
          <textarea
            value={resumeText}
            onChange={(e) => setResumeText(e.target.value)}
            onPaste={handleResumePaste}
            placeholder="粘贴你的原始简历 Markdown / 文本…
支持 Ctrl+V 直接粘贴简历截图，视觉大脑将自动解析…
或点击上方 📎 按钮上传文件…"
            rows={10}
            disabled={isStreaming || resumeOCR.isAnalyzing}
            className="w-full px-3 py-2.5 text-sm rounded-xl border border-zinc-300 dark:border-zinc-700 bg-white dark:bg-zinc-900 text-zinc-900 dark:text-zinc-100 placeholder-zinc-400 focus:outline-none focus:ring-2 focus:ring-blue-500 resize-none disabled:opacity-50 transition-shadow"
          />
          {/* 简历输入区 Loading Spinner */}
          {resumeOCR.isAnalyzing && (
            <div className="flex items-center justify-center gap-2 py-1 text-xs text-blue-600 dark:text-blue-400">
              <span className="w-3 h-3 border-2 border-blue-500 border-t-transparent rounded-full animate-spin" />
              正在识别中...
            </div>
          )}
        </div>

        {/* ── JD 输入 ── */}
        <div className="flex flex-col gap-1.5">
          <div className="flex items-center justify-between">
            <label className="text-xs font-semibold text-zinc-600 dark:text-zinc-400">
              🎯 目标岗位 JD
            </label>
            <button
              type="button"
              onClick={() => jdFileRef.current?.click()}
              disabled={isStreaming || isAnalyzing}
              className={`inline-flex items-center gap-1 text-[11px] font-medium rounded-md px-2 py-0.5 transition-colors ${
                jdOCR.isAnalyzing
                  ? "bg-blue-100 dark:bg-blue-900/30 text-blue-600 dark:text-blue-400"
                  : "text-zinc-500 hover:text-blue-600 dark:text-zinc-400 dark:hover:text-blue-400 hover:bg-blue-50 dark:hover:bg-blue-950/30"
              } disabled:opacity-40`}
            >
              {jdOCR.isAnalyzing ? (
                <>
                  <span className="w-2.5 h-2.5 border-2 border-blue-500 border-t-transparent rounded-full animate-spin" />
                  解析中...
                </>
              ) : (
                <>
                  📎 上传文件/截图
                </>
              )}
            </button>
            <input
              ref={jdFileRef}
              type="file"
              accept=".pdf,.docx,.txt,.md,.png,.jpg,.jpeg,.webp,.gif,.bmp"
              onChange={handleJDFile}
              className="hidden"
            />
          </div>
          <textarea
            value={jdText}
            onChange={(e) => setJdText(e.target.value)}
            onPaste={handleJDPaste}
            placeholder="粘贴目标岗位的职位描述…
支持 Ctrl+V 直接粘贴 JD 截图，视觉大脑将自动提取关键要求…
或点击上方 📎 按钮上传文件…"
            rows={6}
            disabled={isStreaming || jdOCR.isAnalyzing}
            className="w-full px-3 py-2.5 text-sm rounded-xl border border-zinc-300 dark:border-zinc-700 bg-white dark:bg-zinc-900 text-zinc-900 dark:text-zinc-100 placeholder-zinc-400 focus:outline-none focus:ring-2 focus:ring-blue-500 resize-none disabled:opacity-50 transition-shadow"
          />
          {/* JD 输入区 Loading Spinner */}
          {jdOCR.isAnalyzing && (
            <div className="flex items-center justify-center gap-2 py-1 text-xs text-blue-600 dark:text-blue-400">
              <span className="w-3 h-3 border-2 border-blue-500 border-t-transparent rounded-full animate-spin" />
              正在识别中...
            </div>
          )}
        </div>

        {/* 文件上传支持提示 */}
        <div className="flex items-center gap-2 px-3 py-2 rounded-lg border border-dashed border-zinc-300 dark:border-zinc-700 text-xs text-zinc-400 dark:text-zinc-500">
          <span>📎</span>
          <span>支持 PDF / DOCX / TXT / 图片（PNG JPG WEBP）—— 📎 上传 或 Ctrl+V 粘贴，视觉大脑自动 OCR</span>
        </div>

        {/* 点火按钮 */}
        <button
          type="submit"
          disabled={!resumeText.trim() || !jdText.trim() || isStreaming || isAnalyzing}
          className="w-full py-3 text-sm font-bold rounded-xl bg-blue-600 text-white hover:bg-blue-700 disabled:opacity-40 transition-all mt-auto active:scale-[0.98]"
        >
          {isStreaming ? (
            <span className="flex items-center justify-center gap-2">
              <span className="flex gap-0.5">
                <span className="w-1.5 h-1.5 bg-white rounded-full animate-bounce [animation-delay:0ms]" />
                <span className="w-1.5 h-1.5 bg-white rounded-full animate-bounce [animation-delay:150ms]" />
                <span className="w-1.5 h-1.5 bg-white rounded-full animate-bounce [animation-delay:300ms]" />
              </span>
              全链路优化中…
            </span>
          ) : (
            "🚀 一键生成点火"
          )}
        </button>
      </form>
    </div>
  );
}
