/**
 * SSE 协议类型定义 —— 对齐后端双模（一键流水线 + Agent ReAct）所有事件帧
 */

// ── 后端推送的 SSE 事件名枚举 ──
export type PipelineEvent =
  | "radar_init"
  | "resume_stream"
  | "final"
  | "done"
  | "error";

export type AgentEvent =
  | "START"
  | "NODE_CHANGED"
  | "END"
  | "ERROR"
  | "ABORTED"
  | "RESIDUAL";

// ── 诊断原文 ──
export interface DiagnosisData {
  feedback: string;               // "列出最关键的 2-3 个问题"
  core_tool_overlap: string;      // "FastAPI/Redis/MySQL/Docker" 或层级评估
  matched_skills: string[];       // JD 要求且简历已覆盖的技术栈
  missing_skills: string[];       // JD 要求但简历未体现的技术栈
  star_strengths: string[];       // 原始简历 STAR 做得好的点
  star_weaknesses: string[];      // 原始简历 STAR 缺失的点
  weak_verbs: string[];           // 简历中弱动词
}

// ── 6-3-1 雷达指标 ──
export interface RadarScores {
  jd_matching_score: number;  // 0-60
  star_perf_score: number;    // 0-30
  action_verbs_score: number; // 0-10
  total_score: number;        // 0-100
}

// ── 面试压测题 ──
export interface StressTestQuestion {
  question_number: number;
  category: string;
  question: string;
  expected_points: string[];
}

// ── v4.5 混合解耦载荷 ──
export interface VisualPayload {
  name: string;                // 纯中文姓名，严禁拼音
  contact: string;             // "手机：138-XXXX-XXXX | 邮箱：xxx@xxx.com"
  skills: string[];            // ["Python", "LangGraph", "ChromaDB", "FastAPI"]
  main_resume_markdown: string; // 全量简历 Markdown（已清洗裸奔星号）
}

// ── 一键流水线各帧负载 ──
export interface RadarInitFrame {
  original_resume_radar: RadarScores;
  diagnosis?: DiagnosisData;
}

export interface ResumeStreamFrame {
  optimized_resume_text: string;
  text_length: number;
  optimization_summary: string;
  clean_resume_json: Record<string, unknown>;
  visual_payload?: VisualPayload;
}

export interface FinalFrame {
  optimized_resume_radar: RadarScores;
  optimized_resume_text: string;
  stress_test_questions: StressTestQuestion[];
  difficulty_flag: string;
  is_extreme_gap: boolean;
  iteration_count: number;
  score_improvement: number;
  display_score_change: boolean;
  circuit_breaker_triggered: boolean;
  internal_monologue: string;
  evaluation_feedback: string;
  pre_eval_dimensions: Record<string, number>;
  eval_dimensions: Record<string, number>;
  optimization_summary: string;
  clean_resume_json: Record<string, unknown>;
  visual_payload?: VisualPayload;
  session_id: string;
}

// ── Agent ReAct 各帧负载 ──
export interface AgentNodeChangedData {
  node_name: string;
  has_messages: boolean;
  msg_type?: string;
  content?: string;
  tool_calls?: Array<{ name: string; args: Record<string, unknown> }>;
}

// ── 通用 SSE 已解析帧 ──
export interface ParsedSSEFrame<T = unknown> {
  event: string;
  data: T;
}

// ── 流水线流状态快照 ──
export interface PipelineStreamState {
  phase: "idle" | "radar_init" | "resume_stream" | "final" | "done" | "error";
  originalRadar: RadarScores | null;
  diagnosis: DiagnosisData | null;
  optimizedText: string;
  optimizedRadar: RadarScores | null;
  questions: StressTestQuestion[];
  monologue: string;
  scoreImprovement: number;
  displayScoreChange: boolean;
  circuitBreakerTriggered: boolean;
  sessionId: string;
  error: string | null;
  visualPayload: VisualPayload | null;
}
