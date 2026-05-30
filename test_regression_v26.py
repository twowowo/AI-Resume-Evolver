"""
v2.6 SSE 流式回归测试 — 验证三帧分段推送: radar_init → resume_stream → final
"""
import json
import os
import sys

sys.path.insert(0, os.path.abspath("."))

from dotenv import load_dotenv
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__) or ".", ".env"))

from fastapi.testclient import TestClient
from main import app
from src.utils.loader import load_docx, load_txt

client = TestClient(app)

# ── 加载测试数据 ──
resume_path = "data/resumes/测试简历1.docx"
jd_path = "data/jds/jd1.txt"
raw_resume = load_docx(resume_path)
target_jd = load_txt(jd_path)

print("=" * 65)
print("  v2.6 SSE 流式回归测试")
print("  radar_init → resume_stream → final → done")
print("=" * 65)


def parse_sse_events(response_text: str) -> dict[str, dict]:
    """解析 SSE 事件流，返回 {event_name: data_dict} 映射"""
    events = {}
    current_event = None
    current_data = None

    for line in response_text.split("\n"):
        line = line.strip()
        if not line:
            # 空行 = 事件结束
            if current_event and current_data is not None:
                try:
                    events[current_event] = json.loads(current_data)
                except json.JSONDecodeError:
                    events[current_event] = {"raw": current_data}
            current_event = None
            current_data = None
            continue

        if line.startswith("event: "):
            current_event = line[7:]
        elif line.startswith("data: "):
            current_data = line[6:]

    # 处理最后一条（如果没有尾随空行）
    if current_event and current_data is not None:
        try:
            events[current_event] = json.loads(current_data)
        except json.JSONDecodeError:
            events[current_event] = {"raw": current_data}

    return events


# ── Test 1: Health ──
print("\n[1/5] Health check...")
resp = client.get("/health")
assert resp.status_code == 200
assert resp.json()["version"] == "2.6.0"
print("  PASS: health ok (v2.6.0)")

# ── Test 2: INTERACTIVE 501 ──
print("\n[2/5] INTERACTIVE 模式 501 验证...")
resp = client.post("/api/v1/resume/optimize", json={
    "resume_text": raw_resume,
    "jd_text": target_jd,
    "mode": "interactive",
})
assert resp.status_code == 501
detail = resp.json().get("detail", "")
assert "对话式深度访谈模式正在研发中" in detail
print(f"  PASS: 501 + 标准提示语: {detail[:60]}...")

# ── Test 3: ONE_CLICK SSE 流式 ──
print("\n[3/5] ONE_CLICK SSE 流式全链路...")
payload = {"resume_text": raw_resume, "jd_text": target_jd, "mode": "one_click"}
resp = client.post("/api/v1/resume/optimize", json=payload, timeout=600)
assert resp.status_code == 200, f"Expected 200, got {resp.status_code}"

# 解析 SSE 事件流
events = parse_sse_events(resp.text)
print(f"  收到 {len(events)} 个 SSE 事件: {list(events.keys())}")

# ── Test 4: 逐帧校验 ──
print("\n[4/5] 逐帧结构化校验...")
errors = []

# Frame 1: radar_init
if "radar_init" not in events:
    errors.append("缺失 radar_init 事件")
else:
    radar_data = events["radar_init"]
    orig = radar_data.get("original_resume_radar", {})
    o_total = orig.get("total_score", 0)
    print(f"  Frame 1 [radar_init]: 原始雷达 {o_total}/100 "
          f"(JD: {orig.get('jd_matching_score')}/60, "
          f"STAR: {orig.get('star_perf_score')}/30, "
          f"Verb: {orig.get('action_verbs_score')}/10)")
    if o_total < 30:
        errors.append(f"原始总分 {o_total} < 30 熔断线")
    if o_total > 98:
        errors.append(f"原始总分 {o_total} > 98 满分上限异常")
    # 6-3-1 一致性
    expected = orig.get("jd_matching_score", 0) + orig.get("star_perf_score", 0) + orig.get("action_verbs_score", 0)
    if abs(o_total - expected) > 5:
        errors.append(f"radar_init 分项不一致: {expected} vs total={o_total}")

# Frame 2: resume_stream
if "resume_stream" not in events:
    errors.append("缺失 resume_stream 事件")
else:
    stream_data = events["resume_stream"]
    opt_text = stream_data.get("optimized_resume_text", "")
    text_len = stream_data.get("text_length", 0)
    print(f"  Frame 2 [resume_stream]: 精修文本 {text_len} 字符")
    if len(opt_text) < 500:
        errors.append(f"精修文本过短: {len(opt_text)} 字符")
    if len(opt_text) != text_len:
        errors.append(f"text_length 不一致: {text_len} vs actual {len(opt_text)}")

