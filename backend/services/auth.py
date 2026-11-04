import base64
import binascii
import hashlib
import hmac
import json
import os
import re
import secrets
import time
import uuid
from http.cookies import SimpleCookie

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError
import psycopg

from .database import connect, configured
from .errors import ApiError

PASSWORD_HASHER = PasswordHasher(
    time_cost=int(os.environ.get("PASSWORD_HASH_TIME_COST", "3")),
    memory_cost=int(os.environ.get("PASSWORD_HASH_MEMORY_COST", "65536")),
    parallelism=int(os.environ.get("PASSWORD_HASH_PARALLELISM", "2")),
    hash_len=32,
    salt_len=16,
)
EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
MAX_PASSWORD_LENGTH = 128


def _b64url(value):
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _secret():
    secret = os.environ.get("JWT_SECRET", "")
    if len(secret.encode("utf-8")) < 32:
        raise ApiError(503, "La autenticación no está configurada en el servidor.")
    return secret.encode("utf-8")


def _encode_token(payload):
    header = _b64url(b'{"alg":"HS256","typ":"JWT"}')
    body = _b64url(json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8"))
    unsigned = f"{header}.{body}".encode("ascii")
    signature = hmac.new(_secret(), unsigned, hashlib.sha256).digest()
    return f"{unsigned.decode('ascii')}.{_b64url(signature)}"


def _decode_token(token):
    parts = token.split(".")
    if len(parts) != 3:
        return None
    header, payload, signature = parts
    unsigned = f"{header}.{payload}".encode("ascii")
    expected = _b64url(hmac.new(_secret(), unsigned, hashlib.sha256).digest())
    if not hmac.compare_digest(signature, expected):
        return None
    try:
        decoded_header = json.loads(base64.urlsafe_b64decode(header + "=" * (-len(header) % 4)))
        claims = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
    except (ValueError, json.JSONDecodeError, binascii.Error):
        return None
    now = int(time.time())
    if (
        decoded_header != {"alg": "HS256", "typ": "JWT"}
        or not isinstance(claims, dict)
        or claims.get("iss") != os.environ.get("JWT_ISSUER", "songo")
        or not isinstance(claims.get("exp"), int)
        or claims["exp"] <= now
        or not isinstance(claims.get("sub"), str)
        or not isinstance(claims.get("jti"), str)
    ):
        return None
    return claims


def cookie_name():
    return "__Host-songo_session" if _is_production() else "songo_session"


def _is_production():
    return os.environ.get("APP_ENV") == "production" or os.environ.get("VERCEL_ENV") == "production"


def _cookie_token(environ):
    cookie = SimpleCookie()
    try:
        cookie.load(environ.get("HTTP_COOKIE", ""))
    except Exception:
        return None
    morsel = cookie.get(cookie_name())
    return morsel.value if morsel else None


def _user_agent_hash(environ):
    return hashlib.sha256(environ.get("HTTP_USER_AGENT", "").encode("utf-8")[:512]).hexdigest()


def _session_cookie(token, max_age):
    secure = "; Secure" if _is_production() else ""
    return (
        f"{cookie_name()}={token}; Max-Age={max_age}; Path=/; "
        f"HttpOnly; SameSite=Lax{secure}"
    )


def clear_cookie():
    secure = "; Secure" if _is_production() else ""
    return f"{cookie_name()}=; Max-Age=0; Path=/; HttpOnly; SameSite=Lax{secure}"


def _normalize_email(email):
    if not isinstance(email, str):
        raise ApiError(400, "Escribe un correo electrónico válido.")
    normalized = email.strip().lower()
    if len(normalized) > 254 or not EMAIL_PATTERN.fullmatch(normalized):
        raise ApiError(400, "Escribe un correo electrónico válido.")
    return normalized


def _validate_password(password):
    if not isinstance(password, str) or not 12 <= len(password) <= MAX_PASSWORD_LENGTH:
        raise ApiError(400, "La contraseña debe tener entre 12 y 128 caracteres.")
    return password


def _rate_limit_key(email, environ):
    secret = _secret()
    remote = environ.get("REMOTE_ADDR", "")[:64]
    return hmac.new(secret, f"{email}|{remote}".encode("utf-8"), hashlib.sha256).hexdigest()


def _increment_login_attempts(key):
    with connect() as connection, connection.cursor() as cursor:
        cursor.execute(
            """
            DELETE FROM auth_rate_limits
            WHERE window_started_at < now() - interval '1 day'
              AND (locked_until IS NULL OR locked_until < now())
            """
        )
        cursor.execute(
            """
            INSERT INTO auth_rate_limits (key_hash, window_started_at, attempts)
            VALUES (%s, now(), 1)
            ON CONFLICT (key_hash) DO UPDATE SET
                attempts = CASE
                    WHEN auth_rate_limits.window_started_at < now() - interval '15 minutes' THEN 1
                    ELSE auth_rate_limits.attempts + 1
                END,
                window_started_at = CASE
                    WHEN auth_rate_limits.window_started_at < now() - interval '15 minutes' THEN now()
                    ELSE auth_rate_limits.window_started_at
                END,
                locked_until = CASE
                    WHEN auth_rate_limits.window_started_at < now() - interval '15 minutes' THEN NULL
                    WHEN auth_rate_limits.attempts + 1 >= 8 THEN now() + interval '15 minutes'
                    ELSE auth_rate_limits.locked_until
                END
            RETURNING attempts, locked_until > now()
            """,
            (key,),
        )
        attempts, locked = cursor.fetchone()
        if locked or attempts > 8:
            raise ApiError(429, "Demasiados intentos. Espera 15 minutos antes de volver a intentarlo.")


def _clear_login_attempts(key):
    with connect() as connection, connection.cursor() as cursor:
        cursor.execute("DELETE FROM auth_rate_limits WHERE key_hash = %s", (key,))


def _create_session(user, environ):
    ttl = int(os.environ.get("SESSION_TTL_SECONDS", "43200"))
    if ttl < 300 or ttl > 2592000:
        raise ApiError(503, "La duración de sesión configurada no es válida.")
    now = int(time.time())
    session_id = str(uuid.uuid4())
    expires = now + ttl
    with connect() as connection, connection.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO auth_sessions (id, user_id, expires_at, user_agent_hash)
            VALUES (%s, %s, to_timestamp(%s), %s)
            """,
            (session_id, user["id"], expires, _user_agent_hash(environ)),
        )
    token = _encode_token({
        "iss": os.environ.get("JWT_ISSUER", "songo"),
        "sub": str(user["id"]),
        "jti": session_id,
        "iat": now,
        "exp": expires,
    })
    return token, ttl


def register(payload, environ):
    if not configured():
        raise ApiError(503, "El registro requiere configurar PostgreSQL.")
    email = _normalize_email(payload.get("email"))
    password = _validate_password(payload.get("password"))
    key = _rate_limit_key(email, environ)
    _increment_login_attempts(key)
    password_hash = PASSWORD_HASHER.hash(password)
    try:
        with connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO users (email, password_hash)
                VALUES (%s, %s)
                RETURNING id, email, role
                """,
                (email, password_hash),
            )
            row = cursor.fetchone()
    except ApiError:
        raise
    except Exception as error:
        if getattr(error, "sqlstate", None) == "23505":
            raise ApiError(409, "No se pudo crear la cuenta con ese correo.")
        raise
    user = {"id": str(row[0]), "email": row[1], "role": row[2]}
    _clear_login_attempts(key)
    token, ttl = _create_session(user, environ)
    return user, _session_cookie(token, ttl)


