/**
 * useAgentStream — Agent ReAct 大脑 SSE 流式 Hook (v5.3 全局常驻版本)
 *
 * 对接后端 POST /api/agent/stream
 * 事件帧: START → NODE_CHANGED* → END (或 ERROR) → ABORTED
 *
 * v5.3: 所有状态迁移至 AgentSessionContext 全局常驻容器，
 * 组件卸载/模式切换不再蒸发对话历史。AbortController 由
 * useGlobalAbortController 统一托管。
 *
 * 返回:
 *   - startStream(query) → 点火流式连接
 *   - nodeLogs[]       → 累积的节点变更日志（全局持久）
 *   - isStreaming      → 流是否活跃
 *   - error            → 异常信息
 */

"use client";

import { useCallback } from "react";
import { parseSSEStream } from "@/lib/sse-parser";
import { streamRequest } from "@/lib/api";
import { useAuth } from "@/contexts/AuthContext";

function uuid(): string {
  try {
    return crypto.randomUUID();
  } catch {
    return "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g, (c) => {
      const r = (Math.random() * 16) | 0;
      return (c === "x" ? r : (r & 0x3) | 0x8).toString(16);
    });
  }
}
import {
  useAgentSession,
  useAgentSessionDispatch,
  useGlobalAbortController,
} from "@/contexts/AgentSessionContext";
import type { AgentNodeChangedData } from "@/types/sse";

export interface NodeLog {
  id: string;
  nodeName: string;
  msgType: string;
  content: string;
  toolCalls: Array<{ name: string; args: Record<string, unknown> }>;
  timestamp: number;
}

export function useAgentStream() {
  const { user } = useAuth();
  const { messages: nodeLogs, isStreaming, isThinking, error, sessionId } = useAgentSession();
  const dispatch = useAgentSessionDispatch();
  const { createController, abort } = useGlobalAbortController();

  const startStream = useCallback(async (userQuery: string) => {
    // 中断上一次未完成的流（全局 AbortController 托管）
    const controller = createController();

    dispatch({ type: "SET_STREAMING", payload: true });
    dispatch({ type: "SET_THINKING", payload: true });
    dispatch({ type: "SET_ERROR", payload: null });

    // 增量追加用户输入伪帧，保留历史多轮对话上下文
    const userLog: NodeLog = {
      id: uuid(),
      nodeName: "user",
      msgType: "HumanMessage",
      content: userQuery,
      toolCalls: [],
      timestamp: Date.now(),
    };
    dispatch({ type: "ADD_MESSAGE", payload: userLog });

    try {
      const response = await streamRequest("/api/agent/stream", {
        method: "POST",
        body: JSON.stringify({
          user_query: userQuery,
          user_id: user?.username ?? "",
          thread_id: sessionId || undefined,
        }),
        signal: controller.signal,
      });

      if (!response.body) {
        throw new Error("后端未返回 ReadableStream body");
      }

      for await (const frame of parseSSEStream<AgentNodeChangedData>(
        response.body,
        controller.signal
      )) {
        switch (frame.event) {
          case "START":
            break;

          case "NODE_CHANGED": {
            const nd = frame.data as AgentNodeChangedData;
            const hasContent = nd?.content && nd.content.trim().length > 0;

            // 首个真实非空 Token 抵达 → 熄灭思考锁
            if (hasContent) {
              dispatch({ type: "SET_THINKING", payload: false });
            }

            dispatch({
              type: "ADD_MESSAGE",
              payload: {
                id: uuid(),
                nodeName: nd?.node_name ?? "unknown",
                msgType: nd?.msg_type ?? "",
                content: nd?.content ?? "",
                toolCalls: nd?.tool_calls ?? [],
                timestamp: Date.now(),
              },
            });
            break;
          }

          case "END": {
            const endData = frame.data as { summary?: string; session_id?: string };
            if (endData?.session_id) {
              dispatch({ type: "SET_SESSION_ID", payload: endData.session_id });
            }
            break;
          }

          case "ABORTED": {
            // 后端确认熔断 + 状态已回滚
            const abortedData = frame.data as unknown as Record<string, unknown> | undefined;
            if (abortedData?.session_id) {
              dispatch({ type: "SET_SESSION_ID", payload: abortedData.session_id as string });
            }
            dispatch({
              type: "ADD_MESSAGE",
              payload: {
                id: uuid(),
                nodeName: "abort_handler",
                msgType: "SystemNotification",
                content: (abortedData?.content as string) ?? "会话已安全中止",
                toolCalls: [],
                timestamp: Date.now(),
              },
            });
            break;
          }

          case "RESIDUAL":
            dispatch({
              type: "ADD_MESSAGE",
              payload: {
                id: uuid(),
                nodeName: "residual",
                msgType: "",
                content: typeof frame.data === "string" ? frame.data : JSON.stringify(frame.data),
                toolCalls: [],
                timestamp: Date.now(),
              },
            });
            break;

          case "ERROR":
            dispatch({
              type: "SET_ERROR",
              payload: (frame.data as { data?: string })?.data ?? "Agent 大脑运行时异常",
            });
            break;

          default: {
            const unknownData = frame.data as unknown as Record<string, unknown> | undefined;
            const fallbackContent =
              (unknownData?.content as string) ??
              (typeof unknownData === "string" ? unknownData : "") ??
              "";
            if (fallbackContent) {
              dispatch({
                type: "ADD_MESSAGE",
                payload: {
                  id: uuid(),
                  nodeName: (unknownData?.node_name as string) ?? frame.event,
                  msgType: (unknownData?.msg_type as string) ?? "",
                  content: fallbackContent,
                  toolCalls: (unknownData?.tool_calls as NodeLog["toolCalls"]) ?? [],
                  timestamp: Date.now(),
                },
              });
            }
            break;
          }
        }
      }
    } catch (err: unknown) {
      if (err instanceof DOMException && err.name === "AbortError") {
        // 用户主动中断，后端已通过 CancelledError 处理
        return;
      }
      dispatch({
        type: "SET_ERROR",
        payload: err instanceof Error ? err.message : "未知流异常",
      });
    } finally {
      dispatch({ type: "SET_THINKING", payload: false });
      dispatch({ type: "SET_STREAMING", payload: false });
    }
  }, [createController, dispatch, sessionId, user?.username]);

  return { nodeLogs, isStreaming, isThinking, error, startStream, abort };
}
