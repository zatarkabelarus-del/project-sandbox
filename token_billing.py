import json
from datetime import datetime, timedelta, timezone
from typing import Any
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import BILLING_TARIFFS_PATH, AppMode, get_settings
from core.exceptions import AuthenticationError, InsufficientTokensError
from database.models import TokenTransaction, User


class TokenBillingService:
    """Движок биллинга токенов с защитой от мультиаккаунтов (устройство/IP/e-mail) и лимитом админа."""

    @staticmethod
    def load_tariffs() -> dict[str, Any]:
        if BILLING_TARIFFS_PATH.exists():
            with open(BILLING_TARIFFS_PATH, "r", encoding="utf-8") as fh:
                return json.load(fh)
        return {
            "welcome_bonus": 100,
            "max_bonus_per_device": 1,
            "max_bonus_per_ip_24h": 2,
            "admin_daily_safety_limit": 5000,
            "token_usd_rate": 0.01,
            "blocked_email_domains": [],
            "operations": {},
        }

    @classmethod
    def normalize_email_canonical(cls, raw_email: str) -> str:
        clean = raw_email.strip().lower()
        if "@" not in clean:
            return clean
        local_part, domain = clean.split("@", 1)
        if "+" in local_part:
            local_part = local_part.split("+", 1).pop(0)
        if domain in ("gmail.com", "googlemail.com"):
            local_part = local_part.replace(".", "")
        if domain in ("ya.ru", "yandex.by", "yandex.kz", "yandex.ua"):
            domain = "yandex.ru"
        return f"{local_part}@{domain}"

    @classmethod
    def validate_email_domain(cls, raw_email: str) -> None:
        tariffs = cls.load_tariffs()
        blocked = {d.strip().lower() for d in tariffs.get("blocked_email_domains", []) if d}
        domain = raw_email.strip().lower().split("@", 1).pop()
        if domain in blocked:
            raise ValueError("Регистрация с временных одноразовых почтовых доменов запрещена.")

    @classmethod
    def get_operation_cost(cls, operation_type: str, quantity: int = 1) -> int:
        tariffs = cls.load_tariffs()
        op_cfg = tariffs.get("operations", {}).get(operation_type, {})
        unit_cost = int(op_cfg.get("cost", 0))
        return max(0, unit_cost * max(1, quantity))

    @classmethod
    async def can_grant_welcome_bonus(
        cls,
        db: AsyncSession,
        canonical_email: str,
        device_fingerprint: str | None,
        registration_ip: str | None,
    ) -> tuple[bool, str]:
        tariffs = cls.load_tariffs()
        dup_canonical = (
            await db.execute(select(func.count(User.id)).where(User.canonical_email == canonical_email, User.bonus_granted.is_(True)))
        ).scalar_one()
        if dup_canonical > 0:
            return False, "Бонус на данный почтовый адрес уже был выдан ранее"

        max_per_device = int(tariffs.get("max_bonus_per_device", 1))
        if device_fingerprint and max_per_device > 0:
            dev_count = (
                await db.execute(
                    select(func.count(User.id)).where(User.device_fingerprint == device_fingerprint, User.bonus_granted.is_(True))
                )
            ).scalar_one()
            if dev_count >= max_per_device:
                return False, "Приветственный бонус на это устройство уже был начислен"

        max_per_ip = int(tariffs.get("max_bonus_per_ip_24h", 2))
        if registration_ip and max_per_ip > 0:
            since = datetime.now(timezone.utc) - timedelta(hours=24)
            ip_count = (
                await db.execute(
                    select(func.count(User.id)).where(
                        User.registration_ip == registration_ip,
                        User.bonus_granted.is_(True),
                        User.created_at >= since,
                    )
                )
            ).scalar_one()
            if ip_count >= max_per_ip:
                return False, "Превышен суточный лимит бонусных регистраций с одного IP"

        return True, "Приветственный бонус при регистрации"
    @classmethod
    async def grant_welcome_bonus(cls, db: AsyncSession, user: User) -> TokenTransaction | None:
        eligible, reason = await cls.can_grant_welcome_bonus(
            db=db,
            canonical_email=user.canonical_email,
            device_fingerprint=user.device_fingerprint,
            registration_ip=user.registration_ip,
        )
        if not eligible:
            user.bonus_granted = False
            tx = TokenTransaction(
                user_id=user.id,
                amount=0,
                balance_after=user.token_balance,
                operation_type="welcome_bonus_skipped",
                description=reason,
            )
            db.add(tx)
            await db.flush()
            return tx

        tariffs = cls.load_tariffs()
        bonus = int(tariffs.get("welcome_bonus", 100))
        user.token_balance += bonus
        user.bonus_granted = True
        tx = TokenTransaction(
            user_id=user.id,
            amount=bonus,
            balance_after=user.token_balance,
            operation_type="welcome_bonus",
            description=reason,
        )
        db.add(tx)
        await db.flush()
        return tx

    @classmethod
    async def get_admin_spent_today(cls, db: AsyncSession, user_id: int) -> int:
        start_of_day = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        stmt = select(func.coalesce(func.sum(TokenTransaction.amount), 0)).where(
            TokenTransaction.user_id == user_id,
            TokenTransaction.amount < 0,
            TokenTransaction.created_at >= start_of_day,
        )
        spent_neg = (await db.execute(stmt)).scalar_one()
        return abs(int(spent_neg or 0))

    @classmethod
    async def charge_user(
        cls,
        db: AsyncSession,
        user: User | None,
        operation_type: str,
        quantity: int = 1,
        description: str = "",
    ) -> int:
        cost = cls.get_operation_cost(operation_type, quantity=quantity)
        if user is None:
            if get_settings().app_mode != AppMode.DEV_MOCK and cost > 0:
                raise AuthenticationError("Для запуска платной ИИ-генерации войдите или зарегистрируйтесь (100 бонусных токенов).")
            return 0
        if cost <= 0:
            return 0

        tariffs = cls.load_tariffs()
        if user.role == "admin":
            daily_cap = int(tariffs.get("admin_daily_safety_limit", 5000))
            spent_today = await cls.get_admin_spent_today(db, user.id)
            if spent_today + cost > daily_cap:
                raise InsufficientTokensError(
                    f"Превышен суточный лимит безопасности администратора ({daily_cap} токенов).",
                    details={"daily_cap": daily_cap, "spent_today": spent_today, "requested": cost},
                )
            tx = TokenTransaction(
                user_id=user.id,
                amount=-cost,
                balance_after=user.token_balance,
                operation_type=operation_type,
                description=description or f"[ADMIN TEST] {operation_type} (x{quantity})",
            )
            db.add(tx)
            await db.flush()
            return cost

        if user.token_balance < cost:
            raise InsufficientTokensError(
                f"Недостаточно токенов: требуется {cost}, доступно {user.token_balance}.",
                details={"required": cost, "available": user.token_balance, "operation": operation_type},
            )

        user.token_balance -= cost
        tx = TokenTransaction(
            user_id=user.id,
            amount=-cost,
            balance_after=user.token_balance,
            operation_type=operation_type,
            description=description or f"Списание за операцию: {operation_type} (x{quantity})",
        )
        db.add(tx)
        await db.flush()
        return cost

    @classmethod
    async def admin_adjust_user(
        cls,
        db: AsyncSession,
        target_user: User,
        delta_tokens: int = 0,
        new_role: str | None = None,
        reason: str = "",
    ) -> User:
        if delta_tokens != 0:
            target_user.token_balance = max(0, target_user.token_balance + delta_tokens)
            tx = TokenTransaction(
                user_id=target_user.id,
                amount=delta_tokens,
                balance_after=target_user.token_balance,
                operation_type="admin_adjustment",
                description=reason or f"Корректировка баланса администратором ({delta_tokens:+d})",
            )
            db.add(tx)
        if new_role in ("admin", "user"):
            target_user.role = new_role
        await db.flush()
        return target_user
