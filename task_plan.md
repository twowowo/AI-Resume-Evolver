# Task Plan — AI-Resume-Evolver 前端大屏交付

**日期**: 2026-06-03
**状态**: 实施中

## 目标

为 `ai-resume-frontend` (Next.js + Tailwind + shadcn/ui) 编写核心可视化交互大屏，对接后端 v2.6 SSE 流式分帧网关。

## 阶段

| # | 阶段 | 状态 | 产出 |
|---|------|------|------|
| 1 | API 调研 | ✅ complete | findings.md — SSE 协议完整记录 |
| 2 | 核心 UI + SSE 管道 | 🔄 in_progress | page.tsx 重写、SSE hook、暗黑科技风全屏 |
| 3 | Playwright 联调测试 | ⏳ pending | e2e/resume-optimize.spec.ts |
| 4 | 落盘 + 启动命令 | ⏳ pending | 所有文件保存、终端输出 |

## 架构决策

- **SSE 解析**: 纯 `fetch + ReadableStream`，不引入 EventSource（EventSource 只支持 GET）
- **状态管理**: React `useState` + `useRef`，无需引入 Redux/Zustand
- **打字机效果**: `useEffect` + `requestAnimationFrame` 分帧追加，流畅不卡顿
- **暗黑主题**: Zinc 灰度 + 强制 dark（`.dark` 类始终激活），无需切换

## 关键约束

- 后端地址硬编码 `http://127.0.0.1:8000`
- CORS 已由后端 FastAPI 中间件处理
- 前端仅消费 SSE，不修改后端任何文件
