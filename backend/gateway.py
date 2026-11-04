import io
import hashlib
import hmac
import json
import os
import secrets
import threading
import time
import uuid
import wave
from http import HTTPStatus
from urllib.parse import parse_qs

from .services import auth, catalog, tips
from .services.audio import analyze_music
from .services.database import configured, connect
from .services.errors import ApiError
from .services.tempo import AnalysisError, decode_samples

MAX_BODY_BYTES = 4 * 1024 * 1024
FEATURES = (
    {"id": "bpm", "name": "Tempo y BPM", "requiresAuth": False},
    {"id": "recording", "name": "Grabación", "requiresAuth": False},
    {"id": "chords", "name": "Acordes y tonalidad", "requiresAuth": True},
    {"id": "similarity", "name": "Similitud acústica", "requiresAuth": True},
    {"id": "library", "name": "Historial", "requiresAuth": True},
)
DEFAULT_FEATURES = {"bpm", "recording", "chords"}
KNOWN_FEATURES = {item["id"] for item in FEATURES}
_MEMORY_RATE_LIMITS = {}
_MEMORY_RATE_LIMITS_LOCK = threading.Lock()
_MEMORY_RATE_LIMIT_SECRET = secrets.token_bytes(32)


def _response(start_response, status, payload, headers=()):
    body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    result_headers = [
        ("Content-Type", "application/json; charset=utf-8"),
        ("Content-Length", str(len(body))),
        ("Cache-Control", "no-store"),
        ("X-Content-Type-Options", "nosniff"),
        ("Referrer-Policy", "no-referrer"),
    ]
    result_headers.extend(headers)
    start_response(f"{status} {HTTPStatus(status).phrase}", result_headers)
    return [body]


def _request_body(environ, maximum=MAX_BODY_BYTES):
    try:
        length = int(environ.get("CONTENT_LENGTH", "0"))
    except ValueError:
        raise ApiError(400, "No pudimos validar el tamaño de la solicitud.")
    if length <= 0:
        raise ApiError(400, "La solicitud no contiene información.")
    if length > maximum:
        raise ApiError(413, "La solicitud supera el límite de 4 MB.")
    body = bytearray(environ["wsgi.input"].read(length))
    if len(body) != length:
        for index in range(len(body)):
            body[index] = 0
        raise ApiError(400, "La carga de la solicitud quedó incompleta.")
    return body


