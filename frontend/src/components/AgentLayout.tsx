"use client";

import { useCallback } from "react";
import { useAgentStream } from "@/hooks/useAgentStream";
import AgentConsole from "./AgentConsole";
import AgentRightPanel from "./AgentRightPanel";

/**
 * Agent 模式布局 —— useAgentStream 提升到此层管理，
 * nodeLogs 同时注入左轴 AgentConsole（日志渲染）和右轴 AgentRightPanel（简历画布 + 智脑洞察看板），
 * 实现"一次流式推送，三轴同步消费"。
 */
export default function AgentLayout() {
  const { nodeLogs, isStreaming, isThinking, error, startStream, abort } = useAgentStream();

  const handleSubmit = useCallback(
    (query: string) => {
      startStream(query);
    },
    [startStream]
  );

  return (
    <div className="flex h-full w-full">
      {/* 左轴：Agent 大脑控制台（受控模式） */}
      <div className="w-[45%] min-w-[380px] h-full">
        <AgentConsole
          nodeLogs={nodeLogs}
          isStreaming={isStreaming}
          isThinking={isThinking}
          error={error}
          onSubmit={handleSubmit}
          onAbort={abort}
          subtitle="纯 Agent 智脑交互 · 全局自由指令"
        />
      </div>

      {/* 右轴：Tab 容器（简历画布 + 智脑洞察看板） */}
      <div className="flex-1 h-full">
        <AgentRightPanel nodeLogs={nodeLogs} />
      </div>
    </div>
  );
}
