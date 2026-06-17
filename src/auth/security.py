"""
v5.2 密码哈希与 JWT Token 工具

- verify_password / hash_password: bcrypt 密码哈希
- create_access_token: 签发 JWT
- decode_access_token: 校验并解码 JWT
- get_current_user: FastAPI 依赖项，从 Authorization Bearer 头提取并校验当前用户
"""

import os
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, Request, status, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy import select

import bcrypt

from jose import JWTError, jwt

from src.auth.schemas import UserInfo

# ── JWT 配置 ──
JWT_SECRET = os.getenv("JWT_SECRET", "zhoujiankai_jwt_secret_2026")
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
JWT_EXPIRE_MINUTES = int(os.getenv("JWT_EXPIRE_MINUTES", "1440"))


def hash_password(password: str) -> str:
    """将明文密码哈希加密，返回 bcrypt 哈希字符串。"""
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """验证明文密码与 bcrypt 哈希是否匹配。"""
    return bcrypt.checkpw(plain_password.encode("utf-8"), hashed_password.encode("utf-8"))


def create_access_token(data: dict) -> str:
    """签发 JWT access token，payload 中注入 exp 过期时间。

    data 至少应包含 {"sub": username}。
    """
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(minutes=JWT_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, JWT_SECRET, algorithm=JWT_ALGORITHM)


def decode_access_token(token: str) -> dict | None:
    """解码 JWT token，校验签名和过期。成功返回 payload 字典，失败返回 None。"""
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        return payload if payload.get("sub") else None
    except JWTError:
        return None


# ── FastAPI Bearer Token 安全方案 ──
_bearer_scheme = HTTPBearer(auto_error=False)

# 免检路径（无需 Token 即可访问）
_EXEMPT_PATHS = {
    "/health",
    "/docs",
    "/redoc",
    "/openapi.json",
    "/api/v1/auth/login",
}


def _is_exempt(path: str) -> bool:
    """检查路径是否免 Token 校验。"""
    if path in _EXEMPT_PATHS:
        return True
    if path.startswith("/docs") or path.startswith("/redoc"):
        return True
    return False


async def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials = Depends(_bearer_scheme),
):
    """全局 JWT Bearer Token 校验依赖项。

    免检路径:
      - /health, /docs, /redoc, /openapi.json, /api/v1/auth/login

    校验流程:
      1. 免检路径直接放行（request.state.user = None）
      2. 提取 Authorization: Bearer <token>
      3. 解码 JWT，验证签名与过期
      4. 查询数据库确认用户存在且 is_active
      5. 注入 request.state.user = UserInfo
    """
    if _is_exempt(request.url.path):
        request.state.user = None
        return

    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="[安全熔断] 缺少 Authorization Bearer Token，请先登录。",
            headers={"WWW-Authenticate": "Bearer"},
        )

    payload = decode_access_token(credentials.credentials)
    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="[安全熔断] Token 无效或已过期，请重新登录。",
            headers={"WWW-Authenticate": "Bearer"},
        )

    username = payload.get("sub", "")
    user_id = payload.get("uid", 0)

    # 数据库校验用户存活状态（延迟导入避免循环依赖）
    from src.database.connection import get_session
    from src.database.models import User

    with get_session() as session:
        stmt = select(User).where(User.id == user_id, User.username == username)
        db_user = session.scalars(stmt).first()

    if db_user is None or not db_user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="[安全熔断] 用户不存在或已被停用。",
        )

    request.state.user = UserInfo(
        id=db_user.id,
        username=db_user.username,
        is_active=db_user.is_active,
    )
