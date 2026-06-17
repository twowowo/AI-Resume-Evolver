"""
v5.2 认证种子守卫 —— lifespan 启动时自动建表 + 默认 admin 账号注入

行为:
  1. 调用 Base.metadata.create_all 确保 users 表存在
  2. 若 users 表为空，自动插入 admin / 123zhoujiankai
  3. 若已有用户，静默跳过
"""

import logging
from sqlalchemy import select, func
from sqlalchemy.orm import Session as OrmSession

from src.database.connection import engine, get_session
from src.database.models import Base, User
from src.auth.security import hash_password

logger = logging.getLogger("AuthSeed")

DEFAULT_ADMIN_USERNAME = "admin"
DEFAULT_ADMIN_PASSWORD = "123zhoujiankai"


def ensure_users_table_and_admin() -> int:
    """确保 users 表存在并包含至少一个管理员账号。

    返回 1 若新增了 admin 用户，否则返回 0。
    """
    # Step 1: 物理建表（幂等，CREATE TABLE IF NOT EXISTS）
    Base.metadata.create_all(bind=engine)

    # Step 2: 检查是否有用户
    with get_session() as session:
        count = session.scalar(select(func.count(User.id)))
        if count and count > 0:
            logger.info(f"[AuthSeed] users 表已有 {count} 个账号，跳过种子注入")
            return 0

        # Step 3: 注入默认管理员
        admin = User(
            username=DEFAULT_ADMIN_USERNAME,
            hashed_password=hash_password(DEFAULT_ADMIN_PASSWORD),
            is_active=True,
        )
        session.add(admin)
        session.commit()
        logger.info(
            f"[AuthSeed] 冷启动注入完成：默认管理员 {DEFAULT_ADMIN_USERNAME} "
            f"已就绪，密码为 {DEFAULT_ADMIN_PASSWORD}"
        )
        return 1
