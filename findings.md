# Findings — 前端大屏 SSE 对接

## SSE 协议完整记录 (后端 v2.6)

### 端点

```
POST http://127.0.0.1:8000/api/v1/resume/optimize
Content-Type: application/json
```

### 请求体

```json
{
  "resume_text": "原始简历文本 (10-10000 字符)",
  "jd_text": "目标岗位 JD (10-5000 字符)",
  "mode": "one_click"
}
```

### SSE 响应事件序列

| 序号 | event | data 负载 | 触发时机 |
|------|-------|-----------|----------|
| 1 | `radar_init` | `{"original_resume_radar": {"jd_matching_score": int(0-60), "star_perf_score": int(0-30), "action_verbs_score": int(0-10), "total_score": int(0-100)}}` | PreEvaluator 初筛完成 |
| 2 | `resume_stream` | `{"optimized_resume_text": "string", "text_length": int}` | Editor 精修完成 |
| 3 | `final` | `{"optimized_resume_radar": {...}, "optimized_resume_text": "string", "stress_test_questions": [{"question_number": int, "category": "string", "question": "string", "expected_points": ["string"]}], "score_improvement": int, "difficulty_flag": "NORMAL/EXTREME_GAP", "iteration_count": int, "internal_monologue": "string"}` | Evaluator+Interviewer 完成 |
| 4 | `done` | `{}` | 流正常结束 |
| 5 | `error` | `{"error": "string"}` | 异常中断（随后推送 done） |

### SSE 帧格式

```
event: radar_init
data: {"original_resume_radar":{"jd_matching_score":50,"star_perf_score":18,"action_verbs_score":4,"total_score":72}}

```

- 每帧以 `event: <name>\ndata: <json>\n\n` 格式推送
- `data:` 后跟单行 JSON（`ensure_ascii=False`，中文原样输出）
- 帧间由 `\n\n` 分隔

### CORS

后端未显式配置 CORS 中间件。前端 Next.js dev server (localhost:3000) 请求 127.0.0.1:8000 可能触发跨域。需要确认后端是否有宽松 CORS 配置，或在 Next.js 中配置 rewrite 代理。

## 前端技术栈

- Next.js 16.2.6 (App Router)
- React 19.2.4
- Tailwind CSS 4
- shadcn/ui (card, button, input, textarea, badge, scroll-area, tabs)
- lucide-react 1.17.0 (图标库)
- tw-animate-css 1.4.0 (Tailwind 动画插件)
- radix-ui 1.4.3 (Tabs 基元)

## 已安装的 shadcn 组件

card, button, input, textarea, badge, scroll-area, tabs

## 设计决策

1. 使用 `fetch` + `ReadableStream` 消费 SSE（EventSource 仅支持 GET）
2. 打字机效果用 `useEffect` + `setInterval` 逐字追加
3. 雷达图用纯 CSS/SVG 绘制，不引入图表库
4. 暗黑主题强制启用（`.dark` 类固定在 `<html>`），无需主题切换