def login(payload, environ):
    if not configured():
        raise ApiError(503, "El inicio de sesión requiere configurar PostgreSQL.")
    email = _normalize_email(payload.get("email"))
    password = _validate_password(payload.get("password"))
    key = _rate_limit_key(email, environ)
    _increment_login_attempts(key)

    with connect() as connection, connection.cursor() as cursor:
        cursor.execute(
            "SELECT id, email, password_hash, role FROM users WHERE email = %s",
            (email,),
        )
        row = cursor.fetchone()

    valid = False
    if row:
        try:
            valid = PASSWORD_HASHER.verify(row[2], password)
        except (VerifyMismatchError, VerificationError, InvalidHashError):
            valid = False
    if not valid:
        raise ApiError(401, "Correo o contraseña incorrectos.")

    _clear_login_attempts(key)
    user = {"id": str(row[0]), "email": row[1], "role": row[3]}
    token, ttl = _create_session(user, environ)
    return user, _session_cookie(token, ttl)


def current_user(environ):
    token = _cookie_token(environ)
    if not token:
        return None
    try:
        claims = _decode_token(token)
        if not claims:
            return None
        with connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT users.id, users.email, users.role
                FROM auth_sessions
                JOIN users ON users.id = auth_sessions.user_id
                WHERE auth_sessions.id = %s
                  AND auth_sessions.user_id = %s
                  AND auth_sessions.revoked_at IS NULL
                  AND auth_sessions.expires_at > now()
                """,
                (claims["jti"], claims["sub"]),
            )
            row = cursor.fetchone()
        if not row:
            return None
        return {"id": str(row[0]), "email": row[1], "role": row[2]}
    except ApiError:
        raise
    except psycopg.Error:
        raise ApiError(503, "No fue posible verificar la sesión.")


def require_user(environ, admin=False):
    user = current_user(environ)
    if not user:
        raise ApiError(401, "Inicia sesión para continuar.")
    if admin and user["role"] != "admin":
        raise ApiError(403, "Esta operación requiere permisos de administración.")
    return user


def logout(environ):
    token = _cookie_token(environ)
    if token:
        claims = _decode_token(token)
        if claims:
            with connect() as connection, connection.cursor() as cursor:
                cursor.execute(
                    "UPDATE auth_sessions SET revoked_at = now() WHERE id = %s AND revoked_at IS NULL",
                    (claims["jti"],),
                )
    return clear_cookie()


def revoke_other_sessions(user_id, keep_session_id):
    with connect() as connection, connection.cursor() as cursor:
        cursor.execute(
            """
            UPDATE auth_sessions
            SET revoked_at = now()
            WHERE user_id = %s AND id <> %s AND revoked_at IS NULL
            """,
            (user_id, keep_session_id),
        )
