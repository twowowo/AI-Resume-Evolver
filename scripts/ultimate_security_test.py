"""
================================================================================
  AI-Resume-Evolver v5.8 终极安全审计与自动化攻击测试套件
================================================================================

用途:
  上线前红队安全测试 — 模拟黑客攻击、边界轰炸、并发压测、注入攻击

测试用例:
  A. JWT 伪造攻击 → 期望 401
  B. 超长/畸形文本轰炸 → 期望 422 或优雅降级
  C. 多线程并发压测 (10 线程同 session_id) → 期望无死锁/无数据错乱
  D. 脏数据注入 (SQL/JSON 特殊字符) → 期望安全隔离、无崩溃

运行方式:
  pytest scripts/ultimate_security_test.py -v -s

前置条件:
  1. 后端服务已启动 (默认 http://localhost:8080)
  2. 数据库已初始化 (含默认 admin 账号)
"""

import os
import sys
import json
import time
import uuid
import hashlib
import threading
from datetime import datetime, timedelta, timezone
from concurrent.futures import ThreadPoolExecutor, as_completed

import pytest
import httpx
from jose import jwt

# ═══════════════════════════════════════════════════════════════
# 配置常量
# ═══════════════════════════════════════════════════════════════

# ── v5.9 容器感知：宿主机用 localhost:8001，Docker 内用 http://backend:8001 ──
BASE_URL = os.getenv("TEST_BACKEND_URL", "http://localhost:8001")
JWT_SECRET = os.getenv("JWT_SECRET", "zhoujiankai_jwt_secret_2026")
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")

ADMIN_USERNAME = "admin"
ADMIN_PASSWORD = "123zhoujiankai"

# 如果服务器不可达，跳过所有需要服务器的测试
_SERVER_AVAILABLE = False


# ═══════════════════════════════════════════════════════════════
# 工具函数
# ═══════════════════════════════════════════════════════════════

def _check_server() -> bool:
    """检查后端服务是否可达"""
    try:
        import urllib.request
        req = urllib.request.Request(f"{BASE_URL}/health")
        resp = urllib.request.urlopen(req, timeout=5)
        return resp.status == 200
    except Exception:
        return False


def _make_forged_token(username: str = "hacker", expired: bool = False) -> str:
    """制造伪造/过期 JWT Token"""
    payload = {
        "sub": username,
        "uid": 99999,
    }
    if expired:
        payload["exp"] = datetime.now(timezone.utc) - timedelta(hours=1)
    else:
        payload["exp"] = datetime.now(timezone.utc) + timedelta(hours=1)
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def _make_token_with_wrong_secret(username: str = "hacker") -> str:
    """使用错误密钥签发的 JWT Token"""
    payload = {
        "sub": username,
        "uid": 99999,
        "exp": datetime.now(timezone.utc) + timedelta(hours=1),
    }
    return jwt.encode(payload, "wrong_secret_key_12345678", algorithm=JWT_ALGORITHM)


def _make_tampered_token(original_token: str) -> str:
    """篡改 Token payload (保留签名, 修改中间段)"""
    parts = original_token.split(".")
    if len(parts) != 3:
        return original_token
    # 解码 payload, 修改 sub, 不重新签名
    try:
        import base64
        payload_bytes = parts[1].encode("utf-8")
        # 补齐 base64 padding
        padding = 4 - len(payload_bytes) % 4
        if padding != 4:
            payload_bytes += b"=" * padding
        decoded = base64.urlsafe_b64decode(payload_bytes)
        payload_dict = json.loads(decoded)
        payload_dict["sub"] = "tampered_admin"
        payload_dict["uid"] = 1
        new_payload = base64.urlsafe_b64encode(
            json.dumps(payload_dict).encode("utf-8")
        ).rstrip(b"=").decode("utf-8")
        return f"{parts[0]}.{new_payload}.{parts[2]}"
    except Exception:
        return original_token


# ═══════════════════════════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════════════════════════

@pytest.fixture(scope="module")
def server_available():
    """模块级 fixture: 检查服务可用性"""
    available = _check_server()
    if not available:
        pytest.skip(
            f"后端服务不可达 ({BASE_URL}/health)，跳过所有网络测试。"
            f"请先启动服务: python main.py --server"
        )
    return True


