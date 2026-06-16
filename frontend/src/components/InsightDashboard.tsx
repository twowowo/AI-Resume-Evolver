"use client";

import { useMemo, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

export interface InsightItem {
  id: string;
  content: string;
  timestamp: number;
  /** 来源消息类型：AIMessage → AI 头脑风暴；其他 → 外部检索回执 */
  msgType: string;
}

interface Props {
  items: InsightItem[];
}

/** 安全渲染组件：捕获 ReactMarkdown 解析异常，降级为纯文本 */
function SafeMarkdown({ content }: { content: string }) {
  try {
    return (
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          // eslint-disable-next-line @typescript-eslint/no-explicit-any
          table: (p: any) => (
            <table className="w-full border-collapse border border-zinc-300 dark:border-zinc-600 my-2 text-[12px]" {...p} />
          ),
          th: (p: any) => (
            <th className="border border-zinc-300 dark:border-zinc-600 px-2 py-1 bg-zinc-100 dark:bg-zinc-800 font-semibold" {...p} />
          ),
          td: (p: any) => (
            <td className="border border-zinc-300 dark:border-zinc-600 px-2 py-1" {...p} />
          ),
        }}
      >
        {content}
      </ReactMarkdown>
    );
  } catch {
    return <pre className="text-xs whitespace-pre-wrap break-all">{content}</pre>;
  }
}

