"use client";

import { useMemo, useState } from "react";
import { diffWords } from "diff";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import type { NodeLog } from "@/hooks/useAgentStream";
import A4PaperPreview from "./A4PaperPreview";

// ── 类型定义 ──

export interface SectionModification {
  section: string;
  /** 该章节在此次修改前的内容；首次修改时为 null */
  previousContent: string | null;
  newContent: string;
  timestamp: number;
  logId: string;
}

interface Props {
  nodeLogs: NodeLog[];
  hideHeader?: boolean;
}

// ── 常量 ──

const SECTION_LABELS: Record<string, string> = {
  basic: "个人基础信息",
  skills: "核心技术栈",
  projects: "项目经历",
  campus: "校园经历",
};

const SECTION_ORDER = ["basic", "skills", "projects", "campus"];

// ── 导出工具函数 ──

/**
 * 从 nodeLogs 中按时间顺序提取所有 patch_resume_tool 调用，
 * 追踪每个章节的演进历史，记录每次修改的 before/after。
 */
export function extractSectionModifications(
  nodeLogs: NodeLog[]
): SectionModification[] {
  try {
    const modifications: SectionModification[] = [];
    const currentContent: Record<string, string> = {};

    for (const log of nodeLogs) {
      for (const tc of log.toolCalls) {
        if (tc.name === "patch_resume_tool" && tc.args) {
          const section = tc.args.section as string | undefined;
          const content = tc.args.new_content as string | undefined;
          if (section && content) {
            const prev = currentContent[section] ?? null;
            modifications.push({
              section,
              previousContent: prev,
              newContent: content,
              timestamp: log.timestamp,
              logId: log.id,
            });
            currentContent[section] = content;
          }
        }
      }
    }

    return modifications;
  } catch {
    return [];
  }
}

/** 从修改记录中提取当前最新的四章节快照 */
export function getCurrentSections(
  modifications: SectionModification[]
): Record<string, string> {
  const sections: Record<string, string> = {};
  for (const mod of modifications) {
    sections[mod.section] = mod.newContent;
  }
  return sections;
}

/** 将四章节拼装为完整 Markdown（供 A4 预览使用） */
export function assembleMarkdown(sections: Record<string, string>): string {
  const parts: string[] = ["# 原始简历底座\n"];

  for (const key of SECTION_ORDER) {
    const label = SECTION_LABELS[key] ?? key;
    const content = sections[key];
    if (content) {
      parts.push(`## ${label}\n${content}`);
    }
  }

  return parts.length > 1 ? parts.join("\n\n") : "*暂无简历数据*";
}

// ── 词级 Diff 热力图组件 ──

function DiffHeatmap({
  previous,
  current,
}: {
  previous: string;
  current: string;
}) {
  const changes = useMemo(() => {
    try {
      return diffWords(previous, current);
    } catch {
      // 解析异常降级：返回整段作为未变更文本
      return [{ value: current, added: undefined, removed: undefined, count: undefined }];
    }
  }, [previous, current]);

  return (
    <div className="text-xs leading-relaxed whitespace-pre-wrap break-all">
      {changes.map((change, i) => {
        if (change.removed) {
          return (
            <del
              key={i}
              className="text-red-600 dark:text-red-400 bg-red-100 dark:bg-red-950/40 line-through px-0.5 rounded"
            >
              {change.value}
            </del>
          );
        }
        if (change.added) {
          return (
            <ins
              key={i}
              className="text-emerald-600 dark:text-emerald-400 bg-emerald-100 dark:bg-emerald-950/40 font-semibold no-underline px-0.5 rounded"
            >
              {change.value}
            </ins>
          );
        }
        return <span key={i}>{change.value}</span>;
      })}
    </div>
  );
}

// ── 组件主体 ──

