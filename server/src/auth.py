import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import Header, HTTPException
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError

from .config import SESSION_TTL_HOURS
from .models import AuthPayload, AuthResponse, UserRecord
from .orm import DbSession, DbUser
from .storage import WorkflowStore, utc_now


DEFAULT_USERNAME = "local"


def parse_timestamp(value: str) -> datetime | None:
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def session_expires_at() -> str:
    ttl_hours = max(1, SESSION_TTL_HOURS)
    return (datetime.now(timezone.utc) + timedelta(hours=ttl_hours)).isoformat()


def hash_password(password: str, salt: str | None = None) -> str:
    password_salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), password_salt.encode("utf-8"), 120_000)
    return f"{password_salt}${digest.hex()}"


def verify_password(password: str, stored_hash: str) -> bool:
    try:
        salt, digest = stored_hash.split("$", 1)
    except ValueError:
        return False
    candidate = hash_password(password, salt).split("$", 1)[1]
    return hmac.compare_digest(candidate, digest)


class AuthService:
    def __init__(self, store: WorkflowStore) -> None:
        self.store = store

    def ensure_default_user(self) -> str:
        existing = self.get_user_by_username(DEFAULT_USERNAME)
        if existing:
            return existing.id
        return self.create_user(DEFAULT_USERNAME, secrets.token_urlsafe(24)).user.id

    def create_user(self, username: str, password: str) -> AuthResponse:
        username = username.strip().lower()
        if not username:
            raise HTTPException(status_code=400, detail="Username is required")
        user_id = secrets.token_urlsafe(16)
        created_at = utc_now()
        try:
            with self.store._connect() as connection:
                connection.add(
                    DbUser(
                        id=user_id,
                        username=username,
                        password_hash=hash_password(password),
                        created_at=created_at,
                    )
                )
                connection.commit()
        except IntegrityError as error:
            raise HTTPException(status_code=409, detail="Username already exists") from error
        self.store.ensure_default_workspace(user_id, username)
        token = self.create_session(user_id)
        return AuthResponse(token=token, user=UserRecord(id=user_id, username=username, created_at=created_at))

    def authenticate(self, username: str, password: str) -> AuthResponse:
        user = self.get_user_by_username(username.strip().lower())
        if not user:
            raise HTTPException(status_code=401, detail="Invalid username or password")
        with self.store._connect() as connection:
            db_user = connection.scalar(select(DbUser).where(DbUser.id == user.id))
        if not db_user or not verify_password(password, db_user.password_hash):
            raise HTTPException(status_code=401, detail="Invalid username or password")
        token = self.create_session(user.id)
        return AuthResponse(token=token, user=user)

    def create_session(self, user_id: str) -> str:
        token = secrets.token_urlsafe(32)
        with self.store._connect() as connection:
            connection.add(
                DbSession(
                    token=token,
                    user_id=user_id,
                    created_at=utc_now(),
                    expires_at=session_expires_at(),
                )
            )
            connection.commit()
        return token

    def get_user_by_username(self, username: str) -> UserRecord | None:
        with self.store._connect() as connection:
            row = connection.scalar(select(DbUser).where(DbUser.username == username))
        return UserRecord(id=row.id, username=row.username, created_at=row.created_at) if row else None

    def get_user_by_token(self, token: str) -> UserRecord | None:
        with self.store._connect() as connection:
            row = connection.execute(
                select(DbUser, DbSession)
                .join(DbSession, DbSession.user_id == DbUser.id)
                .where(DbSession.token == token)
            ).one_or_none()
            if not row:
                return None
            db_user, session = row
            expires_at = parse_timestamp(session.expires_at)
            if not expires_at or expires_at <= datetime.now(timezone.utc):
                connection.execute(delete(DbSession).where(DbSession.token == token))
                connection.commit()
                return None
        return UserRecord(id=db_user.id, username=db_user.username, created_at=db_user.created_at)

    def prune_expired_sessions(self) -> int:
        now = utc_now()
        with self.store._connect() as connection:
            result = connection.execute(
                delete(DbSession).where(DbSession.expires_at <= now)
            )
            connection.commit()
        return result.rowcount or 0

    def logout(self, token: str) -> None:
        with self.store._connect() as connection:
            connection.execute(delete(DbSession).where(DbSession.token == token))
            connection.commit()


auth_service: AuthService | None = None


def set_auth_service(service: AuthService) -> None:
    global auth_service
    auth_service = service


def require_auth(authorization: str | None = Header(default=None)) -> UserRecord:
    if not auth_service:
        raise HTTPException(status_code=500, detail="Auth service is not initialized")
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Authentication required")
    token = authorization.removeprefix("Bearer ").strip()
    user = auth_service.get_user_by_token(token)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    return user


def current_token(authorization: str | None = Header(default=None)) -> str:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Authentication required")
    return authorization.removeprefix("Bearer ").strip()


def register(payload: AuthPayload) -> AuthResponse:
    if not auth_service:
        raise HTTPException(status_code=500, detail="Auth service is not initialized")
    return auth_service.create_user(payload.username, payload.password)


def login(payload: AuthPayload) -> AuthResponse:
    if not auth_service:
        raise HTTPException(status_code=500, detail="Auth service is not initialized")
    return auth_service.authenticate(payload.username, payload.password)