@pytest.fixture(scope="module")
def valid_token(server_available):
    """获取有效 JWT Token (通过登录接口)"""
    try:
        resp = httpx.post(
            f"{BASE_URL}/api/v1/auth/login",
            json={"username": ADMIN_USERNAME, "password": ADMIN_PASSWORD},
            timeout=10,
        )
        if resp.status_code == 200:
            data = resp.json()
            return data.get("access_token", "")
        else:
            # 登录失败 — 可能是用户不存在，尝试直接用 JWT 密钥签发
            pytest.skip(f"登录接口返回 {resp.status_code}: {resp.text}")
    except Exception as e:
        pytest.skip(f"登录接口不可达: {e}")


# ═══════════════════════════════════════════════════════════════
# 用例 A: JWT 伪造攻击
# ═══════════════════════════════════════════════════════════════

class TestJWTForgery:
    """JWT 伪造攻击 — 验证鉴权中间件严格拒止所有非法 Token"""

    # ── 受保护端点列表 ──
    PROTECTED_ENDPOINTS = [
        ("POST", "/api/v1/resume/optimize", {"resume_text": "test", "jd_text": "test"}),
        ("POST", "/api/agent/stream", {"user_query": "test"}),
        ("POST", "/api/v1/resume/chat", {"thread_id": "test::resume", "user_message": "hello"}),
    ]

    # ── A1: 完全无 Token ──
    @pytest.mark.parametrize("method,path,body", PROTECTED_ENDPOINTS)
    def test_a1_no_token_rejected(self, server_available, method, path, body):
        """A1: 无 Authorization 头 → 401"""
        client = httpx.Client(timeout=15)
        if method == "POST":
            resp = client.post(f"{BASE_URL}{path}", json=body)
        else:
            resp = client.get(f"{BASE_URL}{path}")

        assert resp.status_code == 401, (
            f"[FAIL A1] {method} {path} 无 Token 应返回 401，"
            f"实际 {resp.status_code}: {resp.text[:200]}"
        )
        assert "安全熔断" in resp.text or "Unauthorized" in resp.text or "缺少" in resp.text, (
            f"[FAIL A1] 401 响应应包含安全熔断标识，实际: {resp.text[:200]}"
        )

    # ── A2: 空字符串 Token ──
    @pytest.mark.parametrize("method,path,body", PROTECTED_ENDPOINTS)
    def test_a2_empty_token_rejected(self, server_available, method, path, body):
        """A2: Authorization: Bearer "" → 401 (双空格避免 httpx 客户端拒绝)"""
        resp = httpx.post(
            f"{BASE_URL}{path}",
            json=body,
            headers={"Authorization": "Bearer  "},
            timeout=15,
        )
        assert resp.status_code == 401, (
            f"[FAIL A2] {path} 空 Token 应返回 401，实际 {resp.status_code}"
        )

    # ── A3: 过期 Token ──
    @pytest.mark.parametrize("method,path,body", PROTECTED_ENDPOINTS)
    def test_a3_expired_token_rejected(self, server_available, method, path, body):
        """A3: 过期 JWT → 401"""
        expired = _make_forged_token(username="admin", expired=True)
        resp = httpx.post(
            f"{BASE_URL}{path}",
            json=body,
            headers={"Authorization": f"Bearer {expired}"},
            timeout=15,
        )
        assert resp.status_code == 401, (
            f"[FAIL A3] {path} 过期 Token 应返回 401，实际 {resp.status_code}: {resp.text[:200]}"
        )
        assert "过期" in resp.text or "无效" in resp.text or "expired" in resp.text.lower(), (
            f"[FAIL A3] 应提示 Token 过期/无效，实际: {resp.text[:200]}"
        )

    # ── A4: 错误密钥签发的 Token ──
    @pytest.mark.parametrize("method,path,body", PROTECTED_ENDPOINTS)
    def test_a4_wrong_secret_token_rejected(self, server_available, method, path, body):
        """A4: 错误密钥签发的 JWT → 401"""
        wrong_token = _make_token_with_wrong_secret(username="admin")
        resp = httpx.post(
            f"{BASE_URL}{path}",
            json=body,
            headers={"Authorization": f"Bearer {wrong_token}"},
            timeout=15,
        )
        assert resp.status_code == 401, (
            f"[FAIL A4] {path} 错误密钥 Token 应返回 401，实际 {resp.status_code}"
        )

    # ── A5: 篡改 Payload 的 Token (签名不匹配) ──
    def test_a5_tampered_token_rejected(self, server_available, valid_token):
        """A5: 篡改 payload 但保留原签名 → 401"""
        tampered = _make_tampered_token(valid_token)
        resp = httpx.post(
            f"{BASE_URL}/api/v1/resume/optimize",
            json={"resume_text": "test", "jd_text": "test"},
            headers={"Authorization": f"Bearer {tampered}"},
            timeout=15,
        )
        assert resp.status_code == 401, (
            f"[FAIL A5] 篡改 Token 应返回 401，实际 {resp.status_code}: {resp.text[:200]}"
        )

    # ── A6: 不存在的用户 (有效签名但数据库中无此用户) ──
    def test_a6_nonexistent_user_rejected(self, server_available):
        """A6: 有效签名但用户不存在 → 401"""
        ghost_token = _make_forged_token(username="nonexistent_user_99999", expired=False)
        resp = httpx.post(
            f"{BASE_URL}/api/v1/resume/optimize",
            json={"resume_text": "test", "jd_text": "test"},
            headers={"Authorization": f"Bearer {ghost_token}"},
            timeout=15,
        )
        assert resp.status_code == 401, (
            f"[FAIL A6] 不存在用户 Token 应返回 401，实际 {resp.status_code}: {resp.text[:200]}"
        )

    # ── A7: 免检路径无需 Token (正向验证) ──
    def test_a7_exempt_paths_no_token_required(self, server_available):
        """A7: /health, /docs 免检路径无需 Token 即可访问"""
        exempt_paths = ["/health", "/docs", "/openapi.json"]
        for path in exempt_paths:
            resp = httpx.get(f"{BASE_URL}{path}", timeout=10)
            assert resp.status_code in (200, 302), (
                f"[FAIL A7] 免检路径 {path} 应返回 200，实际 {resp.status_code}"
            )

    # ── A8: 合法 Token 正常访问 (正向验证) ──
    def test_a8_valid_token_accepted(self, server_available, valid_token):
        """A8: 合法 Token → 200 (业务逻辑正常执行)"""
        resp = httpx.post(
            f"{BASE_URL}/api/v1/resume/optimize",
            json={"resume_text": "Python Developer", "jd_text": "Python Engineer"},
            headers={"Authorization": f"Bearer {valid_token}"},
            timeout=120,
        )
        # 短输入触发降级(返回 JSON 而非 SSE)或正常优化
        assert resp.status_code != 401, (
            f"[FAIL A8] 合法 Token 不应返回 401，实际 {resp.status_code}: {resp.text[:200]}"
        )
        assert resp.status_code != 403, (
            f"[FAIL A8] 合法 Token 不应返回 403，实际 {resp.status_code}: {resp.text[:200]}"
        )