export default function AgentCanvas({ nodeLogs, hideHeader = false }: Props) {
  const [a4Open, setA4Open] = useState(false);

  const modifications = useMemo(() => {
    try {
      return extractSectionModifications(nodeLogs);
    } catch {
      return [];
    }
  }, [nodeLogs]);

  const currentSections = useMemo(() => {
    try {
      return getCurrentSections(modifications);
    } catch {
      return {};
    }
  }, [modifications]);

  const fullMarkdown = useMemo(() => {
    try {
      return assembleMarkdown(currentSections);
    } catch {
      return "*暂无简历数据*";
    }
  }, [currentSections]);

  const modifiedKeys = [
    ...new Set(modifications.map((m) => m.section)),
  ];
  const hasAnyModification = modifiedKeys.length > 0;

  return (
    <div className="flex flex-col h-full bg-white dark:bg-black">
      {/* 标题栏：仅在独立模式（非嵌入）下渲染 */}
      {!hideHeader && (
        <div className="px-4 py-3 border-b border-zinc-200 dark:border-zinc-800 flex items-center justify-between">
          <div>
            <h2 className="text-sm font-bold tracking-wide text-zinc-800 dark:text-zinc-100">
              Agent 简历画布
            </h2>
            <p className="text-xs text-zinc-500 mt-0.5">
              {hasAnyModification
                ? `已微创修改 ${modifiedKeys.length} 个章节，共 ${modifications.length} 次手术`
                : "等待 Agent 下达修改指令..."}
            </p>
          </div>
          <button
            onClick={() => setA4Open(true)}
            disabled={!hasAnyModification}
            className="px-3 py-1.5 text-xs font-semibold rounded-lg bg-indigo-600 text-white hover:bg-indigo-700 disabled:opacity-30 transition-colors"
          >
            A4 画板
          </button>
        </div>
      )}

      {/* 画布主区域 */}
      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        {!hasAnyModification && (
          <div className="flex flex-col items-center justify-center h-full text-center gap-3">
            <span className="text-4xl">🎨</span>
            <p className="text-sm font-semibold text-zinc-500 dark:text-zinc-400">
              Agent 画布就绪
            </p>
            <p className="text-xs text-zinc-400 dark:text-zinc-500 max-w-xs">
              在左侧 Agent 大脑控制台中输入全局修改指令（如"重写项目经历"），
              大脑将通过微创手术刀精准修改简历章节，修改结果将实时渲染在此画布中。
            </p>
            <div className="mt-2 grid grid-cols-2 gap-2 text-[10px] text-zinc-400">
              {Object.entries(SECTION_LABELS).map(([key, label]) => (
                <div
                  key={key}
                  className="px-2 py-1.5 rounded-md border border-dashed border-zinc-300 dark:border-zinc-700"
                >
                  {label}
                  <span className="block text-zinc-300 dark:text-zinc-600">
                    待修改
                  </span>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* 已修改章节卡片 —— 每条修改独立一张卡，视觉分代 */}
        {modifications.map((mod, i) => {
          const label = SECTION_LABELS[mod.section] ?? mod.section;
          const isFirstMod = mod.previousContent === null;
          const isCurrentTurn = i === modifications.length - 1;

          return (
            <div
              key={mod.logId}
              className={`overflow-hidden animate-in fade-in slide-in-from-bottom-2 ${
                isCurrentTurn
                  ? "bg-gradient-to-r from-emerald-50/30 to-transparent dark:from-emerald-950/20 dark:to-transparent border-l-4 border-emerald-500 shadow-sm rounded-r-lg rounded-l-none"
                  : "rounded-xl border border-zinc-200 dark:border-zinc-700 bg-transparent"
              }`}
            >
              {/* 卡片头部 */}
              <div className={`px-3 py-2 border-b border-zinc-200 dark:border-zinc-700 flex items-center justify-between ${
                isCurrentTurn
                  ? "bg-emerald-100/50 dark:bg-emerald-900/20"
                  : "bg-zinc-100 dark:bg-zinc-900"
              }`}>
                <div className="flex items-center gap-2">
                  <span className="text-xs font-bold text-zinc-700 dark:text-zinc-300">
                    {isFirstMod ? `初始版本` : `微创手术`}
                    {" · "}
                    {label}
                  </span>
                  {isFirstMod && (
                    <span className="text-[10px] px-1.5 py-0.5 rounded bg-blue-100 dark:bg-blue-900/40 text-blue-600 dark:text-blue-400 font-semibold">
                      NEW
                    </span>
                  )}
                  {!isFirstMod && (
                    <span className="text-[10px] px-1.5 py-0.5 rounded bg-amber-100 dark:bg-amber-900/40 text-amber-600 dark:text-amber-400 font-semibold">
                      DIFF
                    </span>
                  )}
                  {isCurrentTurn && (
                    <span className="text-[10px] px-1.5 py-0.5 rounded bg-emerald-500 text-white font-semibold animate-pulse">
                      ● CURRENT TURN
                    </span>
                  )}
                </div>
                <span className="text-[10px] text-zinc-400">
                  {new Date(mod.timestamp).toLocaleTimeString("zh-CN")}
                </span>
              </div>

              {/* 卡片内容：首次修改 → 全量 ReactMarkdown 展示；后续修改 → 三栏对比 */}
              {isFirstMod ? (
                <div className="px-4 py-3 text-sm text-zinc-700 dark:text-zinc-300 leading-relaxed">
                  <ReactMarkdown
                    remarkPlugins={[remarkGfm]}
                    components={{
                      // eslint-disable-next-line @typescript-eslint/no-explicit-any
                      table: (p: any) => (
                        <table
                          className="w-full border-collapse border border-zinc-300 dark:border-zinc-600 my-1 text-[12px]"
                          {...p}
                        />
                      ),
                      th: (p: any) => (
                        <th
                          className="border border-zinc-300 dark:border-zinc-600 px-2 py-1 bg-zinc-100 dark:bg-zinc-800 font-semibold"
                          {...p}
                        />
                      ),
                      td: (p: any) => (
                        <td
                          className="border border-zinc-300 dark:border-zinc-600 px-2 py-1"
                          {...p}
                        />
                      ),
                      p: (p: any) => (
                        <p className="my-0.5" {...p} />
                      ),
                      ul: (p: any) => (
                        <ul className="list-disc pl-4 my-0.5 space-y-0" {...p} />
                      ),
                      ol: (p: any) => (
                        <ol className="list-decimal pl-4 my-0.5 space-y-0" {...p} />
                      ),
                      code: (p: any) => {
                        const {
                          className,
                          children,
                          ...rest
                        } = p as {
                          className?: string;
                          children?: React.ReactNode;
                          [k: string]: unknown;
                        };
                        const isInline = !className?.includes("language-");
                        if (isInline) {
                          return (
                            <code
                              className="px-1 py-0.5 bg-zinc-200 dark:bg-zinc-700 rounded text-[11px] font-mono"
                              {...rest}
                            >
                              {children}
                            </code>
                          );
                        }
                        return (
                          <pre className="my-1 p-2 bg-zinc-100 dark:bg-zinc-800 rounded overflow-x-auto text-[11px] font-mono">
                            <code {...rest}>{children}</code>
                          </pre>
                        );
                      },
                    }}
                  >
                    {mod.newContent}
                  </ReactMarkdown>
                </div>
              ) : (
                /* ── Trae 级三栏对比：术前 / 术后 / 词级热力图 ── */
                <div className="divide-y divide-zinc-100 dark:divide-zinc-800">
                  {/* 第一栏：❌ 术前底座 — 红色淡化遮罩 */}
                  <div className="bg-red-50/40 dark:bg-red-950/15">
                    <div className="px-3 py-1.5 text-[11px] font-semibold text-red-600 dark:text-red-400 flex items-center gap-1.5">
                      <span>❌</span> 术前底座
                    </div>
                    <div className="px-3 pb-3 text-xs leading-relaxed text-red-700 dark:text-red-300 whitespace-pre-wrap break-all font-mono">
                      {mod.previousContent}
                    </div>
                  </div>

                  {/* 第二栏：✅ 术后演进 — 绿色背景高亮注入 */}
                  <div className="bg-emerald-50/40 dark:bg-emerald-950/15">
                    <div className="px-3 py-1.5 text-[11px] font-semibold text-emerald-600 dark:text-emerald-400 flex items-center gap-1.5">
                      <span>✅</span> 术后演进
                    </div>
                    <div className="px-3 pb-3 text-xs leading-relaxed text-emerald-700 dark:text-emerald-300 whitespace-pre-wrap break-all font-mono">
                      {mod.newContent}
                    </div>
                  </div>

                  {/* 第三栏：📊 词级变更热力图 — <del>/<ins> 精准标注 */}
                  <div className="bg-zinc-50 dark:bg-zinc-900/30">
                    <div className="px-3 py-1.5 text-[11px] font-semibold text-zinc-500 dark:text-zinc-400 flex items-center gap-1.5">
                      <span>📊</span> 词级变更热力图
                    </div>
                    <div className="px-3 pb-3">
                      <DiffHeatmap
                        previous={mod.previousContent!}
                        current={mod.newContent}
                      />
                    </div>
                  </div>
                </div>
              )}
            </div>
          );
        })}

        {/* 综合提示 */}
        {hasAnyModification && (
          <p className="text-[10px] text-zinc-400 text-center pt-2">
            以上为 Agent 在本次会话中所做的所有微创手术修改摘要。
            MySQL 中的最新简历底座已同步就位。
          </p>
        )}
      </div>

      {/* A4 画板 Modal */}
      <A4PaperPreview
        open={a4Open}
        onClose={() => setA4Open(false)}
        markdownContent={fullMarkdown}
        title="Agent 微创后简历预览"
      />
    </div>
  );
}
