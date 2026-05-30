"""
v2.5 回归测试脚本 — 全链路: retriever → pre_evaluator → editor → evaluator → interviewer
"""
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
print("  v2.5 全链路回归测试")
print("  retriever → pre_evaluator → editor → evaluator → interviewer")
print("=" * 65)

# ── Test 1: Health ──
print("\n[1/4] Health check...")
resp = client.get("/health")
assert resp.status_code == 200
assert resp.json()["version"] == "2.5.0"
print("  PASS: health ok")

# ── Test 2: ONE_CLICK ──
print("\n[2/4] ONE_CLICK 全链路优化...")
payload = {"resume_text": raw_resume, "jd_text": target_jd, "mode": "one_click"}
resp = client.post("/api/v1/resume/optimize", json=payload, timeout=600)
assert resp.status_code == 200, f"Expected 200, got {resp.status_code}"
data = resp.json()

# ── Validate ──
print("\n[3/4] 结构化数据验证...")
errors = []

# success
if not data.get("success"):
    errors.append("success=False")
    print(f"  FAIL: success=False, message={data.get('message')}")

# original radar
orig = data.get("original_resume_radar", {})
o_total = orig.get("total_score", 0)
print(f"  原始简历雷达: JD {orig.get('jd_matching_score')}/60, "
      f"STAR {orig.get('star_perf_score')}/30, "
      f"Verb {orig.get('action_verbs_score')}/10, "
      f"Total {o_total}/100")
if o_total < 30:
    errors.append(f"原始总分 {o_total} < 30 熔断线")

# optimized radar
opt = data.get("optimized_resume_radar") or {}
opt_total = opt.get("total_score", 0)
print(f"  优化后雷达:   JD {opt.get('jd_matching_score')}/60, "
      f"STAR {opt.get('star_perf_score')}/30, "
      f"Verb {opt.get('action_verbs_score')}/10, "
      f"Total {opt_total}/100")
if opt_total < 70:
    errors.append(f"优化后总分 {opt_total} < 70")
if opt_total < 50:
    errors.append(f"优化后总分 {opt_total} < 50 合理区间下限")
if opt_total > 98:
    errors.append(f"优化后总分 {opt_total} > 98 满分上限异常")

# score gradient
if o_total > 0 and opt_total > 0:
    improvement = opt_total - o_total
    print(f"  分数梯度: {o_total} → {opt_total} (+{improvement})")
    if improvement < 0:
        errors.append(f"优化后分数反而下降: {o_total} → {opt_total}")
    elif improvement < 10:
        print(f"  注意: 提升幅度较小 ({improvement} 分)，但仍为正梯度")

# optimized text
opt_text = data.get("optimized_resume_text", "")
print(f"  精修文本: {len(opt_text)} 字符")
if len(opt_text) < 500:
    errors.append(f"精修文本过短: {len(opt_text)} 字符")

# stress test questions
questions = data.get("stress_test_questions", [])
print(f"  压测题: {len(questions)} 道")
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

if len(questions) < 3:
    errors.append(f"压测题不足 3 道: {len(questions)}")

# 6-3-1 三维分项一致性
jd = opt.get("jd_matching_score", 0)
star = opt.get("star_perf_score", 0)
verb = opt.get("action_verbs_score", 0)
expected_total = jd + star + verb
if abs(opt_total - expected_total) > 5:
    errors.append(f"6-3-1 分项不一致: {jd}+{star}+{verb}={expected_total} vs total={opt_total}")

# internal_monologue
monologue = data.get("internal_monologue", "")
has_monologue = len(monologue) > 20
print(f"  内心独白: {'有' if has_monologue else '无'} ({len(monologue)} 字符)")

# difficulty_flag
flag = data.get("difficulty_flag", "")
print(f"  分诊标记: {flag}")

# iteration_count
iters = data.get("iteration_count", 0)
print(f"  迭代轮次: {iters}")

# ── Summary ──
print(f"\n[4/4] 结果汇总")
print("-" * 65)
if errors:
    print(f"  FAILURES ({len(errors)}):")
    for e in errors:
        print(f"    - {e}")
else:
    print(f"  全部校验通过!")

print(f"\n  初筛 {o_total} 分 → 终评 {opt_total} 分 (+{improvement if o_total > 0 else 'N/A'})")
print(f"  MockInterviewer 压测题: {len(questions)} 道")
print(f"  精修文本: {len(opt_text)} 字符")
print(f"  分诊标记: {flag}")

# ── Test 3: INTERACTIVE ──
print(f"\n[Bonus] INTERACTIVE 模式 501 验证...")
resp = client.post("/api/v1/resume/optimize", json={
    "resume_text": raw_resume,
    "jd_text": target_jd,
    "mode": "interactive",
})
assert resp.status_code == 501
print("  PASS: 交互模式正确返回 501")

print("\n" + "=" * 65)
if errors:
    print("  REGRESSION TEST: FAILED")
    sys.exit(1)
else:
    print("  REGRESSION TEST: ALL PASSED")
print("=" * 65)
