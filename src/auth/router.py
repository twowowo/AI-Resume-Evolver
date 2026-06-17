"""
v5.2 认证路由 —— POST /api/v1/auth/login

JWT 签发流程：用户名密码 → bcrypt 校验 → HS256 Token 返回
"""

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from src.auth.schemas import LoginRequest, TokenResponse
from src.auth.security import verify_password, create_access_token
from src.database.connection import get_session
from src.database.models import User

router = APIRouter(prefix="/api/v1/auth", tags=["认证"])


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest):
    """用户登录 —— 验证用户名密码，返回 JWT Bearer Token。

    成功: 200 + {"access_token": "...", "token_type": "bearer", "username": "admin"}
    失败: 401 + {"detail": "用户名或密码错误"}
    """
    with get_session() as session:
        stmt = select(User).where(User.username == payload.username)
        user = session.scalars(stmt).first()

    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户名或密码错误",
        )

    if not verify_password(payload.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户名或密码错误",
        )

    token = create_access_token(data={"sub": user.username, "uid": user.id})
    return TokenResponse(access_token=token, username=user.username)
