/**
 * AI-Resume-Evolver v4.1 主页面 —— 双模并网入口 + 双轴解耦拓扑
 *
 * 顶层 appMode 状态机斩断 Pipeline / Agent 两种模式：
 *   - "pipeline" → 1:3 黄金看板 + 阶段式条件渲染左轴
 *     · 生成前：左轴 PipelineInput（简历 + JD 多模态输入）
 *     · 生成后：左轴 AgentConsole（受控模式，微创精修对话）
 *     · 右轴：PipelinePanel（全量输出看板，纯 props 驱动）
 *   - "agent"    → AgentLayout（useAgentStream 提升 + 双轴同步消费）
 */

"use client";

import { useState, useCallback, useEffect } from "react";
import AgentConsole from "@/components/AgentConsole";
import PipelinePanel from "@/components/PipelinePanel";
import PipelineInput from "@/components/PipelineInput";
import AgentLayout from "@/components/AgentLayout";
import LoginPage from "@/components/LoginPage";
import ModeSwitchGuard from "@/components/ModeSwitchGuard";
import { useAuth } from "@/contexts/AuthContext";
import { useAgentSession, useAgentSessionDispatch, useGlobalAbortController } from "@/contexts/AgentSessionContext";
import { usePipelineStream } from "@/hooks/usePipelineStream";
import { useAgentStream } from "@/hooks/useAgentStream";

type AppMode = "pipeline" | "agent";

