"use client";

import { useState, useMemo } from "react";
import { diffLines, type Change } from "diff";
import type { RadarScores, StressTestQuestion, PipelineStreamState, DiagnosisData } from "@/types/sse";
import A4PaperPreview from "./A4PaperPreview";

interface PipelinePanelProps {
  state: PipelineStreamState;
  isStreaming: boolean;
  originalResume: string;
  isGenerated: boolean;
}

export default function PipelinePanel({
  state,
  isStreaming,
  originalResume,
  isGenerated,
}: PipelinePanelProps) {
  const [a4Open, setA4Open] = useState(false);

  // ── Diff 计算 ──
  const diffResult = useMemo<Change[]>(() => {
    if (!originalResume || !state.optimizedText) return [];
    return diffLines(originalResume, state.optimizedText);
  }, [originalResume, state.optimizedText]);

  // ── 雷达图数据 ──
  const radar: RadarScores | null =
    state.optimizedRadar ?? state.originalRadar;

  // ── 阶段判定 ──
  const hasResult =
    state.phase === "resume_stream" ||
    state.phase === "final" ||
    state.phase === "done";

  return (
    <div className="flex flex-col h-full bg-white dark:bg-black">
      {/* 顶部工具栏 */}
      <div className="px-4 py-3 border-b border-zinc-200 dark:border-zinc-800 flex items-center justify-between">
        <div>
          <h2 className="text-sm font-bold tracking-wide text-zinc-800 dark:text-zinc-100">
            📊 简历优化看板
          </h2>
          <p className="text-xs text-zinc-500 mt-0.5">
            {isStreaming
              ? "⏳ 全链路流式生成中..."
              : isGenerated
              ? state.circuitBreakerTriggered
                ? "⚠️ 优化完成 · 技术栈差距较大，建议针对性提升"
                : `✅ 优化完成 · 提升 +${state.scoreImprovement} 分`
              : hasResult
              ? state.circuitBreakerTriggered
                ? "⚠️ 技术栈差距较大"
                : `提升 +${state.scoreImprovement} 分`
              : "等待左侧输入点火..."}
          </p>
        </div>
        <div className="flex items-center gap-2">
          {/* 完成标记 */}
          {isGenerated && (
            <span className="px-3 py-1 text-xs font-semibold text-emerald-600 dark:text-emerald-400 bg-emerald-50 dark:bg-emerald-950/30 border border-emerald-200 dark:border-emerald-800 rounded-full shadow-sm">
              ✔ 生成完成
            </span>
          )}
          {/* A4 画板按钮 */}
          <button
            onClick={() => setA4Open(true)}
            disabled={!state.optimizedText}
            className="px-3 py-1.5 text-xs font-semibold rounded-lg bg-indigo-600 text-white hover:bg-indigo-700 disabled:opacity-30 transition-colors"
          >
            A4 画板
          </button>
        </div>
      </div>

      {/* 主内容区 */}
      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        {/* ── 流式加载指示器 ── */}
        {isStreaming && state.phase === "idle" && (
          <div className="flex items-center justify-center py-12">
            <div className="flex items-center gap-3 text-blue-600 dark:text-blue-400">
              <span className="text-lg">⚡</span>
              <span className="text-sm font-semibold">全链路引擎点火中...</span>
              <span className="flex gap-0.5">
                <span className="w-1.5 h-1.5 bg-blue-500 rounded-full animate-bounce [animation-delay:0ms]" />
                <span className="w-1.5 h-1.5 bg-blue-500 rounded-full animate-bounce [animation-delay:150ms]" />
                <span className="w-1.5 h-1.5 bg-blue-500 rounded-full animate-bounce [animation-delay:300ms]" />
              </span>
            </div>
          </div>
        )}

        {/* ── 雷达图 ── */}
        {radar && (
          <div className="rounded-xl border border-zinc-200 dark:border-zinc-800 p-4">
            <h3 className="text-xs font-bold text-zinc-600 dark:text-zinc-400 mb-3">
              6-3-1 雷达指标 {state.optimizedRadar ? "(终评)" : "(初筛)"}
            </h3>
            <div className="grid grid-cols-3 gap-3">
              <ScoreBar
                label="JD 匹配"
                score={radar.jd_matching_score}
                max={60}
                color="bg-emerald-500"
              />
              <ScoreBar
                label="STAR 业绩"
                score={radar.star_perf_score}
                max={30}
                color="bg-amber-500"
              />
              <ScoreBar
                label="动词质量"
                score={radar.action_verbs_score}
                max={10}
                color="bg-rose-500"
              />
            </div>
            <div className="mt-3 text-center">
              <span className="text-2xl font-bold text-zinc-800 dark:text-zinc-100">
                {radar.total_score}
              </span>
              <span className="text-sm text-zinc-500"> / 100</span>
              {state.circuitBreakerTriggered ? (
                <span className="ml-2 text-sm font-semibold text-amber-600 dark:text-amber-400">
                  ⚠️ 熔断
                </span>
              ) : state.scoreImprovement > 0 && state.displayScoreChange ? (
                <span className="ml-2 text-sm font-semibold text-emerald-600 dark:text-emerald-400">
                  +{state.scoreImprovement}
                </span>
              ) : null}
            </div>

            {/* v5.4 信任熔断提示卡 */}
            {state.circuitBreakerTriggered && (
              <div className="mt-3 rounded-lg border border-amber-300 dark:border-amber-700 bg-amber-50 dark:bg-amber-950/30 p-3 animate-in fade-in">
                <div className="flex items-start gap-2">
                  <span className="text-lg shrink-0">🛡️</span>
                  <div>
                    <p className="text-xs font-bold text-amber-800 dark:text-amber-200 mb-1">
                      系统提示：已触发体验熔断保护
                    </p>
                    <p className="text-xs text-amber-700 dark:text-amber-300 leading-relaxed">
                      当前简历与目标 JD 存在明显的技术栈脱节，系统已尽力优化表达，但核心硬实力差距较大，建议针对性提升相关技术、多积累项目经验后再尝试对齐。
                    </p>
                  </div>
                </div>
              </div>
            )}
          </div>
        )}

        {/* ── v4.6 诊断报告：仅初筛阶段渲染，紧贴雷达下方 ── */}
        {state.diagnosis && !state.optimizedRadar && (
          <DiagnosisBox diagnosis={state.diagnosis} totalScore={radar?.total_score ?? 0} />
        )}

        {/* ── 流式输出中：内思锁动画 ── */}
        {isStreaming && state.phase === "resume_stream" && !state.optimizedText && (
          <div className="flex items-center gap-3 px-3 py-4 text-sm text-blue-600 dark:text-blue-400 bg-blue-50 dark:bg-blue-950/20 rounded-xl border border-blue-200 dark:border-blue-800">
            <span>🧠</span>
            <span className="font-semibold">LLM 正在深度优化简历...</span>
            <span className="flex gap-0.5">
              <span className="w-1.5 h-1.5 bg-blue-500 rounded-full animate-bounce [animation-delay:0ms]" />
              <span className="w-1.5 h-1.5 bg-blue-500 rounded-full animate-bounce [animation-delay:150ms]" />
              <span className="w-1.5 h-1.5 bg-blue-500 rounded-full animate-bounce [animation-delay:300ms]" />
            </span>
          </div>
        )}

        {/* ── 流式 Markdown 实时输出区 ── */}
        {state.optimizedText && (
          <div className="rounded-xl border border-zinc-200 dark:border-zinc-800 p-4">
            <h3 className="text-xs font-bold text-zinc-600 dark:text-zinc-400 mb-3">
              {isStreaming ? "⏳ 实时流式输出中..." : "✅ 优化后简历"}
            </h3>
            <div className="font-mono text-xs leading-relaxed text-zinc-700 dark:text-zinc-300 whitespace-pre-wrap max-h-[400px] overflow-y-auto bg-zinc-50 dark:bg-zinc-900 rounded-lg p-3 border border-zinc-200 dark:border-zinc-800">
              {state.optimizedText}
            </div>
          </div>
        )}

        {/* ── DiffView ── */}
        {diffResult.length > 0 && (
          <div className="rounded-xl border border-zinc-200 dark:border-zinc-800 overflow-hidden">
            <h3 className="px-4 py-2 text-xs font-bold text-zinc-600 dark:text-zinc-400 bg-zinc-50 dark:bg-zinc-950 border-b border-zinc-200 dark:border-zinc-800">
              行级微创手术对比
            </h3>
            <div className="max-h-[500px] overflow-y-auto font-mono text-xs leading-relaxed">
              {diffResult.map((change, i) => (
                <div
                  key={i}
                  className={`px-4 py-0.5 whitespace-pre-wrap break-words ${
                    change.added
                      ? "bg-emerald-100 dark:bg-emerald-950/40 text-emerald-900 dark:text-emerald-200"
                      : change.removed
                      ? "bg-rose-100 dark:bg-rose-950/40 text-rose-900 dark:text-rose-200"
                      : "text-zinc-600 dark:text-zinc-400"
                  }`}
                >
                  <span className="select-none mr-2">
                    {change.added ? "+" : change.removed ? "-" : " "}
                  </span>
                  {change.value}
                </div>
              ))}
            </div>
          </div>
        )}

        {/* ── 压测题 ── */}
        {state.questions.length > 0 && (
          <div className="rounded-xl border border-zinc-200 dark:border-zinc-800 p-4">
            <h3 className="text-xs font-bold text-zinc-600 dark:text-zinc-400 mb-3">
              Mock 面试压测题 ({state.questions.length} 道)
            </h3>
            <div className="space-y-3">
              {(state.questions as StressTestQuestion[]).map((q) => (
                <details
                  key={q.question_number}
                  className="group border border-zinc-200 dark:border-zinc-800 rounded-lg"
                >
                  <summary className="px-3 py-2 text-sm font-semibold cursor-pointer select-none text-zinc-700 dark:text-zinc-300 hover:bg-zinc-50 dark:hover:bg-zinc-900">
                    <span className="inline-block w-6 h-6 text-center leading-6 rounded-full bg-zinc-200 dark:bg-zinc-700 text-xs mr-2">
                      {q.question_number}
                    </span>
                    {q.question}
                  </summary>
                  <div className="px-4 py-2 border-t border-zinc-200 dark:border-zinc-800 text-xs text-zinc-600 dark:text-zinc-400 space-y-1">
                    <span className="font-semibold text-zinc-500">
                      ({q.category})
                    </span>
                    {q.expected_points.map((pt, i) => (
                      <p key={i}>· {pt}</p>
                    ))}
                  </div>
                </details>
              ))}
            </div>
          </div>
        )}

        {/* ── 毒舌批评 ── */}
        {state.monologue && (
          <div className="rounded-xl border border-amber-200 dark:border-amber-800 bg-amber-50 dark:bg-amber-950/20 p-4">
            <h3 className="text-xs font-bold text-amber-700 dark:text-amber-400 mb-2">
              毒舌批评 · 内部独白
            </h3>
            <p className="text-sm text-amber-800 dark:text-amber-300 leading-relaxed whitespace-pre-wrap">
              {state.monologue}
            </p>
          </div>
        )}

        {/* ── 完成标记 ── */}
        {isGenerated && !isStreaming && (
          <div className="text-center my-3 fade-in">
            <span className="px-4 py-1.5 text-xs font-semibold text-emerald-600 dark:text-emerald-400 bg-emerald-50 dark:bg-emerald-950/30 border border-emerald-200 dark:border-emerald-800 rounded-full shadow-sm">
              ✔ LLM 回答结束 — 您可向左侧 Agent 发送特殊修改指令
            </span>
          </div>
        )}

        {/* ── 错误 ── */}
        {state.error && (
          <div className="rounded-lg px-3 py-2 bg-red-50 dark:bg-red-950/30 border border-red-200 dark:border-red-800 text-sm text-red-700 dark:text-red-300">
            {state.error}
          </div>
        )}
      </div>

      {/* ── A4 画板 Modal ── */}
      <A4PaperPreview
        open={a4Open}
        onClose={() => setA4Open(false)}
        markdownContent={state.optimizedText}
        visualPayload={state.visualPayload}
      />
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════
// v4.6 诊断报告组件 —— 将 PreEvaluator 原始诊断原文渲染为可读报告
// ═══════════════════════════════════════════════════════════════

function DiagnosisBox({
  diagnosis,
  totalScore,
}: {
  diagnosis: DiagnosisData;
  totalScore: number;
}) {
  // 色块判定
  const severity =
    totalScore < 30 ? "critical" : totalScore < 50 ? "warning" : totalScore >= 70 ? "pass" : "neutral";

  const palette = {
    critical: {
      bg: "bg-red-50 dark:bg-red-950/20",
      border: "border-red-300 dark:border-red-800",
      badge: "bg-red-100 dark:bg-red-900/40 text-red-700 dark:text-red-300",
      badgeText: "🔴 严重差距",
      title: "text-red-800 dark:text-red-200",
    },
    warning: {
      bg: "bg-amber-50 dark:bg-amber-950/20",
      border: "border-amber-300 dark:border-amber-800",
      badge: "bg-amber-100 dark:bg-amber-900/40 text-amber-700 dark:text-amber-300",
      badgeText: "🟡 需重点提升",
      title: "text-amber-800 dark:text-amber-200",
    },
    pass: {
      bg: "bg-emerald-50 dark:bg-emerald-950/20",
      border: "border-emerald-300 dark:border-emerald-800",
      badge: "bg-emerald-100 dark:bg-emerald-900/40 text-emerald-700 dark:text-emerald-300",
      badgeText: "🟢 匹配良好",
      title: "text-emerald-800 dark:text-emerald-200",
    },
    neutral: {
      bg: "bg-blue-50 dark:bg-blue-950/20",
      border: "border-blue-300 dark:border-blue-800",
      badge: "bg-blue-100 dark:bg-blue-900/40 text-blue-700 dark:text-blue-300",
      badgeText: "🔵 存在差距",
      title: "text-blue-800 dark:text-blue-200",
    },
  }[severity];

  const hasSkillAnalysis =
    diagnosis.matched_skills.length > 0 || diagnosis.missing_skills.length > 0;
  const hasStarAnalysis =
    diagnosis.star_strengths.length > 0 || diagnosis.star_weaknesses.length > 0;

  return (
    <div className={`rounded-xl border ${palette.border} ${palette.bg} p-4 animate-in fade-in`}>
      {/* 头部：分数 + 严重等级徽章 */}
      <div className="flex items-center justify-between mb-3">
        <h3 className={`text-xs font-bold ${palette.title}`}>
          📋 初筛诊断报告
        </h3>
        <span className={`px-2.5 py-0.5 rounded-full text-[11px] font-semibold ${palette.badge}`}>
          {palette.badgeText} · {totalScore}/100
        </span>
      </div>

      {/* 核心反馈原文 */}
      {diagnosis.feedback && (
        <div className="mb-3">
          <p className="text-xs font-semibold text-zinc-600 dark:text-zinc-400 mb-1">
            💬 评估反馈
          </p>
          <div className="text-sm text-zinc-700 dark:text-zinc-300 leading-relaxed whitespace-pre-wrap">
            {diagnosis.feedback}
          </div>
        </div>
      )}

      {/* 工具覆盖层评估 */}
      {diagnosis.core_tool_overlap && (
        <div className="mb-3">
          <p className="text-xs font-semibold text-zinc-600 dark:text-zinc-400 mb-1">
            📐 层级评估
          </p>
          <p className="text-sm text-zinc-700 dark:text-zinc-300">
            {diagnosis.core_tool_overlap}
          </p>
        </div>
      )}

      {/* 技能覆盖分析：已覆盖 vs 缺失 */}
      {hasSkillAnalysis && (
        <div className="mb-3">
          <p className="text-xs font-semibold text-zinc-600 dark:text-zinc-400 mb-1.5">
            🔍 技能覆盖分析
          </p>
          {diagnosis.matched_skills.length > 0 && (
            <div className="mb-1.5">
              <span className="text-[11px] font-medium text-emerald-600 dark:text-emerald-400">
                ✅ 已覆盖
              </span>
              <div className="flex flex-wrap gap-1 mt-0.5">
                {diagnosis.matched_skills.map((s, i) => (
                  <span
                    key={i}
                    className="px-1.5 py-0.5 text-[11px] rounded-md bg-emerald-100 dark:bg-emerald-900/30 text-emerald-700 dark:text-emerald-300 border border-emerald-200 dark:border-emerald-800"
                  >
                    {s}
                  </span>
                ))}
              </div>
            </div>
          )}
          {diagnosis.missing_skills.length > 0 && (
            <div>
              <span className="text-[11px] font-medium text-red-600 dark:text-red-400">
                ⚠️ 缺失项
              </span>
              <div className="flex flex-wrap gap-1 mt-0.5">
                {diagnosis.missing_skills.map((s, i) => (
                  <span
                    key={i}
                    className="px-1.5 py-0.5 text-[11px] rounded-md bg-red-100 dark:bg-red-900/30 text-red-700 dark:text-red-300 border border-red-200 dark:border-red-800"
                  >
                    {s}
                  </span>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {/* STAR 完成度分析 */}
      {hasStarAnalysis && (
        <div className="mb-3">
          <p className="text-xs font-semibold text-zinc-600 dark:text-zinc-400 mb-1.5">
            ⭐ STAR 完成度分析
          </p>
          {diagnosis.star_strengths.length > 0 && (
            <div className="mb-1.5">
              <span className="text-[11px] font-medium text-emerald-600 dark:text-emerald-400">
                ✅ 优势
              </span>
              <ul className="mt-0.5 space-y-0.5">
                {diagnosis.star_strengths.map((s, i) => (
                  <li key={i} className="text-xs text-zinc-600 dark:text-zinc-400 flex gap-1">
                    <span className="text-emerald-500 shrink-0">•</span>
                    {s}
                  </li>
                ))}
              </ul>
            </div>
          )}
          {diagnosis.star_weaknesses.length > 0 && (
            <div>
              <span className="text-[11px] font-medium text-amber-600 dark:text-amber-400">
                ⚠️ 短板
              </span>
              <ul className="mt-0.5 space-y-0.5">
                {diagnosis.star_weaknesses.map((s, i) => (
                  <li key={i} className="text-xs text-zinc-600 dark:text-zinc-400 flex gap-1">
                    <span className="text-amber-500 shrink-0">•</span>
                    {s}
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}

      {/* 弱动词检测 */}
      {diagnosis.weak_verbs.length > 0 && (
        <div>
          <p className="text-xs font-semibold text-zinc-600 dark:text-zinc-400 mb-1">
            📝 弱动词检测
          </p>
          <div className="flex flex-wrap gap-1">
            {diagnosis.weak_verbs.map((v, i) => (
              <span
                key={i}
                className="px-1.5 py-0.5 text-[11px] rounded-md bg-rose-100 dark:bg-rose-900/30 text-rose-700 dark:text-rose-300 border border-rose-200 dark:border-rose-800 line-through"
              >
                {v}
              </span>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function ScoreBar({
  label,
  score,
  max,
  color,
}: {
  label: string;
  score: number;
  max: number;
  color: string;
}) {
  const pct = Math.min(100, Math.round((score / max) * 100));
  return (
    <div>
      <div className="flex justify-between text-xs text-zinc-500 mb-1">
        <span>{label}</span>
        <span>
          {score}/{max}
        </span>
      </div>
      <div className="w-full h-2 bg-zinc-200 dark:bg-zinc-800 rounded-full overflow-hidden">
        <div
          className={`h-full ${color} rounded-full transition-all duration-700 ease-out`}
          style={{ width: `${pct}%` }}
        />
      </div>
    </div>
  );
}