def _enforce_rate_limit(environ, scope, limit, window_seconds=900):
    remote = environ.get("REMOTE_ADDR", "")[:64] or "unknown"
    if configured():
        secret = (
            os.environ.get("APP_RATE_LIMIT_SECRET")
            or os.environ.get("JWT_SECRET")
            or os.environ.get("DATABASE_URL")
            or os.environ.get("POSTGRES_URL")
            or os.environ.get("POSTGRES_PASSWORD")
        )
        if not secret:
            raise ApiError(503, "No se pudo configurar el límite de solicitudes.")
        key = hmac.new(
            secret.encode("utf-8"),
            f"{scope}|{remote}".encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        with connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO auth_rate_limits (key_hash, window_started_at, attempts)
                VALUES (%s, now(), 1)
                ON CONFLICT (key_hash) DO UPDATE SET
                    attempts = CASE
                        WHEN auth_rate_limits.window_started_at
                             < now() - make_interval(secs => %s) THEN 1
                        ELSE auth_rate_limits.attempts + 1
                    END,
                    window_started_at = CASE
                        WHEN auth_rate_limits.window_started_at
                             < now() - make_interval(secs => %s) THEN now()
                        ELSE auth_rate_limits.window_started_at
                    END,
                    locked_until = CASE
                        WHEN auth_rate_limits.window_started_at
                             < now() - make_interval(secs => %s) THEN NULL
                        WHEN auth_rate_limits.attempts + 1 > %s
                             THEN now() + make_interval(secs => %s)
                        ELSE auth_rate_limits.locked_until
                    END
                RETURNING attempts, COALESCE(locked_until > now(), false)
                """,
                (key, window_seconds, window_seconds, window_seconds, limit, window_seconds),
            )
            attempts, locked = cursor.fetchone()
        if locked or attempts > limit:
            raise ApiError(429, "Recibiste demasiadas solicitudes. Espera unos minutos e inténtalo de nuevo.")
        return

    now = time.monotonic()
    key = hmac.new(
        _MEMORY_RATE_LIMIT_SECRET,
        f"{scope}|{remote}".encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    with _MEMORY_RATE_LIMITS_LOCK:
        started, attempts = _MEMORY_RATE_LIMITS.get(key, (now, 0))
        if now - started >= window_seconds:
            started, attempts = now, 0
        if attempts >= limit:
            raise ApiError(429, "Recibiste demasiadas solicitudes. Espera unos minutos e inténtalo de nuevo.")
        _MEMORY_RATE_LIMITS[key] = (started, attempts + 1)
        if len(_MEMORY_RATE_LIMITS) > 10000:
            expired = [
                entry for entry, (window_started, _) in _MEMORY_RATE_LIMITS.items()
                if now - window_started >= window_seconds
            ]
            for entry in expired:
                _MEMORY_RATE_LIMITS.pop(entry, None)


def _json_body(environ):
    body = _request_body(environ)
    try:
        return json.loads(body)
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise ApiError(400, "El cuerpo debe ser JSON válido.")
    finally:
        for index in range(len(body)):
            body[index] = 0


def _configured_features():
    configured_value = os.environ.get("SONGO_ENABLED_FEATURES")
    enabled = DEFAULT_FEATURES if configured_value is None else {
        feature.strip() for feature in configured_value.split(",") if feature.strip()
    }
    if enabled - KNOWN_FEATURES:
        raise ApiError(500, "La configuración de funciones contiene identificadores desconocidos.")
    database_ready = configured()
    auth_ready = database_ready and len(os.environ.get("JWT_SECRET", "").encode("utf-8")) >= 32
    return {
        "version": 1,
        "features": [
            {
                **feature,
                "enabled": feature["id"] in enabled and (
                    not feature["requiresAuth"] or auth_ready
                ),
                "available": feature["id"] in ("bpm", "recording", "chords")
                or database_ready,
            }
            for feature in FEATURES
        ],
        "auth_configured": auth_ready,
    }


def _enabled_feature_ids():
    return {
        feature["id"]
        for feature in _configured_features()["features"]
        if feature["enabled"]
    }


def _check_origin(environ):
    origin = environ.get("HTTP_ORIGIN")
    if not origin:
        return
    allowed = {
        value.strip().rstrip("/")
        for value in os.environ.get("APP_ALLOWED_ORIGINS", "").split(",")
        if value.strip()
    }
    base_url = os.environ.get("APP_BASE_URL")
    if base_url:
        allowed.add(base_url.rstrip("/"))
    host = environ.get("HTTP_HOST")
    if host:
        forwarded_scheme = environ.get("HTTP_X_FORWARDED_PROTO", "").split(",", 1)[0].strip()
        scheme = "https" if os.environ.get("VERCEL_ENV") == "production" or os.environ.get("APP_ENV") == "production" else "http"
        if forwarded_scheme in ("http", "https"):
            scheme = forwarded_scheme
        allowed.add(f"{scheme}://{host}".rstrip("/"))
    if origin.rstrip("/") not in allowed:
        raise ApiError(403, "El origen de la solicitud no está permitido.")


def _auth_route(path, method, environ):
    if path == "/api/auth/me" and method == "GET":
        user = auth.current_user(environ)
        auth_ready = configured() and len(os.environ.get("JWT_SECRET", "").encode("utf-8")) >= 32
        return 200, {"user": user, "auth_configured": auth_ready}, []
    if path in ("/api/auth/login", "/api/auth/register") and method == "POST":
        _check_origin(environ)
        payload = _json_body(environ)
        if not isinstance(payload, dict):
            raise ApiError(400, "El cuerpo debe ser un objeto JSON.")
        user, cookie = (
            auth.login(payload, environ)
            if path.endswith("/login")
            else auth.register(payload, environ)
        )
        return 201 if path.endswith("/register") else 200, {"user": user}, [("Set-Cookie", cookie)]
    if path == "/api/auth/logout" and method == "POST":
        _check_origin(environ)
        cookie = auth.logout(environ)
        return 200, {"ok": True}, [("Set-Cookie", cookie)]
    return None


def _decode_audio(environ):
    content_type = environ.get("CONTENT_TYPE", "").split(";", 1)[0].strip().lower()
    if content_type not in ("audio/wav", "audio/x-wav", "application/octet-stream"):
        raise ApiError(415, "Formato no compatible. Sube un WAV PCM.")
    return _request_body(environ)


def _analyze_request(environ, user):
    feature_config = _configured_features()
    enabled = {item["id"] for item in feature_config["features"] if item["enabled"]}
    if "bpm" not in enabled:
        raise ApiError(503, "El análisis de BPM está desactivado en este servidor.")

    content = _decode_audio(environ)
    frames = bytearray()
    samples = None
    try:
        with wave.open(io.BytesIO(content), "rb") as audio_file:
            channels = audio_file.getnchannels()
            sample_rate = audio_file.getframerate()
            frame_count = audio_file.getnframes()
            if channels not in (1, 2):
                raise ApiError(422, "El WAV debe tener uno o dos canales.")
            if sample_rate < 8000 or sample_rate > 96000:
                raise ApiError(422, "La frecuencia de muestreo WAV no es compatible.")
            duration = frame_count / sample_rate if sample_rate else 0
            if duration < 2 or duration > 180:
                raise ApiError(422, "El audio debe durar entre 2 segundos y 3 minutos.")
            frames.extend(audio_file.readframes(frame_count))
            samples = decode_samples(frames, audio_file.getsampwidth(), channels)
    except ApiError:
        raise
    except (wave.Error, EOFError, ValueError, ZeroDivisionError):
        raise ApiError(422, "El archivo no es un WAV PCM válido o está dañado.")
    finally:
        for index in range(len(frames)):
            frames[index] = 0
        for index in range(len(content)):
            content[index] = 0

    try:
        advanced = bool(user and "chords" in enabled)
        if advanced and sample_rate != 11025:
            raise ApiError(422, "El análisis avanzado requiere WAV mono a 11.025 Hz.")
        result = analyze_music(samples, sample_rate=sample_rate, advanced=advanced)
        if advanced:
            profile = result.pop("chroma_profile")
            fingerprint = result["audio_fingerprint"]
            if user and "similarity" in enabled:
                result["similarity_matches"] = catalog.find_similar(profile)
                result["similarity_disclaimer"] = (
                    "La similitud compara rasgos acústicos con el catálogo autorizado; "
                    "no es una evaluación legal de plagio."
                )
            if user:
                with connect() as connection, connection.cursor() as cursor:
                    cursor.execute(
                        """
                        INSERT INTO analysis_history (
                            user_id, bpm, musical_key, chord_timeline, audio_fingerprint, similarity_matches
                        )
                        VALUES (%s, %s, %s, %s::jsonb, %s, %s::jsonb)
                        """,
                        (
                            user["id"],
                            result["bpm"],
                            result.get("key"),
                            json.dumps(result.get("chords", [])),
                            fingerprint,
                            json.dumps(result.get("similarity_matches", [])),
                        ),
                    )
        else:
            result["locked_features"] = [
                feature["id"] for feature in FEATURES
                if feature["requiresAuth"] and feature["id"] in enabled
            ]
        return result
    except AnalysisError as error:
        raise ApiError(error.status, str(error))
    finally:
        for index in range(len(samples)):
            samples[index] = 0.0


def _history(environ, user):
    query = parse_qs(environ.get("QUERY_STRING", ""))
    try:
        limit = int(query.get("limit", ["20"])[0])
    except ValueError:
        raise ApiError(400, "El límite del historial debe ser un entero.")
    if not 1 <= limit <= 100:
        raise ApiError(400, "El historial permite consultar entre 1 y 100 registros.")
    with connect() as connection, connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT id, bpm, musical_key, chord_timeline, similarity_matches, created_at
            FROM analysis_history
            WHERE user_id = %s
              AND deleted_at IS NULL
            ORDER BY created_at DESC
            LIMIT %s
            """,
            (user["id"], limit),
        )
        rows = cursor.fetchall()
    return [
        {
            "id": str(row[0]),
            "bpm": row[1],
            "key": row[2],
            "chords": row[3],
            "similarity_matches": row[4],
            "created_at": row[5].isoformat(),
        }
        for row in rows
    ]


