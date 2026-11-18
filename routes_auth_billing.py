from typing import Any
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from core.exceptions import AuthenticationError
from core.security import create_access_token, decode_access_token, hash_password, verify_password
from core.token_billing import TokenBillingService
from database.models import TokenTransaction, User
from database.session import get_db

router = APIRouter(prefix="/api", tags=["auth-and-billing"])


class RegisterRequest(BaseModel):
    email: str = Field(..., min_length=5, max_length=255)
    password: str = Field(..., min_length=4, max_length=128)
    full_name: str = Field(default="", max_length=200)


class LoginRequest(BaseModel):
    email: str = Field(..., min_length=5, max_length=255)
    password: str = Field(..., min_length=1, max_length=128)


class ProfileUpdateRequest(BaseModel):
    current_password: str = Field(..., min_length=1)
    new_email: str | None = Field(default=None, min_length=5, max_length=255)
    full_name: str | None = Field(default=None, max_length=200)
    new_password: str | None = Field(default=None, min_length=4, max_length=128)


class AdminAdjustRequest(BaseModel):
    target_user_id: int
    delta_tokens: int = 0
    new_role: str | None = None
    reason: str = ""


def serialize_user(user: User, spent_today: int = 0, daily_cap: int = 5000) -> dict[str, Any]:
    return {
        "id": user.id,
        "email": user.email,
        "full_name": user.full_name,
        "role": user.role,
        "token_balance": user.token_balance,
        "is_active": user.is_active,
        "admin_spent_today": spent_today if user.role == "admin" else 0,
        "admin_daily_safety_limit": daily_cap if user.role == "admin" else None,
        "created_at": user.created_at.isoformat() if user.created_at else None,
    }


