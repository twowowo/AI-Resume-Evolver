/**
 * AgentSessionContext — 全局常驻会话状态容器
 *
 * 解决组件卸载/模式切换时 useState 蒸发导致的对话历史与 session_id 丢失。
 * 使用 React Context + useReducer 实现，无需额外依赖。
 */
"use client";

import {
  createContext,
  useContext,
  useReducer,
  useCallback,
  useRef,
  type ReactNode,
} from "react";
import type { NodeLog } from "@/hooks/useAgentStream";

// ── 状态结构 ──
interface AgentSessionState {
  messages: NodeLog[];
  sessionId: string;
  isThinking: boolean;
  isStreaming: boolean;
  error: string | null;
  /** 最后已知的简历全文（管道产出后缓存） */
  resumeText: string;
  /** 最后已知的 JD 全文 */
  jdText: string;
}

// ── Action 联合 ──
type AgentSessionAction =
  | { type: "ADD_MESSAGE"; payload: NodeLog }
  | { type: "SET_MESSAGES"; payload: NodeLog[] }
  | { type: "CLEAR_MESSAGES" }
  | { type: "SET_SESSION_ID"; payload: string }
  | { type: "SET_THINKING"; payload: boolean }
  | { type: "SET_STREAMING"; payload: boolean }
  | { type: "SET_RESUME_TEXT"; payload: string }
  | { type: "SET_JD_TEXT"; payload: string }
  | { type: "SET_ERROR"; payload: string | null }
  | { type: "RESET_SESSION" };

// ── Reducer ──
function agentSessionReducer(
  state: AgentSessionState,
  action: AgentSessionAction
): AgentSessionState {
  switch (action.type) {
    case "ADD_MESSAGE":
      return { ...state, messages: [...state.messages, action.payload] };
    case "SET_MESSAGES":
      return { ...state, messages: action.payload };
    case "CLEAR_MESSAGES":
      return { ...state, messages: [] };
    case "SET_SESSION_ID":
      return { ...state, sessionId: action.payload };
    case "SET_THINKING":
      return { ...state, isThinking: action.payload };
    case "SET_STREAMING":
      return { ...state, isStreaming: action.payload };
    case "SET_RESUME_TEXT":
      return { ...state, resumeText: action.payload };
    case "SET_JD_TEXT":
      return { ...state, jdText: action.payload };
    case "SET_ERROR":
      return { ...state, error: action.payload };
    case "RESET_SESSION":
      return {
        ...state,
        messages: [],
        isThinking: false,
        isStreaming: false,
      };
    default:
      return state;
  }
}

const INITIAL_STATE: AgentSessionState = {
  messages: [],
  sessionId: "",
  isThinking: false,
  isStreaming: false,
  error: null,
  resumeText: "",
  jdText: "",
};

// ── Context ──
const StateCtx = createContext<AgentSessionState>(INITIAL_STATE);
const DispatchCtx = createContext<React.Dispatch<AgentSessionAction>>(() => {});

export function AgentSessionProvider({ children }: { children: ReactNode }) {
  const [state, dispatch] = useReducer(agentSessionReducer, INITIAL_STATE);
  return (
    <StateCtx.Provider value={state}>
      <DispatchCtx.Provider value={dispatch}>{children}</DispatchCtx.Provider>
    </StateCtx.Provider>
  );
}

// ── 便捷 Hook ──
export function useAgentSession() {
  return useContext(StateCtx);
}

export function useAgentSessionDispatch() {
  return useContext(DispatchCtx);
}

/**
 * 返回全局 AbortController 管理钩子。
 * AbortController 不能序列化进 reducer，用 useRef 单独托管。
 */
export function useGlobalAbortController() {
  const abortRef = useRef<AbortController | null>(null);

  const createController = useCallback(() => {
    abortRef.current?.abort();
    const ctrl = new AbortController();
    abortRef.current = ctrl;
    return ctrl;
  }, []);

  const abort = useCallback(() => {
    abortRef.current?.abort();
    abortRef.current = null;
  }, []);

  return { abortRef, createController, abort };
}
