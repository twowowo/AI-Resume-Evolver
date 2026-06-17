/**
 * api.ts — v5.2 统一 HTTP 请求封装
 *
 * 每次请求自动从 localStorage 挂载 Authorization: Bearer <token>。
 * 遇到 401 时清除 token，触发重新登录。
 */

const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "http://127.0.0.1:8001";
const AUTH_STORAGE_KEY = "resume_auth_token";

function getToken(): string | null {
  try {
    return localStorage.getItem(AUTH_STORAGE_KEY);
  } catch {
    return null;
  }
}

function clearAuth(): void {
  try {
    localStorage.removeItem(AUTH_STORAGE_KEY);
    localStorage.removeItem("resume_auth_user");
  } catch {
    // ignore
  }
}

interface RequestOptions extends Omit<RequestInit, "headers"> {
  headers?: Record<string, string>;
}

async function request<T = unknown>(
  path: string,
  options: RequestOptions = {}
): Promise<T> {
  const token = getToken();
  const headers: Record<string, string> = {
    ...(options.headers ?? {}),
  };

  if (token) {
    headers["Authorization"] = `Bearer ${token}`;
  }

  const response = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers,
  });

  if (response.status === 401) {
    clearAuth();
    throw new Error("[401] 认证已失效，请重新登录");
  }

  if (!response.ok) {
    const detail = await response
      .json()
      .then((d) => d.detail)
      .catch(() => `服务器返回 ${response.status}`);
    throw new Error(typeof detail === "string" ? detail : `请求失败: ${response.status}`);
  }

  return response.json() as Promise<T>;
}

export { request, API_BASE, getToken, clearAuth };