def _update_history_visibility(record_id, user, restore):
    with connect() as connection, connection.cursor() as cursor:
        if restore:
            cursor.execute(
                """
                UPDATE analysis_history
                SET deleted_at = NULL
                WHERE id = %s AND user_id = %s
                  AND deleted_at > now() - interval '10 seconds'
                RETURNING id
                """,
                (record_id, user["id"]),
            )
        else:
            cursor.execute(
                """
                UPDATE analysis_history
                SET deleted_at = now()
                WHERE id = %s AND user_id = %s AND deleted_at IS NULL
                RETURNING id
                """,
                (record_id, user["id"]),
            )
        return cursor.fetchone() is not None


def _route(path, method, environ, start_response):
    if path in ("/api/features", "/api/features/"):
        if method != "GET":
            raise ApiError(405, "Método no permitido.")
        return 200, _configured_features(), []

    if path.startswith("/api/auth/"):
        result = _auth_route(path, method, environ)
        if result is None:
            raise ApiError(404, "Ruta de autenticación no encontrada.")
        return result

    if path in ("/api/analyze", "/api/analyze/"):
        if method != "POST":
            raise ApiError(405, "Método no permitido.")
        user = auth.current_user(environ)
        if user:
            _check_origin(environ)
        return 200, _analyze_request(environ, user), []

    if path in ("/api/history", "/api/history/"):
        if method == "POST":
            _check_origin(environ)
            user = auth.require_user(environ)
            if "library" not in _enabled_feature_ids():
                raise ApiError(503, "La biblioteca está desactivada en este servidor.")
            payload = _json_body(environ)
            if not isinstance(payload, dict) or payload.get("action") not in ("delete", "restore"):
                raise ApiError(400, "La acción del historial no es válida.")
            try:
                record_id = str(uuid.UUID(payload.get("id", "")))
            except (ValueError, TypeError, AttributeError):
                raise ApiError(400, "El identificador del análisis no es válido.")
            restore = payload["action"] == "restore"
            if not _update_history_visibility(record_id, user, restore=restore):
                raise ApiError(404, "El análisis ya no está disponible para esta acción.")
            return 200, {"ok": True}, []
        if method != "GET":
            raise ApiError(405, "Método no permitido.")
        user = auth.require_user(environ)
        if "library" not in _enabled_feature_ids():
            raise ApiError(503, "La biblioteca está desactivada en este servidor.")
        return 200, {"items": _history(environ, user)}, []

    if path in ("/api/tips", "/api/tips/"):
        if method == "GET":
            user = auth.current_user(environ) if configured() else None
            return 200, {"items": tips.list_tips(user)}, []
        if method != "POST":
            raise ApiError(405, "Método no permitido.")
        _check_origin(environ)
        user = auth.require_user(environ, admin=True)
        payload = _json_body(environ)
        if not isinstance(payload, dict) or payload.get("action") not in ("save", "delete"):
            raise ApiError(400, "La acción de administración no es válida.")
        if payload["action"] == "save":
            return 200, {"item": tips.save_tip(payload.get("item"), user)}, []
        tip_id = payload.get("id")
        if not isinstance(tip_id, str) or not tips.delete_tip(tip_id):
            raise ApiError(404, "El consejo ya no está disponible.")
        return 200, {"ok": True}, []

    if path in ("/api/catalog", "/api/catalog/"):
        if method != "POST":
            raise ApiError(405, "Método no permitido.")
        _check_origin(environ)
        user = auth.require_user(environ, admin=True)
        if "similarity" not in _enabled_feature_ids():
            raise ApiError(503, "La comparación del catálogo está desactivada en este servidor.")
        payload = _json_body(environ)
        if not isinstance(payload, dict):
            raise ApiError(400, "El cuerpo debe ser un objeto JSON.")
        return 201, catalog.add_authorized_entry(payload, user), []

    if path in ("/api/health", "/api/health/") and method == "GET":
        return 200, {"status": "ok"}, []
    raise ApiError(404, "Ruta no encontrada.")


