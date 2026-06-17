"use client";

/**
 * LoginOverlay — v5.2 极简登录遮罩层
 *
 * 未认证时覆盖全屏，登录成功后自动消失。
 * 风格对齐 AI-Resume-Evolver 暗黑专业调性。
 */

import { useState, type FormEvent } from "react";
import { useAuth } from "@/contexts/AuthContext";

export function LoginOverlay() {
  const { login, isLoading, error } = useAuth();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [localError, setLocalError] = useState<string | null>(null);

  const displayError = localError ?? error;

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setLocalError(null);

    if (!username.trim() || !password.trim()) {
      setLocalError("请输入用户名和密码");
      return;
    }

    try {
      await login(username.trim(), password);
    } catch {
      // 错误已在 AuthContext 中设置
      setLocalError(error ?? "登录失败，请重试");
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm">
      <div className="w-full max-w-sm rounded-2xl border border-zinc-800 bg-zinc-950 p-8 shadow-2xl">
        {/* 头部 */}
        <div className="mb-8 text-center">
          <h1 className="text-xl font-bold tracking-tight text-zinc-100">
            AI-Resume-Evolver
          </h1>
          <p className="mt-1 text-sm text-zinc-500">v5.2 · 身份验证</p>
        </div>

        {/* 表单 */}
        <form onSubmit={handleSubmit} className="space-y-5">
          <div>
            <label className="mb-1.5 block text-xs font-medium text-zinc-400">
              用户名
            </label>
            <input
              type="text"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              placeholder="admin"
              autoComplete="username"
              className="w-full rounded-lg border border-zinc-800 bg-zinc-900 px-3.5 py-2.5
                         text-sm text-zinc-100 placeholder-zinc-600
                         outline-none transition-colors focus:border-zinc-600 focus:ring-1 focus:ring-zinc-600"
            />
          </div>

          <div>
            <label className="mb-1.5 block text-xs font-medium text-zinc-400">
              密码
            </label>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="Enter your password"
              autoComplete="current-password"
              className="w-full rounded-lg border border-zinc-800 bg-zinc-900 px-3.5 py-2.5
                         text-sm text-zinc-100 placeholder-zinc-600
                         outline-none transition-colors focus:border-zinc-600 focus:ring-1 focus:ring-zinc-600"
            />
          </div>

          {/* 错误提示 */}
          {displayError && (
            <div className="rounded-lg border border-red-900/50 bg-red-950/30 px-3 py-2 text-xs text-red-400">
              {displayError}
            </div>
          )}

          <button
            type="submit"
            disabled={isLoading}
            className="w-full rounded-lg bg-zinc-100 py-2.5 text-sm font-semibold text-zinc-900
                       transition-all hover:bg-zinc-200 active:scale-[0.98]
                       disabled:cursor-not-allowed disabled:opacity-50"
          >
            {isLoading ? "验证中..." : "登 录"}
          </button>
        </form>

      </div>
    </div>
  );
}
