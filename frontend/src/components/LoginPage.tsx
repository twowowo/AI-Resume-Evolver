"use client";

import { useState, useEffect, useCallback, type FormEvent } from "react";
import { useAuth } from "@/contexts/AuthContext";

// ═══════════════════════════════════════════════════════════════
// LangGraph 状态机 Pipeline 节点定义
// ═══════════════════════════════════════════════════════════════
const PIPELINE_NODES = [
  { id: "01", name: "Parser", label: "简历解析", desc: "多模态文档结构提取与标准化" },
  { id: "02", name: "Retriever", label: "RAG检索增强", desc: "ChromaDB + BM25 混合召回" },
  { id: "03", name: "Editor", label: "深度重写匹配", desc: "STAR 方法论 + JD 语义对齐" },
  { id: "04", name: "Evaluator", label: "自审反思闭环", desc: "多 Agent 评审团量化打分" },
  { id: "05", name: "Polisher", label: "靶向精修", desc: "外科手术式反馈精准修复" },
  { id: "06", name: "Export", label: "导出交付", desc: "DOCX / PDF / A4 纸渲染" },
] as const;

const TICKER_ITEMS = [
  "周同学通过深度 RAG 拓扑优化成功斩获中厂 Java 后端 Offer",
  "LangGraph 状态机持续学习用户文档特征，匹配精度提升 37%",
  "系统完成 v5.2 版本迭代，JWT 鉴权体系全面升级",
  "ChromaDB 混合检索召回率达 92.4%，金牌案例精准命中",
  "多 Agent 评审团机制上线，简历质量评估标准差降至 0.3",
];

// ═══════════════════════════════════════════════════════════════
// 内联 SVG 图标
// ═══════════════════════════════════════════════════════════════
function UserIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.5} className="w-5 h-5">
      <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2" />
      <circle cx="12" cy="7" r="4" />
    </svg>
  );
}

function LockIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.5} className="w-5 h-5">
      <rect x="3" y="11" width="18" height="11" rx="2" />
      <path d="M7 11V7a5 5 0 0 1 10 0v4" />
    </svg>
  );
}

function EyeIcon({ visible }: { visible: boolean }) {
  return visible ? (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.5} className="w-4 h-4">
      <path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94" />
      <path d="M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19" />
      <line x1="1" y1="1" x2="23" y2="23" />
    </svg>
  ) : (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.5} className="w-4 h-4">
      <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z" />
      <circle cx="12" cy="12" r="3" />
    </svg>
  );
}

function Spinner() {
  return (
    <svg viewBox="0 0 24 24" fill="none" className="w-5 h-5 animate-spin">
      <circle cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="3" opacity="0.25" />
      <path
        d="M12 2a10 10 0 0 1 10 10"
        stroke="currentColor"
        strokeWidth="3"
        strokeLinecap="round"
      />
    </svg>
  );
}

function ChevronRight() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} className="w-4 h-4">
      <polyline points="9,18 15,12 9,6" />
    </svg>
  );
}