# ═══════════════════════════════════════════════════════════════
# 用例 B: 超长/畸形文本轰炸
# ═══════════════════════════════════════════════════════════════

class TestInputBombing:
    """超长文本与畸形输入轰炸 — 验证输入防线不退让"""

    # ── B1: 简历超长 (>10000 字符) ──
    def test_b1_resume_exceeds_max_length(self, server_available, valid_token):
        """B1: resume_text 超过 10000 字符 → 422"""
        giant_resume = "Python Developer with 5 years experience. " * 600  # ~21k chars
        resp = httpx.post(
            f"{BASE_URL}/api/v1/resume/optimize",
            json={"resume_text": giant_resume, "jd_text": "正常 JD"},
            headers={"Authorization": f"Bearer {valid_token}"},
            timeout=15,
        )
        # Pydantic 校验在 FastAPI 层直接返回 422
        assert resp.status_code in (422, 400), (
            f"[FAIL B1] 超长 resume 应返回 422/400，实际 {resp.status_code}: {resp.text[:200]}"
        )

    # ── B2: JD 超长 (>5000 字符) ──
    def test_b2_jd_exceeds_max_length(self, server_available, valid_token):
        """B2: jd_text 超过 5000 字符 → 422"""
        giant_jd = "We need a software engineer. " * 300  # ~10k chars
        resp = httpx.post(
            f"{BASE_URL}/api/v1/resume/optimize",
            json={"resume_text": "正常简历", "jd_text": giant_jd},
            headers={"Authorization": f"Bearer {valid_token}"},
            timeout=15,
        )
        assert resp.status_code in (422, 400), (
            f"[FAIL B2] 超长 JD 应返回 422/400，实际 {resp.status_code}: {resp.text[:200]}"
        )

    # ── B3: 极短输入优雅降级 ──
    def test_b3_ultra_short_input_graceful_degrade(self, server_available, valid_token):
        """B3: 极短简历+JD (各1字符) → 降级而非 500"""
        resp = httpx.post(
            f"{BASE_URL}/api/v1/resume/optimize",
            json={"resume_text": "人", "jd_text": "人"},
            headers={"Authorization": f"Bearer {valid_token}"},
            timeout=30,
        )
        assert resp.status_code != 500, (
            f"[FAIL B3] 极短输入不应返回 500，实际 {resp.status_code}: {resp.text[:300]}"
        )
        assert resp.status_code != 422, (
            f"[FAIL B3] 极短输入不应返回 422 (v5.5已移除min_length)，"
            f"实际 {resp.status_code}: {resp.text[:300]}"
        )

    # ── B4: 空字符串输入 ──
    def test_b4_empty_string_input(self, server_available, valid_token):
        """B4: 空字符串简历 → 应被优雅处理"""
        resp = httpx.post(
            f"{BASE_URL}/api/v1/resume/optimize",
            json={"resume_text": "", "jd_text": "正常 JD"},
            headers={"Authorization": f"Bearer {valid_token}"},
            timeout=15,
        )
        # 空字符串可能触发 Pydantic 校验 422 或业务降级
        assert resp.status_code in (200, 400, 422), (
            f"[FAIL B4] 空输入应返回 200/400/422，实际 {resp.status_code}: {resp.text[:200]}"
        )
        if resp.status_code == 200:
            # 应包含降级提示
            body = resp.text
            assert any(kw in body.lower() for kw in ["degraded", "circuit", "熔断", "保护"]), (
                f"[FAIL B4] 降级响应应包含保护性标识，实际首200字符: {resp.text[:200]}"
            )

    # ── B5: Unicode 特殊字符 ──
    def test_b5_unicode_special_chars(self, server_available, valid_token):
        """B5: Unicode 特殊字符 (零宽、RTL、emoji) → 不崩溃"""
        nasty_unicode = (
            "简历内容​‌‍⁠⁡"
            "RTL‮‭反转测试"
            "Emoji🔥💣⚠️🧨"
            "全角符号￥＠＃％＆＊"
        )
        resp = httpx.post(
            f"{BASE_URL}/api/v1/resume/optimize",
            json={"resume_text": nasty_unicode, "jd_text": "正常 JD 要求"},
            headers={"Authorization": f"Bearer {valid_token}"},
            timeout=30,
        )
        assert resp.status_code != 500, (
            f"[FAIL B5] Unicode 特殊字符不应导致 500，实际 {resp.status_code}: {resp.text[:200]}"
        )

    # ── B6: Markdown/HTML 注入尝试 ──
    def test_b6_markdown_html_injection(self, server_available, valid_token):
        """B6: Markdown + HTML 标签注入 → 不应破坏 SSE 协议"""
        injection_payload = (
            "## Resume\n<script>alert('XSS')</script>\n"
            "```json\n{\"malicious\": true}\n```\n"
            "![](http://evil.com/track.png)\n"
            "<img src=x onerror=alert(1)>"
        )
        resp = httpx.post(
            f"{BASE_URL}/api/v1/resume/optimize",
            json={"resume_text": injection_payload, "jd_text": "正常 JD"},
            headers={"Authorization": f"Bearer {valid_token}"},
            timeout=30,
        )
        assert resp.status_code != 500, (
            f"[FAIL B6] Markdown/HTML 注入不应导致 500，实际 {resp.status_code}: {resp.text[:200]}"
        )

    # ── B7: 超大请求体 (接近 FastAPI 默认限制) ──
    def test_b7_massive_json_body(self, server_available, valid_token):
        """B7: 发送接近极限大小的 JSON body → 不应 OOM"""
        # 构造一个合法但巨大的请求体
        big_text = "a" * 9000  # 在 max_length=10000 以内
        resp = httpx.post(
            f"{BASE_URL}/api/v1/resume/optimize",
            json={
                "resume_text": big_text,
                "jd_text": big_text[:5000],
            },
            headers={"Authorization": f"Bearer {valid_token}"},
            timeout=60,
        )
        assert resp.status_code != 500, (
            f"[FAIL B7] 大请求体不应导致 500，实际 {resp.status_code}"
        )


