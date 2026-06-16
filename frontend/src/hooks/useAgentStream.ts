/**
 * useAgentStream — Agent ReAct 大脑 SSE 流式 Hook
 *
 * 对接后端 POST /api/agent/stream
 * 事件帧: START → NODE_CHANGED* → END (或 ERROR)
 *
 * 返回:
 *   - startStream(query) → 点火流式连接
 *   - nodeLogs[]       → 累积的节点变更日志
 *   - isStreaming      → 流是否活跃
 *   - error            → 异常信息
 */

"use client";

import { useState, useRef, useCallback } from "react";
import { parseSSEStream } from "@/lib/sse-parser";
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
  const [nodeLogs, setNodeLogs] = useState<NodeLog[]>([]);
  const [isStreaming, setIsStreaming] = useState(false);
  const [isThinking, setIsThinking] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  const startStream = useCallback(async (userQuery: string) => {
    // 中断上一次未完成的流
    abortRef.current?.abort();

    const controller = new AbortController();
    abortRef.current = controller;

    setIsStreaming(true);
    setIsThinking(true);  // 发送瞬间立刻拉起思考锁
    setError(null);

    // 增量追加用户输入伪帧，保留历史多轮对话上下文
    const userLog: NodeLog = {
      id: crypto.randomUUID(),
      nodeName: "user",
      msgType: "HumanMessage",
      content: userQuery,
      toolCalls: [],
      timestamp: Date.now(),
    };
    setNodeLogs((prev) => [...prev, userLog]);

    try {
      const response = await fetch("http://127.0.0.1:8001/api/agent/stream", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          user_query: userQuery,
          user_id: "default_user",     // v4.2 演示期默认值，后续从 auth context 注入
          resume_id: "default_resume", // v4.2 演示期默认值，后续从文件 Hash 动态计算
        }),
        signal: controller.signal,
      });

      if (!response.ok) {
        throw new Error(`后端返回 ${response.status}: ${response.statusText}`);
      }

      if (!response.body) {
        throw new Error("后端未返回 ReadableStream body");
      }

      for await (const frame of parseSSEStream<AgentNodeChangedData>(
        response.body,
        controller.signal
      )) {
        switch (frame.event) {
          case "START":
            // 点火确认帧，可忽略或做 UI 过渡
            break;

          case "NODE_CHANGED": {
            const nd = frame.data as AgentNodeChangedData;
            const hasContent = nd?.content && nd.content.trim().length > 0;

            // 首个真实非空 Token 抵达 → 熄灭思考锁，平滑交接给打字流
            if (hasContent) {
              setIsThinking((prev) => (prev ? false : prev));
            }

            setNodeLogs((prev) => [
              ...prev,
              {
                id: crypto.randomUUID(),
                nodeName: nd?.node_name ?? "unknown",
                msgType: nd?.msg_type ?? "",
                content: nd?.content ?? "",
                toolCalls: nd?.tool_calls ?? [],
                timestamp: Date.now(),
              },
            ]);
            break;
          }

          case "END":
            // 流正常收敛
            break;

          case "RESIDUAL":
            // 流结束时的残帧透传：尽力追加到日志
            setNodeLogs((prev) => [
              ...prev,
              {
                id: crypto.randomUUID(),
                nodeName: "residual",
                msgType: "",
                content: typeof frame.data === "string" ? frame.data : JSON.stringify(frame.data),
                toolCalls: [],
                timestamp: Date.now(),
              },
            ]);
            break;

          case "ERROR":
            setError((frame.data as { data?: string })?.data ?? "Agent 大脑运行时异常");
            break;

          default: {
            // 兜底：任何未识别的事件帧，只要有 content 文本就追加到日志
            const unknownData = frame.data as unknown as Record<string, unknown> | undefined;
            const fallbackContent =
              (unknownData?.content as string) ??
              (typeof unknownData === "string" ? unknownData : "") ??
              "";
            if (fallbackContent) {
              setNodeLogs((prev) => [
                ...prev,
                {
                  id: crypto.randomUUID(),
                  nodeName: (unknownData?.node_name as string) ?? frame.event,
                  msgType: (unknownData?.msg_type as string) ?? "",
                  content: fallbackContent,
                  toolCalls: (unknownData?.tool_calls as NodeLog["toolCalls"]) ?? [],
                  timestamp: Date.now(),
                },
              ]);
            }
            break;
          }
        }
      }
    } catch (err: unknown) {
      if (err instanceof DOMException && err.name === "AbortError") {
        // 用户主动中断，不报错
        return;
      }
      setError(err instanceof Error ? err.message : "未知流异常");
    } finally {
      setIsThinking(false);   // 防死锁：无论成功/失败/中断，强行拉回 false
      setIsStreaming(false);
    }
  }, []);

  const abort = useCallback(() => {
    abortRef.current?.abort();
  }, []);

  return { nodeLogs, isStreaming, isThinking, error, startStream, abort };
}