// ═══════════════════════════════════════════════════════════════
// LoginPage — 全屏双栏登录门面
// ═══════════════════════════════════════════════════════════════
export default function LoginPage() {
  const { login, isLoading, error } = useAuth();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [activeNodeIdx, setActiveNodeIdx] = useState(0);
  const [localError, setLocalError] = useState<string | null>(null);

  const displayError = localError ?? error;

  // 节点轮播：模拟 LangGraph 状态机流转
  useEffect(() => {
    const timer = setInterval(() => {
      setActiveNodeIdx((prev) => (prev + 1) % PIPELINE_NODES.length);
    }, 2800);
    return () => clearInterval(timer);
  }, []);

  const handleSubmit = useCallback(
    async (e: FormEvent) => {
      e.preventDefault();
      setLocalError(null);

      if (!username.trim() || !password.trim()) {
        setLocalError("请输入用户名和密码");
        return;
      }

      try {
        await login(username.trim(), password);
      } catch {
        setLocalError(error ?? "登录失败，请检查凭据或后端服务");
      }
    },
    [username, password, login, error],
  );

  return (
    <div className="login-page-root fixed inset-0 z-50 flex">
      {/* ═══════════════════════════════════════════════════
          左栏 — 极客深色科技展示墙 (40%)
          ═══════════════════════════════════════════════════ */}
      <aside className="login-left relative hidden w-2/5 flex-col overflow-hidden bg-slate-950 lg:flex">
        {/* 科幻网格背景 */}
        <div className="login-grid pointer-events-none absolute inset-0 opacity-30" />

        {/* 顶部扫描线 */}
        <div className="login-scanline pointer-events-none absolute left-0 right-0 h-px bg-gradient-to-r from-transparent via-cyan-400/40 to-transparent" />

        {/* 头部 Logo */}
        <div className="relative z-10 flex items-center gap-4 px-10 pt-12">
          {/* 六边形 Logo */}
          <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-lg border border-slate-700 bg-slate-900 shadow-lg shadow-cyan-500/10">
            <span className="text-xl font-bold tracking-tighter text-cyan-400">AI</span>
          </div>
          <div>
            <h1 className="text-lg font-bold tracking-wide text-slate-100">
              AI-Resume-Evolver
            </h1>
            <p className="text-xs text-slate-500">
              LangGraph 状态机 · RAG 增强 · 全栈简历进化引擎
            </p>
          </div>
        </div>

        {/* 中部：LangGraph Pipeline 拓扑可视化 */}
        <div className="relative z-10 mt-12 flex flex-1 flex-col justify-center px-10">
          <p className="mb-6 text-[10px] font-semibold uppercase tracking-[0.2em] text-slate-600">
            LangGraph 核心状态机拓扑
          </p>

          <div className="pipeline-track relative flex flex-col gap-0">
            {PIPELINE_NODES.map((node, idx) => {
              const isActive = idx === activeNodeIdx;
              const isPast = idx < activeNodeIdx || (activeNodeIdx === 0 && idx === PIPELINE_NODES.length - 1 && idx !== 0);

              return (
                <div key={node.id} className="pipeline-node-group relative">
                  {/* 连接线 */}
                  {idx < PIPELINE_NODES.length - 1 && (
                    <div className="pipeline-connector absolute left-[23px] top-[48px] w-px bg-slate-800">
                      <div
                        className={`pipeline-flow h-full w-full ${
                          isActive || isPast ? "pipeline-flow-active" : ""
                        }`}
                      />
                    </div>
                  )}

                  {/* 节点卡片 */}
                  <div
                    className={`pipeline-node relative flex items-center gap-4 rounded-xl border px-4 py-3 transition-all duration-700 ${
                      isActive
                        ? "border-cyan-500/40 bg-cyan-950/20 shadow-lg shadow-cyan-500/10 node-active"
                        : isPast
                          ? "border-slate-800 bg-slate-900/50"
                          : "border-slate-800/50 bg-slate-900/30"
                    }`}
                    style={{ animationDelay: `${idx * 80}ms` }}
                  >
                    {/* 序号标记 */}
                    <span
                      className={`flex h-7 w-7 shrink-0 items-center justify-center rounded-md text-[10px] font-bold transition-all duration-700 ${
                        isActive
                          ? "bg-cyan-500 text-slate-950 node-pulse"
                          : isPast
                            ? "bg-slate-700 text-slate-300"
                            : "bg-slate-800 text-slate-500"
                      }`}
                    >
                      {node.id}
                    </span>

                    {/* 信息区 */}
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-2">
                        <span
                          className={`text-sm font-semibold transition-colors duration-700 ${
                            isActive
                              ? "text-cyan-300"
                              : isPast
                                ? "text-slate-300"
                                : "text-slate-500"
                          }`}
                        >
                          {node.name}
                        </span>
                        {isActive && (
                          <span className="inline-flex h-1.5 w-1.5 rounded-full bg-cyan-400 animate-ping" />
                        )}
                      </div>
                      <p
                        className={`mt-0.5 text-xs transition-colors duration-700 ${
                          isActive ? "text-cyan-400/70" : "text-slate-600"
                        }`}
                      >
                        {node.label}
                      </p>
                    </div>

                    {/* 状态标签 */}
                    <span
                      className={`shrink-0 rounded-full px-2 py-0.5 text-[9px] font-medium transition-all duration-700 ${
                        isActive
                          ? "bg-cyan-500/20 text-cyan-400 border border-cyan-500/30"
                          : isPast
                            ? "bg-emerald-500/10 text-emerald-500/70 border border-emerald-500/20"
                            : "bg-slate-800 text-slate-600 border border-slate-700/50"
                      }`}
                    >
                      {isActive ? "PROCESSING" : isPast ? "COMPLETE" : "IDLE"}
                    </span>
                  </div>
                </div>
              );
            })}
          </div>
        </div>

        {/* 底部：滚动进化战报 Ticker */}
        <div className="relative z-10 border-t border-slate-800 bg-slate-900/50 py-3">
          <div className="ticker-wrap overflow-hidden">
            <div className="ticker-track flex w-max gap-12">
              {[...TICKER_ITEMS, ...TICKER_ITEMS].map((msg, i) => (
                <span
                  key={i}
                  className="flex shrink-0 items-center gap-2 text-[11px] text-slate-500"
                >
                  <span className="inline-block h-1 w-1 rounded-full bg-cyan-500/70" />
                  {msg}
                </span>
              ))}
            </div>
          </div>
        </div>
      </aside>

      {/* ═══════════════════════════════════════════════════
          右栏 — 纯净明亮登录表单 (60%)
          ═══════════════════════════════════════════════════ */}
      <main className="login-right flex w-full flex-col items-center justify-center bg-white lg:w-3/5">
        <div className="w-full max-w-[400px] px-8">
          {/* 欢迎文案 */}
          <div className="mb-10">
            <h2 className="text-2xl font-bold tracking-tight text-slate-900">
              欢迎回来
            </h2>
            <p className="mt-2 text-sm leading-relaxed text-slate-500">
              请使用您的凭据验证身份，进入{" "}
              <span className="font-semibold text-slate-700">AI-Resume-Evolver</span>{" "}
              全栈简历进化引擎
            </p>
          </div>

          {/* 登录表单卡片 */}
          <form onSubmit={handleSubmit} className="space-y-5">
            {/* 用户名 */}
            <div className="space-y-1.5">
              <label className="text-xs font-semibold tracking-wide text-slate-500 uppercase">
                用户名
              </label>
              <div className="input-wrapper group relative">
                <span className="absolute left-3.5 top-1/2 -translate-y-1/2 text-slate-400 transition-colors duration-200 group-focus-within:text-slate-700">
                  <UserIcon />
                </span>
                <input
                  type="text"
                  value={username}
                  onChange={(e) => setUsername(e.target.value)}
                  placeholder="输入您的用户名"
                  autoComplete="username"
                  autoFocus
                  className="w-full rounded-xl border border-slate-200 bg-slate-50 py-3 pl-11 pr-4 text-sm text-slate-800 placeholder-slate-400 outline-none transition-all duration-200 hover:border-slate-300 focus:border-slate-400 focus:bg-white focus:ring-4 focus:ring-slate-400/10"
                />
              </div>
            </div>

            {/* 密码 */}
            <div className="space-y-1.5">
              <label className="text-xs font-semibold tracking-wide text-slate-500 uppercase">
                密码
              </label>
              <div className="input-wrapper group relative">
                <span className="absolute left-3.5 top-1/2 -translate-y-1/2 text-slate-400 transition-colors duration-200 group-focus-within:text-slate-700">
                  <LockIcon />
                </span>
                <input
                  type={showPassword ? "text" : "password"}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="输入您的密码"
                  autoComplete="current-password"
                  className="w-full rounded-xl border border-slate-200 bg-slate-50 py-3 pl-11 pr-12 text-sm text-slate-800 placeholder-slate-400 outline-none transition-all duration-200 hover:border-slate-300 focus:border-slate-400 focus:bg-white focus:ring-4 focus:ring-slate-400/10"
                />
                <button
                  type="button"
                  onClick={() => setShowPassword((v) => !v)}
                  className="absolute right-3.5 top-1/2 -translate-y-1/2 text-slate-400 transition-colors hover:text-slate-600"
                  tabIndex={-1}
                >
                  <EyeIcon visible={showPassword} />
                </button>
              </div>
            </div>

            {/* 错误提示 */}
            {displayError && (
              <div
                className="flex items-center gap-2 rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-xs text-red-600 animate-in"
                role="alert"
              >
                <svg viewBox="0 0 24 24" fill="currentColor" className="h-4 w-4 shrink-0 text-red-400">
                  <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm1 15h-2v-2h2v2zm0-4h-2V7h2v6z" />
                </svg>
                <span>{displayError}</span>
              </div>
            )}

            {/* 登录按钮 */}
            <button
              type="submit"
              disabled={isLoading}
              className="w-full flex items-center justify-center gap-2 rounded-xl bg-slate-900 py-3 text-sm font-semibold text-white shadow-lg shadow-slate-900/10 transition-all duration-200 hover:bg-slate-800 hover:shadow-xl hover:shadow-slate-900/15 active:scale-[0.98] disabled:cursor-not-allowed disabled:opacity-60 disabled:active:scale-100"
            >
              {isLoading ? (
                <>
                  <Spinner />
                  <span>验证中...</span>
                </>
              ) : (
                <>
                  <span>验证身份并进入系统</span>
                  <ChevronRight />
                </>
              )}
            </button>
          </form>

          {/* 底部信息 */}
          <div className="mt-8 flex items-center justify-between">
            <p className="text-[11px] text-slate-400">
              v5.2 · LangGraph Agent Pipeline
            </p>
            <p className="text-[11px] text-slate-400">
              首次使用？请联系系统管理员获取凭据
            </p>
          </div>
        </div>
      </main>

      {/* ═══════════════════════════════════════════════════
          动画与特效 CSS
          ═══════════════════════════════════════════════════ */}
      <style jsx>{`
        /* ── 左栏网格背景 ── */
        .login-grid {
          background-image:
            linear-gradient(rgba(255,255,255,0.025) 1px, transparent 1px),
            linear-gradient(90deg, rgba(255,255,255,0.025) 1px, transparent 1px);
          background-size: 48px 48px;
          animation: grid-drift 20s linear infinite;
        }

        @keyframes grid-drift {
          0% { background-position: 0 0, 0 0; }
          100% { background-position: 0 48px, 48px 0; }
        }

        /* ── 扫描线 ── */
        .login-scanline {
          top: 40%;
          animation: scanline-sweep 6s ease-in-out infinite;
        }

        @keyframes scanline-sweep {
          0%, 100% { top: 10%; opacity: 0; }
          25% { opacity: 1; }
          50% { top: 85%; opacity: 0.6; }
          75% { opacity: 0; }
        }

        /* ── Pipeline 连接线 ── */
        .pipeline-connector {
          height: 24px;
        }

        .pipeline-flow {
          background: transparent;
          transition: background 0.7s ease;
        }

        .pipeline-flow-active {
          background: linear-gradient(
            to bottom,
            transparent 0%,
            rgba(6, 182, 212, 0.6) 50%,
            transparent 100%
          );
          background-size: 1px 12px;
          animation: flow-pulse 1.5s ease-in-out infinite;
        }

        @keyframes flow-pulse {
          0%, 100% { opacity: 0.3; }
          50% { opacity: 1; }
        }

        /* ── 节点入场动画 ── */
        .pipeline-node {
          animation: node-enter 0.6s ease-out both;
        }

        @keyframes node-enter {
          from {
            opacity: 0;
            transform: translateY(12px);
          }
          to {
            opacity: 1;
            transform: translateY(0);
          }
        }

        /* ── 活动节点脉冲 ── */
        .node-active {
          animation: node-glow 2.8s ease-in-out infinite;
        }

        @keyframes node-glow {
          0%, 100% {
            box-shadow: 0 0 8px rgba(6, 182, 212, 0.15);
          }
          50% {
            box-shadow: 0 0 24px rgba(6, 182, 212, 0.35), 0 0 48px rgba(6, 182, 212, 0.1);
          }
        }

        .node-pulse {
          animation: number-pulse 2.8s ease-in-out infinite;
        }

        @keyframes number-pulse {
          0%, 100% {
            box-shadow: 0 0 4px rgba(6, 182, 212, 0.3);
          }
          50% {
            box-shadow: 0 0 16px rgba(6, 182, 212, 0.6);
          }
        }

        /* ── 战报 Ticker ── */
        .ticker-wrap {
          mask-image: linear-gradient(
            to right,
            transparent 0%,
            black 8%,
            black 92%,
            transparent 100%
          );
        }

        .ticker-track {
          animation: ticker-scroll 35s linear infinite;
        }

        @keyframes ticker-scroll {
          0% { transform: translateX(0); }
          100% { transform: translateX(-50%); }
        }

        /* ── 右栏入场 ── */
        .login-right {
          animation: right-fade-in 0.8s ease-out both;
        }

        @keyframes right-fade-in {
          from {
            opacity: 0;
          }
          to {
            opacity: 1;
          }
        }

        /* ── 错误提示入场 ── */
        .animate-in {
          animation: error-enter 0.3s ease-out both;
        }

        @keyframes error-enter {
          from {
            opacity: 0;
            transform: translateY(-4px);
          }
          to {
            opacity: 1;
            transform: translateY(0);
          }
        }
      `}</style>
    </div>
  );
}