def application(environ, start_response):
    path = environ.get("PATH_INFO", "")
    method = environ.get("REQUEST_METHOD", "GET").upper()
    try:
        if method == "POST" and path in ("/api/analyze", "/api/analyze/"):
            _enforce_rate_limit(environ, "analyze", limit=20)
        elif method == "POST" and path in ("/api/auth/login", "/api/auth/register"):
            _enforce_rate_limit(environ, "auth", limit=30)
        elif method == "POST" and path in ("/api/catalog", "/api/catalog/"):
            _enforce_rate_limit(environ, "catalog", limit=30)
        elif method == "POST" and path in ("/api/history", "/api/history/"):
            _enforce_rate_limit(environ, "history", limit=30)
        elif method == "POST" and path in ("/api/tips", "/api/tips/"):
            _enforce_rate_limit(environ, "tips", limit=30)
        if path.startswith("/api/auth/") and method in ("POST", "DELETE"):
            _check_origin(environ)
        result = _route(path, method, environ, start_response)
        status, payload, headers = result
        if path in ("/api/auth/me", "/api/auth/logout"):
            # Keep logout/no-cookie responses independent from private cache behavior.
            headers.append(("Vary", "Cookie"))
        start_response_status = status
    except ApiError as error:
        if error.status == 405:
            if path in ("/api/history", "/api/history/"):
                allowed = "GET, POST"
            elif path in ("/api/tips", "/api/tips/"):
                allowed = "GET, POST"
            else:
                allowed = "GET" if path in ("/api/features", "/api/auth/me") else "POST"
            headers = [("Allow", allowed)]
        else:
            headers = []
        if error.status == 429:
            headers.append(("Retry-After", "900"))
        if path.startswith("/api/auth/") and error.status in (401, 503):
            headers.append(("Set-Cookie", auth.clear_cookie()))
        return _response(start_response, error.status, {"error": str(error)}, headers)
    except Exception:
        return _response(start_response, 500, {"error": "Ocurrió un error interno. Inténtalo más tarde."})
    return _response(start_response, start_response_status, payload, headers)
