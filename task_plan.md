# Task Plan: AI-Resume-Evolver 核心节点深度开发

## Goal
在纯净 v2.0 LangGraph 多智能体博弈架构上，持续打磨全链路智能体质量。

## Current Phase
Phase 7 完成 —— SSE StreamingResponse 流式重构 + 三帧分段推送

## Phases

### Phase 1-3.5: 基础架构 + 算法纠偏 ✅
- **Status:** complete

### Phase 4: 终极博弈论架构升级 (pending)

### Phase 5: FastAPI 路由网关 + 数据契约 ✅
- **Status:** complete

### Phase 6: 502 故障抢救 + MockInterviewer 并网 + v2.5 回归 ✅
- **Status:** complete

### Phase 7: SSE StreamingResponse 流式重构 ✅
- [x] 7-a: ONE_CLICK 端点升级为 StreamingResponse (text/event-stream)
- [x] 7-b: 三帧 SSE 推送: radar_init → resume_stream → final → done
- [x] 7-c: ThreadPoolExecutor + asyncio.Queue 桥接同步 LangGraph stream
- [x] 7-d: 标准化 INTERACTIVE 501 提示语
- [x] 7-e: 审计三节点 (无 TODO/硬编码)
- [x] 7-f: v2.6 SSE 流式回归测试 (72→93 稳定梯度)
- **Status:** complete

---

## 当前 v2.6 架构

```
main.py (FastAPI :8000, 127.0.0.1, SSE StreamingResponse)
       │
       ├─ GET  /health
       ├─ POST /api/v1/resume/optimize
       │   ├─ ONE_CLICK → SSE text/event-stream (ThreadPoolExecutor + asyncio.Queue)
       │   │   ├── Frame 1 (radar_init):    PreEvaluator 初筛 → 原始简历雷达
       │   │   ├── Frame 2 (resume_stream): Editor 精修 → 简历全文打字机
       │   │   ├── Frame 3 (final):         Evaluator+Interviewer → 终评雷达 + 压测题
       │   │   └── Frame 4 (done):          流关闭
       │   └─ INTERACTIVE → 501 (标准化提示)
       │
       └── src/graph.py
              │
              ├── retriever → [tavily?] → pre_evaluator (v2.3 双轨制)
              │                                    │
              ├──────────────────────────── editor (满血版)
              │                                    │
              ├──────────────────────────── evaluator (v2.3 6-3-1 + STAR溢价)
              │                                    │
              ├────── [polisher ⇄ evaluator 闭环] ─┘
              │
              └────── interviewer (v2.5 架构师拷问) → END
```

## Key Design Decisions
| 决策 | 说明 |
|------|------|
| ThreadPoolExecutor + asyncio.Queue | 桥接同步 LangGraph.stream() 与异步 SSE 推送，保持事件循环不阻塞 |
| stream_mode="values" | 每个节点完成后获取全量状态快照，按里程碑检测触发 SSE 事件 |
| timeout_keep_alive=300 | 保留 5 分钟弹性超时覆盖完整串行链路 |
| X-Accel-Buffering: no | 禁用 Nginx 代理缓冲，确保 SSE 实时推送 |
