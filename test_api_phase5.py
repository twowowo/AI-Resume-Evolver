"""
Phase 5 接口压测脚本 —— 测试 /api/v1/resume/optimize 一键流
"""
import os
import sys
import json

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
print("  Phase 5 接口压测 — /api/v1/resume/optimize")
print("=" * 65)
print(f"\n[INPUT] 简历: {resume_path} ({len(raw_resume)} 字符)")
print(f"[INPUT] JD: {jd_path} ({len(target_jd)} 字符)")

# ── 测试 1: 健康检查 ──
print("\n" + "-" * 65)
print("  Test 1: GET /health")
print("-" * 65)
resp = client.get("/health")
print(f"  Status: {resp.status_code}")
print(f"  Body: {resp.json()}")
assert resp.status_code == 200
assert resp.json()["status"] == "ok"
print("  [PASS]")

# ── 测试 2: 一键优化 ──
print("\n" + "-" * 65)
print("  Test 2: POST /api/v1/resume/optimize (ONE_CLICK)")
print("-" * 65)

payload = {
    "resume_text": raw_resume,
    "jd_text": target_jd,
    "mode": "one_click",
}

print(f"  Sending: resume={len(raw_resume)} chars, jd={len(target_jd)} chars")
resp = client.post("/api/v1/resume/optimize", json=payload, timeout=600)

print(f"\n  Status: {resp.status_code}")
data = resp.json()

# ── 验证响应结构 ──
print(f"\n  >>> 响应验证 <<<")
print(f"  success: {data.get('success')}")
print(f"  difficulty_flag: {data.get('difficulty_flag')}")
print(f"  iteration_count: {data.get('iteration_count')}")
print(f"  message: {data.get('message')}")

# 原始简历雷达
orig = data.get("original_resume_radar", {})
print(f"\n  [原始简历 6-3-1 雷达]")
print(f"    JD匹配: {orig.get('jd_matching_score')}/60")
print(f"    STAR:   {orig.get('star_perf_score')}/30")
print(f"    动词:   {orig.get('action_verbs_score')}/10")
print(f"    总分:   {orig.get('total_score')}/100")

# 优化后雷达
opt = data.get("optimized_resume_radar") or {}
if opt:
    print(f"\n  [优化后简历 6-3-1 雷达]")
    print(f"    JD匹配: {opt.get('jd_matching_score')}/60")
    print(f"    STAR:   {opt.get('star_perf_score')}/30")
    print(f"    动词:   {opt.get('action_verbs_score')}/10")
    print(f"    总分:   {opt.get('total_score')}/100")

# 优化文本
opt_text = data.get("optimized_resume_text", "")
print(f"\n  [优化后简历] {len(opt_text)} 字符")
print(f"  预览: {opt_text[:300]}...")

# 压测题
questions = data.get("stress_test_questions", [])
print(f"\n  [压测面试题] 共 {len(questions)} 道")
for q in questions:
    print(f"    Q{q.get('question_number')} [{q.get('category')}]: {q.get('question', '')[:120]}...")

# 内心独白
monologue = data.get("internal_monologue", "")
if monologue:
    print(f"\n  [内心独白] {monologue[:300]}...")

# ── 校验 ──
print("\n" + "-" * 65)
print("  校验项")
print("-" * 65)

all_pass = True

# 1. success
if data.get("success"):
    print("  [PASS] success = true")
else:
    print("  [FAIL] success = false")
    all_pass = False

# 2. original radar has valid scores
if orig.get("total_score", 0) > 0:
    print(f"  [PASS] 原始简历雷达总分 {orig.get('total_score')} > 0")
else:
    print(f"  [FAIL] 原始简历雷达总分为 0")
    all_pass = False

# 3. original radar total >= 30 (hard tool baseline)
if orig.get("total_score", 0) >= 30:
    print(f"  [PASS] 初筛分 {orig.get('total_score')} >= 30 熔断线")
else:
    print(f"  [WARN] 初筛分 {orig.get('total_score')} < 30")

# 4. optimized radar present
if opt:
    print(f"  [PASS] 优化后雷达存在，总分 {opt.get('total_score')}/100")
else:
    print(f"  [WARN] 优化后雷达为空")

# 5. optimized text not empty
if len(opt_text) > 100:
    print(f"  [PASS] 优化后简历 {len(opt_text)} 字符 (> 100)")
else:
    print(f"  [FAIL] 优化后简历过短: {len(opt_text)} 字符")
    all_pass = False

# 6. stress test questions
if len(questions) >= 1:
    print(f"  [PASS] 压测题 {len(questions)} 道 (>= 1)")
else:
    print(f"  [WARN] 压测题为空")

# 7. response status
if resp.status_code == 200:
    print(f"  [PASS] HTTP 200")
else:
    print(f"  [FAIL] HTTP {resp.status_code}")
    all_pass = False

if all_pass:
    print(f"\n  [SUCCESS] 全部校验通过！一键流接口稳定通畅。")
else:
    print(f"\n  [FAIL] 部分校验未通过。")

# ── 测试 3: 交互模式 501 ──
print("\n" + "-" * 65)
print("  Test 3: POST /api/v1/resume/optimize (INTERACTIVE)")
print("-" * 65)
payload["mode"] = "interactive"
resp = client.post("/api/v1/resume/optimize", json=payload)
print(f"  Status: {resp.status_code}")
print(f"  Detail: {resp.json().get('detail', '')}")
if resp.status_code == 501:
    print("  [PASS] 交互模式正确返回 501")
else:
    print(f"  [WARN] 预期 501，实际 {resp.status_code}")

print("\n" + "=" * 65)
print("  接口压测完成")
print("=" * 65)