# Frame 3: final
if "final" not in events:
    errors.append("缺失 final 事件")
else:
    final_data = events["final"]
    opt = final_data.get("optimized_resume_radar", {})
    opt_total = opt.get("total_score", 0)
    questions = final_data.get("stress_test_questions", [])
    improvement = final_data.get("score_improvement", 0)
    iters = final_data.get("iteration_count", 0)
    flag = final_data.get("difficulty_flag", "")
    monologue = final_data.get("internal_monologue", "")

    print(f"  Frame 3 [final]: 终评雷达 {opt_total}/100 "
          f"(JD: {opt.get('jd_matching_score')}/60, "
          f"STAR: {opt.get('star_perf_score')}/30, "
          f"Verb: {opt.get('action_verbs_score')}/10)")
    print(f"    分数提升: +{improvement} 分")
    print(f"    压测题: {len(questions)} 道")
    print(f"    分诊标记: {flag}")
    print(f"    迭代轮次: {iters}")
    print(f"    内心独白: {'有' if len(monologue) > 20 else '无'} ({len(monologue)} 字符)")

    if opt_total < 70:
        errors.append(f"优化后总分 {opt_total} < 70")
    if opt_total < 50:
        errors.append(f"优化后总分 {opt_total} < 50 合理区间下限")
    if opt_total > 98:
        errors.append(f"优化后总分 {opt_total} > 98 满分上限异常")

    # 6-3-1 分项一致性
    jd = opt.get("jd_matching_score", 0)
    star = opt.get("star_perf_score", 0)
    verb = opt.get("action_verbs_score", 0)
    expected_sum = jd + star + verb
    if abs(opt_total - expected_sum) > 5:
        errors.append(f"final 分项不一致: {jd}+{star}+{verb}={expected_sum} vs total={opt_total}")

    if improvement < 0:
        errors.append(f"分数负提升: +{improvement}")
    elif improvement < 10:
        print(f"    注意: 提升幅度较小 ({improvement} 分)，但仍为正梯度")

    if len(questions) < 3:
        errors.append(f"压测题不足 3 道: {len(questions)}")

    for q in questions:
        qn = q.get("question_number", "?")
        cat = q.get("category", "?")
        question = q.get("question", "")
        points = q.get("expected_points", [])
        print(f"    Q{qn} [{cat}]: {question[:100]}...")
        print(f"       期望要点: {len(points)} 个")
        if len(question) < 30:
            errors.append(f"Q{qn} 题目过短: {len(question)} 字符")
        if len(points) < 2:
            errors.append(f"Q{qn} 期望要点不足: {len(points)} 个")

# Frame 4: done
if "done" not in events:
    errors.append("缺失 done 事件")
else:
    print(f"  Frame 4 [done]: 流正常关闭")

# 帧顺序校验
event_order = list(events.keys())
expected_order = ["radar_init", "resume_stream", "final", "done"]
if event_order != expected_order:
    print(f"  注意: 事件顺序 {event_order} 与预期 {expected_order} 不完全一致（可能含重复中间帧，非致命）")

# ── Test 5: 汇总 ──
print(f"\n[5/5] 结果汇总")
print("-" * 65)
if errors:
    print(f"  FAILURES ({len(errors)}):")
    for e in errors:
        print(f"    - {e}")
else:
    print(f"  全部校验通过!")

orig_radar = events.get("radar_init", {}).get("original_resume_radar", {})
final_radar = events.get("final", {}).get("optimized_resume_radar", {})
o_total = orig_radar.get("total_score", 0)
opt_total = final_radar.get("total_score", 0)
improvement = events.get("final", {}).get("score_improvement", 0)
questions = events.get("final", {}).get("stress_test_questions", [])
opt_text = events.get("resume_stream", {}).get("optimized_resume_text", "")

print(f"\n  初筛 {o_total} 分 → 终评 {opt_total} 分 (+{improvement})")
print(f"  SSE 事件: {list(events.keys())}")
print(f"  MockInterviewer 压测题: {len(questions)} 道")
print(f"  精修文本: {len(opt_text)} 字符")

print("\n" + "=" * 65)
if errors:
    print("  REGRESSION TEST: FAILED")
    sys.exit(1)
else:
    print("  REGRESSION TEST: ALL PASSED")
print("=" * 65)
