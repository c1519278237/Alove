from collections.abc import Callable

import jwt
from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from .database import get_db
from .errors import AppError, forbidden, not_found
from .models import Family, FamilyMember, User
from .security import decode_access_token

bearer_scheme = HTTPBearer(auto_error=False)


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    if credentials is None:
        raise AppError("UNAUTHORIZED", "请先登录", 401)
    try:
        user_id = decode_access_token(credentials.credentials)
    except jwt.PyJWTError as exc:
        raise AppError("INVALID_TOKEN", "登录状态已失效", 401) from exc
    user = db.get(User, user_id)
    if user is None or user.status != "active" or user.deleted_at is not None:
        raise AppError("INVALID_TOKEN", "登录状态已失效", 401)
    return user


def get_user_from_token(token: str, db: Session) -> User:
    try:
        user_id = decode_access_token(token)
    except jwt.PyJWTError as exc:
        raise AppError("INVALID_TOKEN", "登录状态已失效", 401) from exc
    user = db.get(User, user_id)
    if user is None or user.status != "active" or user.deleted_at is not None:
        raise AppError("INVALID_TOKEN", "登录状态已失效", 401)
    return user


def require_membership(db: Session, family_id: str, user_id: str) -> FamilyMember:
    family = db.get(Family, family_id)
    if family is None or family.status != "active":
        raise not_found("家庭")
    member = db.scalar(
        select(FamilyMember).where(
            FamilyMember.family_id == family_id,
            FamilyMember.user_id == user_id,
            FamilyMember.status == "active",
        )
    )
    if member is None:
        raise not_found("家庭")
    return member


def require_family_role(
    db: Session, family_id: str, user_id: str, allowed_roles: set[str]
) -> FamilyMember:
    member = require_membership(db, family_id, user_id)
    if member.role not in allowed_roles:
        raise forbidden()
    return member


def family_role_dependency(*roles: str) -> Callable:
    def checker(
        family_id: str,
        user: User = Depends(get_current_user),
        db: Session = Depends(get_db),
    ):
        return require_family_role(db, family_id, user.id, set(roles))

    return checker