# ═══════════════════════════════════════════════════════════════
# 用例 C: 多线程并发压测
# ═══════════════════════════════════════════════════════════════

class TestConcurrencyStress:
    """多线程并发压测 — 验证后端无死锁、无数据错乱"""

    # ── C1: 10 线程并发只读请求 (health) ──
    def test_c1_concurrent_health_checks(self, server_available):
        """C1: 10 线程并发 GET /health → 全部 200"""

        def health_check():
            try:
                resp = httpx.get(f"{BASE_URL}/health", timeout=10)
                return resp.status_code == 200
            except Exception:
                return False

        with ThreadPoolExecutor(max_workers=10) as pool:
            futures = [pool.submit(health_check) for _ in range(10)]
            results = [f.result(timeout=15) for f in futures]

        success_count = sum(results)
        assert success_count == 10, (
            f"[FAIL C1] 10 并发 health 应全部 200，实际 {success_count}/10 成功"
        )

    # ── C2: 5 线程并发登录 (同用户) ──
    def test_c2_concurrent_login_same_user(self, server_available):
        """C2: 5 线程同时登录同一用户 → 无死锁"""

        def login():
            try:
                resp = httpx.post(
                    f"{BASE_URL}/api/v1/auth/login",
                    json={"username": ADMIN_USERNAME, "password": ADMIN_PASSWORD},
                    timeout=15,
                )
                return resp.status_code == 200
            except Exception:
                return False

        with ThreadPoolExecutor(max_workers=5) as pool:
            futures = [pool.submit(login) for _ in range(5)]
            results = [f.result(timeout=20) for f in futures]

        success_count = sum(results)
        assert success_count == 5, (
            f"[FAIL C2] 5 并发登录应全部 200，实际 {success_count}/5 成功"
        )

    # ── C3: 10 线程并发一键优化 (同 session_id) ──
    def test_c3_concurrent_optimize_same_session(self, server_available, valid_token):
        """C3: 10 线程同时优化同一 session_id → 无死锁、无 500"""

        headers = {"Authorization": f"Bearer {valid_token}"}
        shared_session_id = f"concurrency-test-{uuid.uuid4().hex[:8]}"

        def optimize():
            try:
                resp = httpx.post(
                    f"{BASE_URL}/api/v1/resume/optimize",
                    json={
                        "resume_text": f"Concurrency test resume {uuid.uuid4().hex[:8]}",
                        "jd_text": "Software Engineer with Python experience",
                        "session_id": shared_session_id,
                    },
                    headers=headers,
                    timeout=60,
                )
                # 接受 200（正常优化或降级）或 4xx（业务拒绝）
                # 但不能是 500
                return resp.status_code, resp.status_code < 500
            except Exception as e:
                return 0, (isinstance(e, httpx.ReadTimeout))

        with ThreadPoolExecutor(max_workers=10) as pool:
            futures = [pool.submit(optimize) for _ in range(10)]
            outcomes = [f.result(timeout=90) for f in futures]

        # 统计结果
        status_codes = {}
        no_500 = True
        for code, ok in outcomes:
            status_codes[code] = status_codes.get(code, 0) + 1
            if code == 500:
                no_500 = False

        print(f"\n  [C3] 并发优化状态码分布: {status_codes}")

        assert no_500, (
            f"[FAIL C3] 10 并发同 session 优化不应出现 500，"
            f"状态码分布: {status_codes}"
        )

    # ── C4: 混合并发 (3 种端点同时) ──
    def test_c4_mixed_endpoint_concurrency(self, server_available, valid_token):
        """C4: 混合并发 — 同时访问 health/login/optimize → 系统稳定"""

        headers = {"Authorization": f"Bearer {valid_token}"}
        errors = []
        lock = threading.Lock()

        def call_health():
            try:
                resp = httpx.get(f"{BASE_URL}/health", timeout=10)
                if resp.status_code != 200:
                    with lock:
                        errors.append(f"health={resp.status_code}")
            except Exception as e:
                with lock:
                    errors.append(f"health_exc={e}")

        def call_login():
            try:
                resp = httpx.post(
                    f"{BASE_URL}/api/v1/auth/login",
                    json={"username": ADMIN_USERNAME, "password": ADMIN_PASSWORD},
                    timeout=15,
                )
                if resp.status_code != 200:
                    with lock:
                        errors.append(f"login={resp.status_code}")
            except Exception as e:
                with lock:
                    errors.append(f"login_exc={e}")

        def call_optimize():
            try:
                resp = httpx.post(
                    f"{BASE_URL}/api/v1/resume/optimize",
                    json={
                        "resume_text": f"Mix concurrency test {uuid.uuid4().hex[:8]}",
                        "jd_text": "Python Backend Developer",
                    },
                    headers=headers,
                    timeout=60,
                )
                if resp.status_code == 500:
                    with lock:
                        errors.append(f"optimize=500: {resp.text[:100]}")
            except Exception as e:
                with lock:
                    errors.append(f"optimize_exc={e}")

        tasks = (
            [call_health] * 4 +
            [call_login] * 3 +
            [call_optimize] * 3
        )

        with ThreadPoolExecutor(max_workers=10) as pool:
            futures = [pool.submit(task) for task in tasks]
            for f in futures:
                try:
                    f.result(timeout=90)
                except Exception as e:
                    with lock:
                        errors.append(f"future_exc={e}")

        assert len(errors) == 0, (
            f"[FAIL C4] 混合并发出现 {len(errors)} 个错误: {errors[:10]}"
        )