async def get_optional_current_user(request: Request, db: AsyncSession = Depends(get_db)) -> User | None:
    auth_header = request.headers.get("Authorization", "").strip()
    if not auth_header.lower().startswith("bearer "):
        return None
    token = auth_header.split(" ", 1).pop().strip()
    if not token:
        return None
    settings = request.app.state.settings
    payload = decode_access_token(token, settings.master_key)
    if not payload or "sub" not in payload:
        raise AuthenticationError("Недействительный или просроченный токен авторизации.")
    user_id = int(payload["sub"])
    user = (await db.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
    if not user or not user.is_active:
        raise AuthenticationError("Пользователь не найден или заблокирован.")
    return user


async def get_required_current_user(user: User | None = Depends(get_optional_current_user)) -> User:
    if user is None:
        raise AuthenticationError("Требуется авторизация в аккаунте.")
    return user

@router.post("/auth/register")
async def register_user(request: Request, payload: RegisterRequest, db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    norm_email = payload.email.strip().lower()
    if "@" not in norm_email:
        raise HTTPException(status_code=400, detail="Укажите корректный e-mail")
    try:
        TokenBillingService.validate_email_domain(norm_email)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    canonical = TokenBillingService.normalize_email_canonical(norm_email)
    existing = (await db.execute(select(User).where(User.email == norm_email))).scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=409, detail="Пользователь с таким e-mail уже зарегистрирован")

    users_count = (await db.execute(select(func.count(User.id)))).scalar_one()
    settings = request.app.state.settings
    admin_env = (settings.admin_email or "").strip().lower()
    assigned_role = "admin" if (users_count == 0 or (admin_env and norm_email == admin_env)) else "user"

    forwarded_for = request.headers.get("X-Forwarded-For", "").split(",", 1).pop(0).strip()
    client_ip = forwarded_for or (request.client.host if request.client else "")
    device_fp = request.headers.get("X-Device-Fingerprint", "").strip()[:128] or None

    user = User(
        email=norm_email,
        canonical_email=canonical,
        password_hash=hash_password(payload.password),
        full_name=payload.full_name.strip() or norm_email.split("@", 1).pop(0),
        role=assigned_role,
        token_balance=0,
        registration_ip=client_ip or None,
        device_fingerprint=device_fp,
    )
    db.add(user)
    await db.flush()
    await TokenBillingService.grant_welcome_bonus(db, user)
    await db.commit()
    await db.refresh(user)

    token = create_access_token({"sub": user.id, "role": user.role}, settings.master_key, settings.jwt_expire_hours)
    tariffs = TokenBillingService.load_tariffs()
    return {
        "access_token": token,
        "token_type": "bearer",
        "bonus_granted": user.bonus_granted,
        "user": serialize_user(user, spent_today=0, daily_cap=int(tariffs.get("admin_daily_safety_limit", 5000))),
    }
@router.post("/auth/login")
async def login_user(request: Request, payload: LoginRequest, db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    norm_email = payload.email.strip().lower()
    user = (await db.execute(select(User).where(User.email == norm_email))).scalar_one_or_none()
    if not user or not verify_password(payload.password, user.password_hash):
        raise AuthenticationError("Неверный e-mail или пароль.")
    if not user.is_active:
        raise AuthenticationError("Учётная запись деактивирована.")

    settings = request.app.state.settings
    admin_env = (settings.admin_email or "").strip().lower()
    if admin_env and norm_email == admin_env and user.role != "admin":
        user.role = "admin"
        await db.commit()
        await db.refresh(user)

    token = create_access_token({"sub": user.id, "role": user.role}, settings.master_key, settings.jwt_expire_hours)
    tariffs = TokenBillingService.load_tariffs()
    spent_today = await TokenBillingService.get_admin_spent_today(db, user.id) if user.role == "admin" else 0
    return {
        "access_token": token,
        "token_type": "bearer",
        "user": serialize_user(user, spent_today=spent_today, daily_cap=int(tariffs.get("admin_daily_safety_limit", 5000))),
    }


@router.get("/auth/me")
async def get_my_profile(user: User = Depends(get_required_current_user), db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    tariffs = TokenBillingService.load_tariffs()
    spent_today = await TokenBillingService.get_admin_spent_today(db, user.id) if user.role == "admin" else 0
    return {
        "user": serialize_user(user, spent_today=spent_today, daily_cap=int(tariffs.get("admin_daily_safety_limit", 5000)))
    }


@router.patch("/auth/profile")
async def update_my_profile(
    payload: ProfileUpdateRequest, user: User = Depends(get_required_current_user), db: AsyncSession = Depends(get_db)
) -> dict[str, Any]:
    if not verify_password(payload.current_password, user.password_hash):
        raise AuthenticationError("Текущий пароль указан неверно.")
    if payload.new_email is not None:
        clean_email = payload.new_email.strip().lower()
        if "@" not in clean_email:
            raise HTTPException(status_code=400, detail="Укажите корректный новый e-mail")
        if clean_email != user.email:
            dup = (await db.execute(select(User).where(User.email == clean_email))).scalar_one_or_none()
            if dup:
                raise HTTPException(status_code=409, detail="Этот e-mail уже занят другим аккаунтом")
            user.email = clean_email
    if payload.full_name is not None:
        user.full_name = payload.full_name.strip()
    if payload.new_password is not None:
        user.password_hash = hash_password(payload.new_password)
    await db.commit()
    await db.refresh(user)
    tariffs = TokenBillingService.load_tariffs()
    spent_today = await TokenBillingService.get_admin_spent_today(db, user.id) if user.role == "admin" else 0
    return {"user": serialize_user(user, spent_today=spent_today, daily_cap=int(tariffs.get("admin_daily_safety_limit", 5000)))}


@router.get("/billing/tariffs")
async def get_billing_tariffs() -> dict[str, Any]:
    return TokenBillingService.load_tariffs()


@router.get("/billing/transactions")
async def list_my_transactions(
    limit: int = Query(default=30, ge=1, le=200),
    user: User = Depends(get_required_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    stmt = select(TokenTransaction).where(TokenTransaction.user_id == user.id).order_by(TokenTransaction.id.desc()).limit(limit)
    rows = (await db.execute(stmt)).scalars().all()
    return {
        "balance": user.token_balance,
        "role": user.role,
        "items": [
            {
                "id": t.id,
                "amount": t.amount,
                "balance_after": t.balance_after,
                "operation_type": t.operation_type,
                "description": t.description,
                "created_at": t.created_at.isoformat() if t.created_at else None,
            }
            for t in rows
        ],
    }


@router.get("/billing/admin/users")
async def admin_list_users(user: User = Depends(get_required_current_user), db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="Доступ разрешён только администратору")
    rows = (await db.execute(select(User).order_by(User.id.asc()))).scalars().all()
    return {"users": [serialize_user(u) for u in rows]}


@router.post("/billing/admin/adjust")
async def admin_adjust_user_account(
    payload: AdminAdjustRequest, user: User = Depends(get_required_current_user), db: AsyncSession = Depends(get_db)
) -> dict[str, Any]:
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="Доступ разрешён только администратору")
    target = (await db.execute(select(User).where(User.id == payload.target_user_id))).scalar_one_or_none()
    if not target:
        raise HTTPException(status_code=404, detail="Пользователь не найден")
    if target.id == user.id and payload.new_role == "user":
        admins_count = (await db.execute(select(func.count(User.id)).where(User.role == "admin"))).scalar_one()
        if admins_count <= 1:
            raise HTTPException(status_code=400, detail="Нельзя снять права администратора с единственного админа")
    await TokenBillingService.admin_adjust_user(
        db=db,
        target_user=target,
        delta_tokens=payload.delta_tokens,
        new_role=payload.new_role,
        reason=payload.reason,
    )
    await db.commit()
    await db.refresh(target)
    return {"user": serialize_user(target)}
