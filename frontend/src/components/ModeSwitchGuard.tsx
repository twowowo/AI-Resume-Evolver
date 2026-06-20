/**
 * ModeSwitchGuard — 模式切换防呆确认弹窗
 *
 * 当 Agent 处于 isThinking / isStreaming 状态时，拦截用户切换模式操作，
 * 弹出警告确认窗，确认后执行熔断 + 状态回退 + 切换。
 */
"use client";

interface ModeSwitchGuardProps {
  open: boolean;
  targetMode: "pipeline" | "agent";
  onConfirm: () => void;
  onCancel: () => void;
}

const MODE_LABELS: Record<string, string> = {
  pipeline: "一键流水线优化",
  agent: "纯 Agent 智脑交互",
};

export default function ModeSwitchGuard({
  open,
  targetMode,
  onConfirm,
  onCancel,
}: ModeSwitchGuardProps) {
  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      {/* 遮罩 */}
      <div
        className="absolute inset-0 bg-black/60 backdrop-blur-sm"
        onClick={onCancel}
      />

      {/* 弹窗卡片 */}
      <div className="relative w-full max-w-md mx-4 bg-zinc-900 border border-red-500/30 rounded-2xl shadow-2xl shadow-red-500/10 p-6 animate-in fade-in zoom-in-95 duration-200">
        {/* 图标 */}
        <div className="flex items-center gap-3 mb-4">
          <div className="flex-shrink-0 w-10 h-10 rounded-full bg-red-500/10 border border-red-500/30 flex items-center justify-center">
            <svg
              className="w-5 h-5 text-red-400"
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
              strokeWidth={2}
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                d="M12 9v3.75m-9.303 3.376c-.866 1.5.217 3.374 1.948 3.374h14.71c1.73 0 2.813-1.874 1.948-3.374L13.949 3.378c-.866-1.5-3.032-1.5-3.898 0L2.697 16.126zM12 15.75h.007v.008H12v-.008z"
              />
            </svg>
          </div>
          <h2 className="text-lg font-bold text-zinc-100">Agent 正在深度推演中</h2>
        </div>

        <p className="text-sm text-zinc-400 leading-relaxed mb-2">
          切换至 <span className="text-purple-400 font-semibold">{MODE_LABELS[targetMode] || targetMode}</span> 模式将：
        </p>

        <ul className="text-sm text-zinc-500 space-y-1.5 mb-5 pl-1">
          <li className="flex items-start gap-2">
            <span className="text-red-400 mt-0.5">•</span>
            <span>强行中止当前 Agent 的所有运行中任务</span>
          </li>
          <li className="flex items-start gap-2">
            <span className="text-red-400 mt-0.5">•</span>
            <span>回退本轮对话数据到最近一次安全快照</span>
          </li>
          <li className="flex items-start gap-2">
            <span className="text-red-400 mt-0.5">•</span>
            <span>释放该会话的后端分布式状态锁</span>
          </li>
        </ul>

        <p className="text-sm font-semibold text-red-300 mb-6">
          ⚠️ 是否确认执行强制熔断并切换模式？
        </p>

        {/* 按钮组 */}
        <div className="flex gap-3">
          <button
            onClick={onCancel}
            className="flex-1 py-2.5 px-4 text-sm font-semibold rounded-xl border border-zinc-700 text-zinc-300 hover:bg-zinc-800 hover:border-zinc-600 transition-colors"
          >
            取消，留在当前模式
          </button>
          <button
            onClick={onConfirm}
            className="flex-1 py-2.5 px-4 text-sm font-bold rounded-xl bg-red-600 text-white hover:bg-red-500 active:scale-[0.98] transition-all"
          >
            确认熔断并切换
          </button>
        </div>
      </div>
    </div>
  );
}