export default function Home() {
  const { user, token, isLoading: authLoading, logout } = useAuth();
  const [appMode, setAppMode] = useState<AppMode>("pipeline");
  const [pendingMode, setPendingMode] = useState<AppMode | null>(null);

  // ── 全局 Agent 会话状态（模式切换防呆栅栏依赖）──
  const { isThinking: globalThinking, isStreaming: globalStreaming } = useAgentSession();
  const agentDispatch = useAgentSessionDispatch();
  const { abort: globalAbort } = useGlobalAbortController();

  // ── Pipeline 模式 AgentConsole 消息过滤时间戳 ──
  // 切换到 Pipeline 模式 / 新建优化时更新，只显示该时间点之后的消息
  const [pipelineChatSince, setPipelineChatSince] = useState<number>(Date.now());

  // ── Pipeline 模式顶层状态：双 Hook 并网 ──
  const {
    state: pipelineState,
    isStreaming: pipelineStreaming,
    isGenerated,
    startPipeline,
  } = usePipelineStream();

  const {
    nodeLogs: agentLogs,
    isStreaming: agentStreaming,
    isThinking: agentThinking,
    error: agentError,
    startStream: agentStartStream,
    abort: agentAbort,
  } = useAgentStream();

  const [originalResume, setOriginalResume] = useState("");
  const [forceInputMode, setForceInputMode] = useState(false);

  // ── v7.3 Pipeline 完成时将优化后简历注入 Agent 上下文，供后续交互/纯 Agent 模式使用 ──
  useEffect(() => {
    if (isGenerated && pipelineState.optimizedText) {
      agentDispatch({ type: "SET_RESUME_TEXT", payload: pipelineState.optimizedText });
    }
  }, [isGenerated, pipelineState.optimizedText, agentDispatch]);

  // ── 模式切换防呆栅栏 ──
  const handleModeSwitch = useCallback((target: AppMode) => {
    if (target === appMode) return;
    if (globalThinking || globalStreaming) {
      setPendingMode(target);
    } else {
      // 从 Agent 跳回 Pipeline 时，重置消息过滤时间戳，确保聊天框干净
      if (appMode === "agent" && target === "pipeline") {
        setPipelineChatSince(Date.now());
      }
      // 从 Pipeline 跳回 Agent 时，清空 Agent 会话避免聊天记录泄漏
      if (appMode === "pipeline" && target === "agent") {
        agentDispatch({ type: "RESET_SESSION" });
      }
      setAppMode(target);
    }
  }, [appMode, globalThinking, globalStreaming, agentDispatch]);

  const handleConfirmSwitch = useCallback(() => {
    globalAbort(); // 前端拉闸 → 后端 CancelledError → checkpoint 回滚
    // 从 Agent 跳回 Pipeline 时，重置消息过滤时间戳
    if (appMode === "agent" && pendingMode === "pipeline") {
      setPipelineChatSince(Date.now());
    }
    // 从 Pipeline 强制跳 Agent 时，清空 Agent 会话避免聊天记录泄漏
    if (appMode === "pipeline" && pendingMode === "agent") {
      agentDispatch({ type: "RESET_SESSION" });
    }
    setAppMode(pendingMode!);
    setPendingMode(null);
  }, [globalAbort, pendingMode, appMode, agentDispatch]);

  const handleCancelSwitch = useCallback(() => {
    setPendingMode(null);
  }, []);

  // 左轴条件：生成完成 + 未强制回退输入模式 → 显示 Agent 精修对话
  const showAgentChat = isGenerated && !forceInputMode;

  // Pipeline 输入提交 → 点火流水线
  const handlePipelineSubmit = useCallback(
    (resume: string, jd: string) => {
      setOriginalResume(resume);
      setForceInputMode(false);
      setPipelineChatSince(Date.now());  // 新优化 → 聊天框重置
      startPipeline(resume, jd);
    },
    [startPipeline]
  );

  // 从 Agent 对话模式切回输入模式（新建优化）
  const handleNewOptimize = useCallback(() => {
    setForceInputMode(true);
    setPipelineChatSince(Date.now());  // 新优化 → 聊天框重置
  }, []);

  // ── 认证加载态 ──
  if (authLoading) {
    return (
      <div className="flex h-screen w-screen items-center justify-center bg-zinc-950">
        <div className="text-sm text-zinc-400 animate-pulse">加载中...</div>
      </div>
    );
  }

  // ── 未认证：显示全屏登录门面 ──
  if (!user) return <LoginPage />;

  return (
    <div className="flex flex-col h-screen w-screen overflow-hidden bg-zinc-100 dark:bg-zinc-950">
      {/* ── 双模并网入口：Splash 卡片选择器 ── */}
      <div className="flex-shrink-0 bg-white dark:bg-black border-b-2 border-zinc-200 dark:border-zinc-800">
        <div className="max-w-2xl mx-auto px-6 py-4">
          <div className="flex items-center justify-between mb-4">
            <div className="text-center flex-1">
              <h1 className="text-base font-bold text-zinc-800 dark:text-zinc-100">
                AI-Resume-Evolver 5.2
              </h1>
              <p className="text-xs text-zinc-500 mt-0.5">
                选择工作模式，智能简历优化引擎全力驱动
              </p>
            </div>
            {user && (
              <button
                onClick={logout}
                className="shrink-0 px-3 py-1.5 text-[11px] font-medium rounded-lg border border-zinc-300 dark:border-zinc-700 text-zinc-500 hover:text-zinc-300 hover:border-zinc-500 transition-colors"
              >
                {user.username} · 登出
              </button>
            )}
          </div>

          <div className="grid grid-cols-2 gap-3">
            <button
              onClick={() => handleModeSwitch("pipeline")}
              className={`group relative flex flex-col items-center justify-center p-4 rounded-2xl border-2 transition-all duration-200 ${
                appMode === "pipeline"
                  ? "border-blue-500 bg-blue-50 dark:bg-blue-950/30 shadow-lg shadow-blue-500/20"
                  : "border-zinc-200 dark:border-zinc-700 bg-white dark:bg-zinc-900 hover:border-blue-300 dark:hover:border-blue-700"
              }`}
            >
              <span className="text-2xl mb-1.5">⚡</span>
              <span
                className={`text-sm font-bold ${
                  appMode === "pipeline"
                    ? "text-blue-700 dark:text-blue-300"
                    : "text-zinc-700 dark:text-zinc-300"
                }`}
              >
                一键流水线优化
              </span>
              <span className="text-[11px] text-zinc-400 dark:text-zinc-500 mt-0.5 text-center leading-tight">
                粘贴简历 + JD → 全链路 Agent 自动精修
              </span>
              {appMode === "pipeline" && (
                <span className="absolute top-2 right-2 w-2.5 h-2.5 bg-blue-500 rounded-full animate-pulse" />
              )}
            </button>

            <button
              onClick={() => handleModeSwitch("agent")}
              className={`group relative flex flex-col items-center justify-center p-4 rounded-2xl border-2 transition-all duration-200 ${
                appMode === "agent"
                  ? "border-purple-500 bg-purple-50 dark:bg-purple-950/30 shadow-lg shadow-purple-500/20"
                  : "border-zinc-200 dark:border-zinc-700 bg-white dark:bg-zinc-900 hover:border-purple-300 dark:hover:border-purple-700"
              }`}
            >
              <span className="text-2xl mb-1.5">🧠</span>
              <span
                className={`text-sm font-bold ${
                  appMode === "agent"
                    ? "text-purple-700 dark:text-purple-300"
                    : "text-zinc-700 dark:text-zinc-300"
                }`}
              >
                纯 Agent 智脑交互
              </span>
              <span className="text-[11px] text-zinc-400 dark:text-zinc-500 mt-0.5 text-center leading-tight">
                自由对话 · 微创手术刀 · 联网情报检索
              </span>
              {appMode === "agent" && (
                <span className="absolute top-2 right-2 w-2.5 h-2.5 bg-purple-500 rounded-full animate-pulse" />
              )}
            </button>
          </div>

          <div className="mt-3 flex items-center justify-center gap-2">
            <span
              className={`inline-flex items-center gap-1 px-3 py-1 rounded-full text-[11px] font-semibold ${
                appMode === "pipeline"
                  ? "bg-blue-100 text-blue-700 dark:bg-blue-900/40 dark:text-blue-300"
                  : "bg-purple-100 text-purple-700 dark:bg-purple-900/40 dark:text-purple-300"
              }`}
            >
              <span className="w-1.5 h-1.5 rounded-full bg-current animate-pulse" />
              {appMode === "pipeline" ? "一键流水线模式已激活" : "Agent 智脑模式已激活"}
            </span>
          </div>
        </div>
      </div>

      {/* ── 内容区 ── */}
      <div className="flex-1 overflow-hidden">
        {appMode === "pipeline" ? (
          /* ── Pipeline 模式：1:3 黄金看板 + 阶段式条件左轴 ── */
          <div className="flex h-full w-full">
            {/* 左轴 1/4：条件渲染 */}
            <div className="w-1/4 min-w-[340px] h-full">
              {showAgentChat ? (
                /* 生成完成后 → Agent 微创精修对话 */
                <div className="flex flex-col h-full">
                  <AgentConsole
                    nodeLogs={agentLogs.filter(log => log.timestamp >= pipelineChatSince)}
                    isStreaming={agentStreaming}
                    isThinking={agentThinking}
                    error={agentError}
                    onSubmit={agentStartStream}
                    onAbort={agentAbort}
                    subtitle="✨ 基础简历已生成！已为您开启 Agent 特殊修改模式"
                  />
                  {/* 新建优化按钮 */}
                  <div className="flex-shrink-0 px-3 py-2 border-t border-zinc-200 dark:border-zinc-800 bg-white dark:bg-black">
                    <button
                      onClick={handleNewOptimize}
                      className="w-full py-2 text-xs font-semibold rounded-lg border border-zinc-300 dark:border-zinc-700 text-zinc-600 dark:text-zinc-400 hover:bg-zinc-50 dark:hover:bg-zinc-900 transition-colors"
                    >
                      🔄 新建优化
                    </button>
                  </div>
                </div>
              ) : (
                /* 生成前 → 多模态输入 */
                <PipelineInput
                  onSubmit={handlePipelineSubmit}
                  isStreaming={pipelineStreaming}
                />
              )}
            </div>

            {/* 右轴 3/4：全量输出看板（纯 props 驱动） */}
            <div className="w-3/4 h-full">
              <PipelinePanel
                state={pipelineState}
                isStreaming={pipelineStreaming}
                originalResume={originalResume}
                isGenerated={isGenerated}
              />
            </div>
          </div>
        ) : (
          /* Agent 模式：AgentLayout 内部提升 useAgentStream，双轴同步消费 */
          <AgentLayout />
        )}
      </div>

      {/* ── 模式切换防呆确认弹窗 ── */}
      <ModeSwitchGuard
        open={pendingMode !== null}
        targetMode={pendingMode ?? "pipeline"}
        onConfirm={handleConfirmSwitch}
        onCancel={handleCancelSwitch}
      />
    </div>
  );
}
