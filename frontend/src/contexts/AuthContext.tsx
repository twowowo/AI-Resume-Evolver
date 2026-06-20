"use client";

/**
 * AuthContext — v5.2 JWT 认证全局状态管理
 *
 * 职责:
 *   1. 管理 user / token 状态
 *   2. 登录时调用 POST /api/v1/auth/login
 *   3. 登出时清除 localStorage 中的 token
 *   4. 应用启动时自动恢复已保存的 token
 */

import React, {
  createContext,
  useContext,
  useState,
  useEffect,
  useCallback,
  type ReactNode,
} from "react";

interface UserInfo {
  id: number;
  username: string;
}

interface AuthState {
  user: UserInfo | null;
  token: string | null;
  isLoading: boolean;
  error: string | null;
  login: (username: string, password: string) => Promise<void>;
  logout: () => void;
}

const AuthContext = createContext<AuthState | undefined>(undefined);

const AUTH_STORAGE_KEY = "resume_auth_token";
const AUTH_USER_KEY = "resume_auth_user";
const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "http://127.0.0.1:8001";

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<UserInfo | null>(null);
  const [token, setToken] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // 启动时从 localStorage 恢复 token
  useEffect(() => {
    try {
      const savedToken = localStorage.getItem(AUTH_STORAGE_KEY);
      const savedUser = localStorage.getItem(AUTH_USER_KEY);
      if (savedToken && savedUser) {
        setToken(savedToken);
        setUser(JSON.parse(savedUser));
      }
    } catch {
      // 损坏数据，清除
      localStorage.removeItem(AUTH_STORAGE_KEY);
      localStorage.removeItem(AUTH_USER_KEY);
    } finally {
      setIsLoading(false);
    }
  }, []);

  const logout = useCallback(() => {
    localStorage.removeItem(AUTH_STORAGE_KEY);
    localStorage.removeItem(AUTH_USER_KEY);
    setToken(null);
    setUser(null);
    setError(null);
  }, []);

  // 监听全局 auth:expired 事件（streamRequest / vision.ts 在 401 时派发）
  useEffect(() => {
    const handleExpired = () => {
      logout();
      setError("登录已失效，请重新认证");
    };
    window.addEventListener("auth:expired", handleExpired);
    return () => window.removeEventListener("auth:expired", handleExpired);
  }, [logout]);

  const login = useCallback(async (username: string, password: string) => {
    setError(null);
    setIsLoading(true);

    try {
      const response = await fetch(`${API_BASE}/api/v1/auth/login`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username, password }),
      });

      if (!response.ok) {
        const detail = await response.json().then((d) => d.detail).catch(() => "登录失败");
        throw new Error(typeof detail === "string" ? detail : "用户名或密码错误");
      }

      const data = await response.json();
      const userInfo: UserInfo = { id: 0, username: data.username };

      localStorage.setItem(AUTH_STORAGE_KEY, data.access_token);
      localStorage.setItem(AUTH_USER_KEY, JSON.stringify(userInfo));
      setToken(data.access_token);
      setUser(userInfo);
    } catch (err) {
      const msg = err instanceof Error ? err.message : "网络异常，请检查后端服务";
      setError(msg);
      throw err;
    } finally {
      setIsLoading(false);
    }
  }, []);

  return (
    <AuthContext.Provider value={{ user, token, isLoading, error, login, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) {
    throw new Error("useAuth 必须在 AuthProvider 内部使用");
  }
  return ctx;
}
