"use client";

import { useMemo, useState, useEffect, useRef } from "react";
import type { NodeLog } from "@/hooks/useAgentStream";
import AgentCanvas, { extractSectionModifications, getCurrentSections, assembleMarkdown } from "./AgentCanvas";
import A4PaperPreview from "./A4PaperPreview";
import InsightDashboard, { type InsightItem } from "./InsightDashboard";

type RightTab = "canvas" | "insight";

interface Props {
  nodeLogs: NodeLog[];
}

/** 表格语法检测：内容中是否含有 |---|---| 或 | 列 | 列 | 模式 */
const TABLE_PATTERN = /\|.+\|/;

/** 超长文本阈值：超过此字符数视为洞察级长文 */
const LONG_TEXT_THRESHOLD = 300;

/**
 * 判断一条 NodeLog 是否包含"智脑洞察"级别的内容：
 * - 含 Markdown 表格语法
 * - 或内容超过长度阈值（排除 HumanMessage / ToolMessage 等短回执）
 */
function isInsightWorthy(log: NodeLog): boolean {
  const content = log.content ?? "";
  if (!content.trim()) return false;
  const hasTable = TABLE_PATTERN.test(content);
  const isLong = content.length > LONG_TEXT_THRESHOLD;
  return hasTable || isLong;
}

/** 从 nodeLogs 中提取洞察级内容项，携带 msgType 供右轴语义分流 */
function extractInsightItems(nodeLogs: NodeLog[]): InsightItem[] {
  return nodeLogs
    .filter(isInsightWorthy)
    .map((log) => ({
      id: log.id,
      content: log.content,
      timestamp: log.timestamp,
      msgType: log.msgType,
    }));
}

export default function AgentRightPanel({ nodeLogs }: Props) {
  const [activeTab, setActiveTab] = useState<RightTab>("canvas");
  const [a4Open, setA4Open] = useState(false);
  const prevInsightCountRef = useRef(0);

  const modifications = useMemo(() => extractSectionModifications(nodeLogs), [nodeLogs]);
  const sections = useMemo(() => getCurrentSections(modifications), [modifications]);
  const fullMarkdown = useMemo(() => assembleMarkdown(sections), [sections]);
  const hasAnyModification = modifications.length > 0;

  const insightItems = useMemo(() => extractInsightItems(nodeLogs), [nodeLogs]);

  // 当有新的洞察内容到达时，自动切换到洞察看板
  useEffect(() => {
    if (insightItems.length > prevInsightCountRef.current) {
      setActiveTab("insight");
    }
    prevInsightCountRef.current = insightItems.length;
  }, [insightItems.length]);

  const hasInsight = insightItems.length > 0;

  return (
    <div className="flex flex-col h-full bg-white dark:bg-black">
      {/* Tab 切换栏 + A4 按钮 */}
      <div className="flex-shrink-0 flex items-center justify-between px-4 py-2.5 border-b border-zinc-200 dark:border-zinc-800">
        <div className="flex rounded-lg bg-zinc-100 dark:bg-zinc-900 p-0.5">
          <button
            onClick={() => setActiveTab("canvas")}
            className={`px-4 py-1.5 text-xs font-semibold rounded-md transition-all ${
              activeTab === "canvas"
                ? "bg-indigo-600 text-white shadow-sm"
                : "text-zinc-600 dark:text-zinc-400 hover:text-zinc-900 dark:hover:text-zinc-200"
            }`}
          >
            📄 简历画布
          </button>
          <button
            onClick={() => setActiveTab("insight")}
            className={`px-4 py-1.5 text-xs font-semibold rounded-md transition-all relative ${
              activeTab === "insight"
                ? "bg-amber-600 text-white shadow-sm"
                : "text-zinc-600 dark:text-zinc-400 hover:text-zinc-900 dark:hover:text-zinc-200"
            }`}
          >
            📊 智脑洞察看板
            {hasInsight && activeTab !== "insight" && (
              <span className="absolute -top-0.5 -right-0.5 w-2 h-2 bg-amber-500 rounded-full animate-pulse" />
            )}
          </button>
        </div>

        {/* A4 画板按钮 */}
        <button
          onClick={() => setA4Open(true)}
          disabled={!hasAnyModification}
          className="px-3 py-1.5 text-xs font-semibold rounded-lg bg-indigo-600 text-white hover:bg-indigo-700 disabled:opacity-30 transition-colors"
        >
          A4 画板
        </button>
      </div>

      {/* 内容区域 */}
      <div className="flex-1 overflow-hidden">
        {activeTab === "canvas" ? (
          <AgentCanvas nodeLogs={nodeLogs} hideHeader />
        ) : (
          <InsightDashboard items={insightItems} />
        )}
      </div>

      {/* A4 画板 Modal */}
      <A4PaperPreview
        open={a4Open}
        onClose={() => setA4Open(false)}
        markdownContent={fullMarkdown}
        title="Agent 微创后简历预览"
        visualPayload={null}
      />
    </div>
  );
}