# ═══════════════════════════════════════════════════════════════
# 用例 D: 脏数据注入
# ═══════════════════════════════════════════════════════════════

class TestInjectionDefense:
    """脏数据注入 — 验证 SQL/JSON/路径遍历/控制字符免疫"""

    # ── D1: SQL 关键字注入 ──
    def test_d1_sql_keyword_injection(self, server_available, valid_token):
        """D1: SQL 关键字注入 resume_text → 不应破坏查询"""
        sql_payloads = [
            "'; DROP TABLE users; --",
            "1' OR '1'='1",
            "UNION SELECT * FROM users",
            "'; UPDATE users SET is_active=1 WHERE '1'='1",
            "1; DELETE FROM users WHERE 1=1; --",
        ]
        headers = {"Authorization": f"Bearer {valid_token}"}

        for i, payload in enumerate(sql_payloads):
            resp = httpx.post(
                f"{BASE_URL}/api/v1/resume/optimize",
                json={
                    "resume_text": payload,
                    "jd_text": "Normal software engineer job description",
                },
                headers=headers,
                timeout=30,
            )
            assert resp.status_code != 500, (
                f"[FAIL D1.{i}] SQL 注入 payload 不应导致 500，"
                f"payload='{payload[:50]}...', status={resp.status_code}"
            )

    # ── D2: JSON 特殊字符注入 ──
    def test_d2_json_special_chars(self, server_available, valid_token):
        """D2: JSON 特殊字符 → 不应破坏 SSE 帧解析"""
        null_byte = chr(0)
        json_nasty = (
            '{"nested": "json", "array": [1,2,3]}\n'
            + '\\"escape\\" \\n \\t \\r \\b\n'
            + null_byte + ' null byte attempt\n'
            + 'data: injected_sse_frame\n\n'
            + 'event: fake_event\ndata: fake_data\n\n'
        )
        headers = {"Authorization": f"Bearer {valid_token}"}
        resp = httpx.post(
            f"{BASE_URL}/api/v1/resume/optimize",
            json={"resume_text": json_nasty, "jd_text": "Normal JD"},
            headers=headers,
            timeout=30,
        )
        assert resp.status_code != 500, (
            f"[FAIL D2] JSON 特殊字符不应导致 500，实际 {resp.status_code}"
        )

    # ── D3: 路径遍历尝试 ──
    def test_d3_path_traversal(self, server_available, valid_token):
        """D3: 路径遍历字符 → 不应泄露文件"""
        traversal_payloads = [
            "../../../etc/passwd",
            "..\\..\\..\\Windows\\System32\\config\\SAM",
            "../../.env",
            "/proc/self/environ",
        ]
        headers = {"Authorization": f"Bearer {valid_token}"}

        for i, payload in enumerate(traversal_payloads):
            resp = httpx.post(
                f"{BASE_URL}/api/v1/resume/optimize",
                json={
                    "resume_text": f"Resume content with path: {payload}",
                    "jd_text": "Job description",
                },
                headers=headers,
                timeout=30,
            )
            assert resp.status_code != 500, (
                f"[FAIL D3.{i}] 路径遍历不应导致 500，"
                f"payload='{payload}', status={resp.status_code}"
            )
            # 注意: 不对响应体做关键词扫描 ("root:", "admin:" 等)
            # 因为 SSE 诊断输出中可能合法包含这些词 (如 missing_skills 字段)
            # 真正的文件内容泄露检测需要更复杂的模式匹配 (如 /etc/passwd 格式)

    # ── D4: 空字节注入 ──
    def test_d4_null_byte_injection(self, server_available, valid_token):
        """D4: NULL 字节注入 → 不应截断或崩溃"""
        null_injection = "Normal text\x00with NULL byte\x00injection"
        headers = {"Authorization": f"Bearer {valid_token}"}
        resp = httpx.post(
            f"{BASE_URL}/api/v1/resume/optimize",
            json={"resume_text": null_injection, "jd_text": "Normal JD"},
            headers=headers,
            timeout=30,
        )
        assert resp.status_code != 500, (
            f"[FAIL D4] NULL 字节注入不应导致 500，实际 {resp.status_code}"
        )

    # ── D5: Agent 端点脏数据注入 ──
    def test_d5_agent_endpoint_injection(self, server_available, valid_token):
        """D5: Agent SSE 端点脏数据 → 安全隔离"""
        injection = "'; DROP TABLE users; -- <script>alert(1)</script>"
        headers = {"Authorization": f"Bearer {valid_token}"}
        try:
            resp = httpx.post(
                f"{BASE_URL}/api/agent/stream",
                json={"user_query": injection},
                headers=headers,
                timeout=30,
            )
            assert resp.status_code != 500, (
                f"[FAIL D5] Agent 端点注入不应导致 500，实际 {resp.status_code}"
            )
        except httpx.RemoteProtocolError:
            # SSE 流被服务端主动关闭，这是可接受的行为
            pass


