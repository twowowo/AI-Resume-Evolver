"use client";

import { useState, useRef, type FormEvent } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { useAgentStream, type NodeLog } from "@/hooks/useAgentStream";
import { useOCRParser } from "@/hooks/useOCRParser";

// ── Props：支持受控模式与自管理模式 ──

interface AgentConsoleProps {
  nodeLogs?: NodeLog[];
  isStreaming?: boolean;
  isThinking?: boolean;
  error?: string | null;
  onSubmit?: (query: string) => void;
  onAbort?: () => void;
  subtitle?: string;
}

/** v4.6 物理屏蔽过滤器：ToolMessage + ToolCall 帧不参与渲染 */
function shouldRenderLog(log: NodeLog): boolean {
  if (log.msgType === "ToolMessage") return false;
  if (log.toolCalls && log.toolCalls.length > 0) return false;
  return true;
}

/** 检测是否有最终 AI 回复完成 */
function hasCompletionReply(logs: NodeLog[], isStreaming: boolean): boolean {
  if (isStreaming) return false;
  const lastLog = logs[logs.length - 1];
  return !!(
    lastLog &&
    (lastLog.msgType === "AIMessage" || lastLog.nodeName === "circuit_breaker") &&
    lastLog.content?.trim()
  );
}

export default function AgentConsole({
  nodeLogs: extLogs,
  isStreaming: extStreaming,
  isThinking: extThinking,
  error: extError,
  onSubmit,
  onAbort,
  subtitle,
}: AgentConsoleProps) {
  const internal = useAgentStream();
  const isControlled = !!onSubmit;

  const nodeLogs = isControlled ? (extLogs ?? []) : internal.nodeLogs;
  const isStreaming = isControlled ? (extStreaming ?? false) : internal.isStreaming;
  const isThinking = isControlled ? (extThinking ?? false) : internal.isThinking;
  const error = isControlled ? (extError ?? null) : internal.error;

  const [input, setInput] = useState("");
  const fileInputRef = useRef<HTMLInputElement>(null);

  // ── v4.6 共享 OCR 解析 Hook ──
  const { isAnalyzing, status: ocrStatus, handlePaste, handleFileSelect, resetStatus: resetOCR } = useOCRParser();

  // ── 过滤后的可见消息 ──
  const visibleLogs = nodeLogs.filter(shouldRenderLog);
  const showCompletion = hasCompletionReply(nodeLogs, isStreaming || isThinking);

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault();
    if (!input.trim() || isStreaming || isAnalyzing) return;
    if (isControlled) {
      onSubmit!(input.trim());
    } else {
      internal.startStream(input.trim());
    }
    setInput("");
    resetOCR();
  };

  const handleAbort = () => {
    if (isControlled && onAbort) {
      onAbort();
    } else {
      internal.abort();
    }
  };

  // ── Ctrl+V 粘贴拦截：图片 → OCR → 注入输入框 ──
  const onPaste = async (e: React.ClipboardEvent<HTMLTextAreaElement>) => {
    const text = await handlePaste(e);
    if (text) {
      const injection = `[已自动识别并挂载简历内容]\n以下是从上传图片中提取的简历信息，请基于此内容进行优化：\n\n${text}`;
      setInput((prev) => (prev ? `${prev}\n\n${injection}` : injection));
    }
  };

  // ── 📎 文件上传通道：提取 File → OCR → 注入输入框 ──
  const onFileChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const result = await handleFileSelect(e);
    if (result?.text) {
      const fileName = result.file.name;
      const injection = `[已自动识别并挂载简历内容]\n以下是从上传图片中提取的简历信息，请基于此内容进行优化：\n\n${result.text}`;
      setInput((prev) => (prev ? `${prev}\n\n${injection}` : injection));
      // 成功 toast 由 hook 内部管理，此处额外追加文件名信息
    }
  };

  return (
    <div className="flex flex-col h-full border-r border-zinc-200 dark:border-zinc-800 bg-zinc-50 dark:bg-zinc-950">
      {/* 标题栏 */}
      <div className="px-4 py-3 border-b border-zinc-200 dark:border-zinc-800 bg-white dark:bg-black">
        <h2 className="text-sm font-bold tracking-wide text-zinc-800 dark:text-zinc-100">
          🤖 AI 简历智脑
        </h2>
        <p className="text-xs text-zinc-500 mt-0.5">
          {subtitle ?? "Ctrl+V 粘贴图片 · 输入指令 · 一键优化"}
        </p>
      </div>

      {/* ── OCR 状态 Toast ── */}
      {ocrStatus && (
        <div
          className={`mx-4 mt-3 px-3 py-2 rounded-lg text-xs font-medium flex items-center justify-between gap-2 transition-all ${
            ocrStatus.type === "loading"
              ? "bg-blue-50 dark:bg-blue-950/30 border border-blue-200 dark:border-blue-700 text-blue-700 dark:text-blue-300"
              : ocrStatus.type === "success"
              ? "bg-emerald-50 dark:bg-emerald-950/30 border border-emerald-200 dark:border-emerald-700 text-emerald-700 dark:text-emerald-300"
              : "bg-red-50 dark:bg-red-950/30 border border-red-200 dark:border-red-700 text-red-700 dark:text-red-300"
          }`}
        >
          <span className="flex items-center gap-2">
            {ocrStatus.type === "loading" && (
              <span className="flex gap-0.5">
                <span className="w-1.5 h-1.5 bg-blue-500 rounded-full animate-bounce [animation-delay:0ms]" />
                <span className="w-1.5 h-1.5 bg-blue-500 rounded-full animate-bounce [animation-delay:150ms]" />
                <span className="w-1.5 h-1.5 bg-blue-500 rounded-full animate-bounce [animation-delay:300ms]" />
              </span>
            )}
            {ocrStatus.message}
          </span>
          {ocrStatus.type === "error" && (
            <button
              onClick={resetOCR}
              className="text-red-400 hover:text-red-600 dark:hover:text-red-200 transition-colors shrink-0"
            >
              ✕
            </button>
          )}
        </div>
      )}

      {/* ── 对话区：渲染用户提问 + AI 回复 + 进度状态 ── */}
      <div className="flex-1 overflow-y-auto px-4 py-4 space-y-4">
        {/* 空状态 */}
        {visibleLogs.length === 0 && !isStreaming && !isThinking && (
          <div className="flex flex-col items-center justify-center h-full text-center gap-3">
            <span className="text-4xl">📝</span>
            <p className="text-sm font-semibold text-zinc-500 dark:text-zinc-400">
              开始优化您的简历
            </p>
            <p className="text-xs text-zinc-400 dark:text-zinc-500 max-w-xs">
              Ctrl+V 粘贴简历截图，或直接输入修改意见，AI 智脑将自动完成优化。
            </p>
          </div>
        )}

        {/* 逐条渲染可见消息 */}
        {visibleLogs.map((log) => {
          // HumanMessage — 用户输入气泡（右对齐，蓝色）
          if (log.msgType === "HumanMessage" && log.content?.trim()) {
            return (
              <div key={log.id} className="flex justify-end animate-in fade-in slide-in-from-bottom-2">
                <div className="max-w-[85%] rounded-2xl rounded-br-md px-4 py-2.5 bg-indigo-600 text-white shadow-sm">
                  <p className="text-sm leading-relaxed whitespace-pre-wrap break-words">
                    {log.content.length > 500
                      ? log.content.slice(0, 500) + "\n\n... (内容已截断预览)"
                      : log.content}
                  </p>
                  <span className="block mt-1 text-[10px] text-indigo-200 text-right">
                    {new Date(log.timestamp).toLocaleTimeString("zh-CN")}
                  </span>
                </div>
              </div>
            );
          }

          // AIMessage — LLM 回复气泡（左对齐，ReactMarkdown 渲染）
          if (log.msgType === "AIMessage" && log.content?.trim()) {
            return (
              <div key={log.id} className="flex items-start gap-3 animate-in fade-in slide-in-from-bottom-2">
                <div className="w-8 h-8 rounded-full bg-indigo-100 dark:bg-indigo-900/40 flex items-center justify-center shrink-0">
                  <span className="text-sm">🧠</span>
                </div>
                <div className="flex-1 min-w-0 max-w-[85%]">
                  <div className="rounded-2xl rounded-bl-md px-4 py-3 bg-white dark:bg-zinc-900 border border-zinc-200 dark:border-zinc-800 shadow-sm">
                    <div className="prose prose-sm dark:prose-invert max-w-none prose-headings:text-sm prose-headings:font-bold prose-p:text-sm prose-li:text-sm prose-ul:my-1 prose-ol:my-1 prose-p:my-1">
                      <ReactMarkdown remarkPlugins={[remarkGfm]}>
                        {log.content}
                      </ReactMarkdown>
                    </div>
                  </div>
                  <span className="block mt-0.5 ml-1 text-[10px] text-zinc-400 dark:text-zinc-500">
                    {new Date(log.timestamp).toLocaleTimeString("zh-CN")}
                  </span>
                </div>
              </div>
            );
          }

          // circuit_breaker 系统通知
          if (log.nodeName === "circuit_breaker" && log.content?.trim()) {
            return (
              <div key={log.id} className="flex items-start gap-3 animate-in fade-in">
                <div className="w-8 h-8 rounded-full bg-amber-100 dark:bg-amber-900/40 flex items-center justify-center shrink-0">
                  <span className="text-sm">⚠️</span>
                </div>
                <div className="flex-1 min-w-0 max-w-[85%]">
                  <div className="rounded-2xl rounded-bl-md px-4 py-3 bg-amber-50 dark:bg-amber-950/20 border border-amber-200 dark:border-amber-800">
                    <div className="prose prose-sm dark:prose-invert max-w-none">
                      <ReactMarkdown remarkPlugins={[remarkGfm]}>
                        {log.content}
                      </ReactMarkdown>
                    </div>
                  </div>
                </div>
              </div>
            );
          }

          // 其他有内容的消息（兜底渲染）
          if (log.content?.trim()) {
            return (
              <div key={log.id} className="flex items-start gap-3 animate-in fade-in">
                <div className="w-8 h-8 rounded-full bg-zinc-100 dark:bg-zinc-800 flex items-center justify-center shrink-0">
                  <span className="text-xs text-zinc-500">{log.nodeName.slice(0, 2)}</span>
                </div>
                <div className="flex-1 min-w-0 max-w-[85%]">
                  <div className="rounded-2xl rounded-bl-md px-4 py-2 bg-white dark:bg-zinc-900 border border-zinc-200 dark:border-zinc-800 shadow-sm">
                    <p className="text-xs text-zinc-600 dark:text-zinc-400 whitespace-pre-wrap break-words">
                      {log.content.slice(0, 300)}
                    </p>
                  </div>
                </div>
              </div>
            );
          }

          return null;
        })}

        {/* 流式进行中的思考进度指示器 */}
        {(isStreaming || isThinking) && (
          <div className="flex items-start gap-3 animate-in fade-in">
            <div className="w-8 h-8 rounded-full bg-indigo-100 dark:bg-indigo-900/40 flex items-center justify-center shrink-0">
              <span className="text-sm">🧠</span>
            </div>
            <div className="flex-1 min-w-0">
              <div className="rounded-2xl rounded-bl-md px-4 py-3 bg-white dark:bg-zinc-900 border border-zinc-200 dark:border-zinc-800 shadow-sm">
                <div className="flex items-center gap-2 mb-2">
                  <span className="flex gap-0.5">
                    <span className="w-1.5 h-1.5 bg-indigo-500 rounded-full animate-bounce [animation-delay:0ms]" />
                    <span className="w-1.5 h-1.5 bg-indigo-500 rounded-full animate-bounce [animation-delay:150ms]" />
                    <span className="w-1.5 h-1.5 bg-indigo-500 rounded-full animate-bounce [animation-delay:300ms]" />
                  </span>
                  <span className="text-xs font-semibold text-indigo-600 dark:text-indigo-400">
                    LLM正在思考请稍后
                  </span>
                </div>
                <p className="text-xs text-zinc-500 dark:text-zinc-400">
                  模型推理进行中，请耐心等待...
                </p>
              </div>
            </div>
          </div>
        )}

        {/* 完成标记 */}
        {showCompletion && (
          <div className="flex items-start gap-3 animate-in fade-in">
            <div className="w-8 h-8 rounded-full bg-emerald-100 dark:bg-emerald-900/40 flex items-center justify-center shrink-0">
              <span className="text-sm">✅</span>
            </div>
            <div className="rounded-2xl rounded-bl-md px-4 py-3 bg-emerald-50 dark:bg-emerald-950/20 border border-emerald-200 dark:border-emerald-800 shadow-sm">
              <p className="text-sm font-semibold text-emerald-700 dark:text-emerald-300">
                LLM思考完成，仅供参考
              </p>
              <p className="text-xs text-emerald-600 dark:text-emerald-400 mt-1">
                以上内容由 AI 自动生成，右侧画布可预览修改详情，或点击 A4 画板查看最终效果。
              </p>
            </div>
          </div>
        )}

        {/* 错误提示 */}
        {error && (
          <div className="flex items-start gap-3 animate-in fade-in">
            <div className="w-8 h-8 rounded-full bg-red-100 dark:bg-red-900/40 flex items-center justify-center shrink-0">
              <span className="text-sm">⚠️</span>
            </div>
            <div className="rounded-2xl rounded-bl-md px-4 py-3 bg-red-50 dark:bg-red-950/20 border border-red-200 dark:border-red-800">
              <p className="text-sm text-red-700 dark:text-red-300">{error}</p>
            </div>
          </div>
        )}
      </div>

      {/* 底部输入区 */}
      <form
        onSubmit={handleSubmit}
        className="border-t border-zinc-200 dark:border-zinc-800 p-3 bg-white dark:bg-black"
      >
        <div className="flex gap-2 items-end">
          {/* 附件上传按钮 */}
          <input
            ref={fileInputRef}
            type="file"
            accept="image/png,image/jpeg,image/webp,image/bmp"
            onChange={onFileChange}
            className="hidden"
            id="agent-file-upload"
          />
          <button
            type="button"
            onClick={() => fileInputRef.current?.click()}
            disabled={isStreaming || isAnalyzing}
            className="shrink-0 w-10 h-10 flex items-center justify-center rounded-lg border border-zinc-300 dark:border-zinc-700 bg-zinc-50 dark:bg-zinc-900 text-zinc-500 dark:text-zinc-400 hover:bg-zinc-100 dark:hover:bg-zinc-800 hover:text-indigo-600 dark:hover:text-indigo-400 disabled:opacity-40 transition-colors"
            title="上传简历图片自动识别（也支持 Ctrl+V 直接粘贴）"
          >
            {isAnalyzing ? (
              <span className="animate-spin text-sm">⏳</span>
            ) : (
              <span className="text-lg">📎</span>
            )}
          </button>

          {/* 多模态输入区：textarea + 粘贴监听 + Loading Spinner */}
          <div className="flex-1 relative">
            <textarea
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onPaste={onPaste}
              placeholder={
                isControlled
                  ? "请先上传一份简历噢亲"
                  : "输入修改意见，或 Ctrl+V 粘贴简历截图..."
              }
              disabled={isStreaming}
              rows={2}
              className="w-full px-3 py-2.5 text-sm rounded-lg border border-zinc-300 dark:border-zinc-700 bg-white dark:bg-zinc-900 text-zinc-900 dark:text-zinc-100 placeholder-zinc-400 focus:outline-none focus:ring-2 focus:ring-indigo-500 disabled:opacity-50 resize-none"
            />
            {/* 识别中 Loading Spinner */}
            {isAnalyzing && (
              <div className="absolute right-3 top-1/2 -translate-y-1/2 flex items-center gap-1.5 px-2 py-1 rounded-full bg-blue-100 dark:bg-blue-900/40 text-xs font-medium text-blue-700 dark:text-blue-300">
                <span className="w-3 h-3 border-2 border-blue-500 border-t-transparent rounded-full animate-spin" />
                正在识别中...
              </div>
            )}
          </div>

          {/* 发送/中断按钮 */}
          {isStreaming ? (
            <button
              type="button"
              onClick={handleAbort}
              className="shrink-0 px-4 py-2.5 text-sm font-semibold rounded-lg bg-red-600 text-white hover:bg-red-700 transition-colors"
            >
              中断
            </button>
          ) : (
            <button
              type="submit"
              disabled={!input.trim() || isAnalyzing}
              className="shrink-0 px-4 py-2.5 text-sm font-semibold rounded-lg bg-indigo-600 text-white hover:bg-indigo-700 disabled:opacity-40 transition-colors"
            >
              发送
            </button>
          )}
        </div>
      </form>
    </div>
  );
}