export default function InsightDashboard({ items }: Props) {
  const [expandedTools, setExpandedTools] = useState<Record<string, boolean>>({});

  const safeItems = useMemo(() => {
    try {
      return items;
    } catch {
      return [];
    }
  }, [items]);

  const toggleTool = (id: string) => {
    setExpandedTools((prev) => ({ ...prev, [id]: !prev[id] }));
  };

  if (safeItems.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center h-full text-center gap-3 p-6">
        <span className="text-4xl">📊</span>
        <p className="text-sm font-semibold text-zinc-500 dark:text-zinc-400">
          智脑洞察看板待命中
        </p>
        <p className="text-xs text-zinc-400 dark:text-zinc-500 max-w-sm">
          当 Agent 大脑输出包含表格数据、结构化分析或超长文本时，
          内容将自动同步至此处，提供全尺寸无死角阅览体验。
        </p>
      </div>
    );
  }

  return (
    <div className="h-full overflow-y-auto p-5">
      <div className="space-y-6">
        {safeItems.map((item, i) => {
          const isCurrentTurn = i === safeItems.length - 1;
          const isAIBrainstorm = item.msgType === "AIMessage";
          const isToolExpanded = expandedTools[item.id] === true;

          // ── 语义分流：AI 头脑风暴 vs 外部检索回执 ──
          if (isAIBrainstorm) {
            return (
              <div
                key={item.id}
                className={`overflow-hidden animate-in fade-in slide-in-from-bottom-2 ${
                  isCurrentTurn
                    ? "bg-gradient-to-r from-indigo-50/40 to-transparent dark:from-indigo-950/30 dark:to-transparent border-l-4 border-indigo-500 shadow-sm rounded-r-lg rounded-l-none"
                    : "rounded-xl border border-indigo-200 dark:border-indigo-800 bg-indigo-50/20 dark:bg-indigo-950/5"
                }`}
              >
                <div className={`px-4 py-2 border-b border-indigo-200 dark:border-indigo-800 flex items-center justify-between ${
                  isCurrentTurn
                    ? "bg-indigo-100/50 dark:bg-indigo-900/20"
                    : "bg-indigo-50/50 dark:bg-indigo-900/10"
                }`}>
                  <div className="flex items-center gap-2">
                    <span className="text-xs font-bold text-indigo-700 dark:text-indigo-300">
                      💡 AI 头脑风暴
                    </span>
                    {isCurrentTurn && (
                      <span className="text-[10px] px-1.5 py-0.5 rounded bg-indigo-500 text-white font-semibold animate-pulse">
                        ● CURRENT TURN
                      </span>
                    )}
                  </div>
                  <span className="text-[10px] text-indigo-400 dark:text-indigo-500">
                    {new Date(item.timestamp).toLocaleTimeString("zh-CN")}
                  </span>
                </div>
                {/* AI 头脑风暴：无条件全量展开，零截断，心流阅读 */}
                <div className="px-4 py-4 prose prose-sm dark:prose-invert max-w-none prose-headings:text-zinc-800 dark:prose-headings:text-zinc-100 prose-p:text-zinc-700 dark:prose-p:text-zinc-300 prose-table:text-xs prose-th:text-[11px] prose-td:text-[11px] prose-li:text-zinc-700 dark:prose-li:text-zinc-300 prose-code:text-[11px] prose-code:bg-zinc-100 dark:prose-code:bg-zinc-800 prose-code:px-1 prose-code:py-0.5 prose-code:rounded prose-pre:bg-zinc-100 dark:prose-pre:bg-zinc-800 prose-pre:text-[11px]">
                  <SafeMarkdown content={item.content} />
                </div>
              </div>
            );
          }

          // ── 外部检索回执：默认折叠，max-h-12 单行 + 渐变模糊 ──
          return (
            <div
              key={item.id}
              className={`overflow-hidden animate-in fade-in slide-in-from-bottom-2 ${
                isCurrentTurn
                  ? "bg-gradient-to-r from-emerald-50/30 to-transparent dark:from-emerald-950/20 dark:to-transparent border-l-4 border-emerald-500 shadow-sm rounded-r-lg rounded-l-none"
                  : "rounded-xl border border-amber-200 dark:border-amber-800 bg-amber-50/50 dark:bg-amber-950/10"
              }`}
            >
              <div className={`px-4 py-2 border-b border-amber-200 dark:border-amber-800 flex items-center justify-between ${
                isCurrentTurn
                  ? "bg-emerald-100/50 dark:bg-emerald-900/20"
                  : "bg-amber-100/50 dark:bg-amber-900/20"
              }`}>
                <div className="flex items-center gap-2">
                  <span className="text-xs font-bold text-amber-700 dark:text-amber-300">
                    🔍 智能洞察片段
                  </span>
                  {isCurrentTurn && (
                    <span className="text-[10px] px-1.5 py-0.5 rounded bg-emerald-500 text-white font-semibold animate-pulse">
                      ● CURRENT TURN
                    </span>
                  )}
                </div>
                <span className="text-[10px] text-amber-500 dark:text-amber-600">
                  {new Date(item.timestamp).toLocaleTimeString("zh-CN")}
                </span>
              </div>
              {/* 外部检索：默认折叠为 max-h-12 单行 */}
              <div className="relative">
                <div className={`px-4 py-3 prose prose-sm dark:prose-invert max-w-none prose-headings:text-zinc-800 dark:prose-headings:text-zinc-100 prose-p:text-zinc-700 dark:prose-p:text-zinc-300 prose-table:text-xs prose-th:text-[11px] prose-td:text-[11px] prose-li:text-zinc-700 dark:prose-li:text-zinc-300 prose-code:text-[11px] prose-code:bg-zinc-100 dark:prose-code:bg-zinc-800 prose-code:px-1 prose-code:py-0.5 prose-code:rounded prose-pre:bg-zinc-100 dark:prose-pre:bg-zinc-800 prose-pre:text-[11px] ${
                  isToolExpanded ? "" : "max-h-12 overflow-hidden"
                } transition-all duration-300`}>
                  <SafeMarkdown content={item.content} />
                </div>
                {!isToolExpanded && (
                  <div className="absolute bottom-0 left-0 right-0 h-10 bg-gradient-to-t from-white dark:from-zinc-950 via-white/70 dark:via-zinc-950/70 to-transparent pointer-events-none" />
                )}
              </div>
              <div className="px-4 pb-3 pt-1 flex justify-end">
                <button
                  onClick={() => toggleTool(item.id)}
                  className="text-[11px] font-medium text-blue-600 dark:text-blue-400 hover:text-blue-700 dark:hover:text-blue-300 transition-colors"
                >
                  {isToolExpanded ? "收起外部文献 ⬆️" : "点击展开外部文献 ⬇️"}
                </button>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
