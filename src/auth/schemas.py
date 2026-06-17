"""v5.2 认证相关 Pydantic 模型"""

from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    """登录请求体"""
    username: str = Field(..., min_length=1, max_length=64, description="用户名")
    password: str = Field(..., min_length=1, max_length=128, description="密码")


class TokenResponse(BaseModel):
    """登录成功返回的 JWT Token"""
    access_token: str
    token_type: str = "bearer"
    username: str


class UserInfo(BaseModel):
    """当前登录用户信息（供 get_current_user 挂载到 request.state）"""
    id: int
    username: str
    is_active: bool
