/**
 * usePipelineStream — 一键流水线 SSE 流式 Hook
 *
 * 对接后端 POST /api/v1/resume/optimize (ONE_CLICK 模式)
 * 事件帧序列: radar_init → resume_stream → final → done
 *
 * 返回:
 *   - startPipeline(resume, jd) → 点火流式连接
 *   - state → PipelineStreamState 全量快照
 *   - isStreaming / abort
 */

"use client";

import { useState, useRef, useCallback } from "react";
import { parseSSEStream } from "@/lib/sse-parser";
import { streamRequest } from "@/lib/api";
import { useAuth } from "@/contexts/AuthContext";
import type {
  RadarInitFrame,
  ResumeStreamFrame,
  FinalFrame,
  PipelineStreamState,
} from "@/types/sse";

const INITIAL_STATE: PipelineStreamState = {
  phase: "idle",
  originalRadar: null,
  diagnosis: null,
  optimizedText: "",
  optimizedRadar: null,
  questions: [],
  monologue: "",
  scoreImprovement: 0,
  displayScoreChange: true,
  circuitBreakerTriggered: false,
  sessionId: "",
  error: null,
  visualPayload: null,
};

export function usePipelineStream() {
  const { user } = useAuth();
  const [state, setState] = useState<PipelineStreamState>(INITIAL_STATE);
  const [isStreaming, setIsStreaming] = useState(false);
  const [isGenerated, setIsGenerated] = useState(false);
  const abortRef = useRef<AbortController | null>(null);

  const startPipeline = useCallback(
    async (resumeText: string, jdText: string) => {
      abortRef.current?.abort();
      const controller = new AbortController();
      abortRef.current = controller;

      setIsStreaming(true);
      setIsGenerated(false);
      setState(INITIAL_STATE);

      try {
        const response = await streamRequest("/api/v1/resume/optimize", {
          method: "POST",
          body: JSON.stringify({
            resume_text: resumeText,
            jd_text: jdText,
            mode: "one_click",
            user_id: user?.username ?? "",
          }),
          signal: controller.signal,
        });

        if (!response.body) {
          throw new Error("后端未返回 ReadableStream body");
        }

        for await (const frame of parseSSEStream(
          response.body,
          controller.signal
        )) {
          switch (frame.event) {
            case "radar_init": {
              const d = frame.data as RadarInitFrame;
              setState((prev) => ({
                ...prev,
                phase: "radar_init",
                originalRadar: d.original_resume_radar,
                diagnosis: d.diagnosis ?? null,
              }));
              break;
            }

            case "resume_stream": {
              const d = frame.data as ResumeStreamFrame;
              setState((prev) => ({
                ...prev,
                phase: "resume_stream",
                optimizedText: d.optimized_resume_text,
                visualPayload: d.visual_payload ?? prev.visualPayload,
              }));
              break;
            }

            case "final": {
              const d = frame.data as FinalFrame;
              setState((prev) => ({
                ...prev,
                phase: "final",
                optimizedRadar: d.optimized_resume_radar,
                optimizedText: d.optimized_resume_text,
                questions: d.stress_test_questions,
                monologue: d.internal_monologue,
                scoreImprovement: d.score_improvement,
                displayScoreChange: d.display_score_change ?? true,
                circuitBreakerTriggered: d.circuit_breaker_triggered ?? false,
                sessionId: d.session_id,
                visualPayload: d.visual_payload ?? prev.visualPayload,
              }));
              break;
            }

            case "done":
              setState((prev) => ({ ...prev, phase: "done" }));
              setIsGenerated(true);
              break;

            case "error":
              setState((prev) => ({
                ...prev,
                phase: "error",
                error: (frame.data as { error?: string })?.error ?? "未知异常",
              }));
              break;
          }
        }
      } catch (err: unknown) {
        if (err instanceof DOMException && err.name === "AbortError") {
          return;
        }
        setState((prev) => ({
          ...prev,
          phase: "error",
          error: err instanceof Error ? err.message : "未知流异常",
        }));
      } finally {
        setIsStreaming(false);
      }
    },
    []
  );

  const abort = useCallback(() => {
    abortRef.current?.abort();
  }, []);

  return { state, isStreaming, isGenerated, startPipeline, abort };
}
