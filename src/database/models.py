"""
SQLAlchemy 2.0 现代 ORM 声明式映射模型

表结构:
  1. users          — 登录账密认证 (v5.2 JWT 认证系统)
  2. user_resumes   — 简历四章节微创手术刀持久化 (user_id 唯一，按章节 UPDATE)
  3. user_profiles  — 用户求职意图长期画像记忆 (user_id + profile_key 联合唯一，幂等 Upsert)
"""

import datetime
from typing import Optional

from sqlalchemy import String, Text, DateTime, Integer, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


# ==========================================
# 🏛️ 1. 定义 SQLAlchemy 现代 ORM 统一基类
# ==========================================

class Base(DeclarativeBase):
    pass


# ==========================================
# 👤 2. 用户登录账密表模型（v5.2 JWT 认证系统）
# ==========================================

class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True, comment="自增主键"
    )
    username: Mapped[str] = mapped_column(
        String(64), unique=True, nullable=False, index=True, comment="登录用户名，全局唯一"
    )
    hashed_password: Mapped[str] = mapped_column(
        String(256), nullable=False, comment="bcrypt 哈希密文"
    )
    is_active: Mapped[bool] = mapped_column(
        default=True, comment="账号是否激活，管理员可停用"
    )
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime,
        default=datetime.datetime.utcnow,
        comment="账号创建时间",
    )


# ==========================================
# 📝 3. 用户简历结构化持久化表模型
# ==========================================

class UserResume(Base):
    __tablename__ = "user_resumes"

    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True, comment="自增主键"
    )
    user_id: Mapped[str] = mapped_column(
        String(64), unique=True, nullable=False, index=True, comment="用户全局唯一ID，索引关联"
    )

    # 局部微创手术刀精准对接的 4 大核心简历章节（Text 类型，容纳富文本 Markdown）
    basic: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True, comment="个人基础信息章节"
    )
    skills: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True, comment="核心技术栈章节"
    )
    projects: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True, comment="核心项目经历章节"
    )
    campus: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True, comment="校园经历与领导力章节"
    )

    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime,
        default=datetime.datetime.utcnow,
        onupdate=datetime.datetime.utcnow,
        comment="最后一次被大模型精修润色的物理时间",
    )


# ==========================================
# 🧊 4. 用户求职意图与长期记忆画像表模型 (Upsert 专属)
# ==========================================

class UserProfile(Base):
    __tablename__ = "user_profiles"

    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True, comment="自增主键"
    )
    user_id: Mapped[str] = mapped_column(
        String(64), nullable=False, index=True, comment="用户全局唯一ID"
    )

    # 长期记忆特征键值对映射，如 target_company -> 字节跳动
    profile_key: Mapped[str] = mapped_column(
        String(128), nullable=False, comment="画像特征键，如 preferred_tech_stack"
    )
    profile_value: Mapped[str] = mapped_column(
        Text, nullable=False, comment="画像特征值内容"
    )

    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime,
        default=datetime.datetime.utcnow,
        comment="特征被大模型捕获冷冻的时间",
    )

    # 大厂工程防御规范：建立联合唯一索引，确保同一个用户的同一个特征键
    # 在数据库中只有一条最新记录，方便 Upsert 幂等操作
    __table_args__ = (
        UniqueConstraint(
            "user_id", "profile_key", name="uix_user_id_profile_key"
        ),
    )