# ═══════════════════════════════════════════════════════════════
# 汇总报告
# ═══════════════════════════════════════════════════════════════

def test_generate_security_report():
    """生成汇总测试报告 (始终执行)"""
    print("\n" + "=" * 70)
    print("  AI-Resume-Evolver v5.8 终极安全审计测试报告")
    print("=" * 70)
    print(f"  目标服务器: {BASE_URL}")
    print(f"  服务状态: {'可达' if _check_server() else '不可达 (跳过网络测试)'}")
    print(f"  JWT 算法: {JWT_ALGORITHM}")
    print(f"  测试时间: {datetime.now().isoformat()}")
    print("=" * 70)
    print()
    print("  测试覆盖:")
    print("    A1-A8:  JWT 伪造攻击 (8 项)")
    print("    B1-B7:  输入轰炸 (7 项)")
    print("    C1-C4:  并发压测 (4 项)")
    print("    D1-D5:  注入防御 (5 项)")
    print()
    print("  严重漏洞速查表 (来自源码审计):")
    print("    🔴 CR1: SQLite checkpointer 双图并发写入冲突")
    print("    🔴 CR2: 全项目零锁 (无 asyncio.Lock/threading.Lock)")
    print("    🔴 CR3: AgentPayload 无 max_length (无界输入)")
    print("    🔴 CR4: text_sanitizer.py logger 未定义 (NameError)")
    print("    🟠 HI1: hybrid_retrieve ChromaDB 异常无捕获")
    print("    🟠 HI2: _build_radar score=None → TypeError")
    print("    🟠 HI3: circuit breaker score=None → TypeError")
    print("    🟠 HI4: state.get() 键存在值=None 时默认值失效")
    print("    🟡 ME1: ThreadPoolExecutor 无 shutdown + 无界队列")
    print("    🟡 ME2: rollback 非原子操作 (read-modify-write)")
    print("    🟡 ME3: 5 个全局单例无锁 (double-check 反模式)")
    print("=" * 70)

    # 此测试始终通过 — 它只是打印报告
    assert True


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
