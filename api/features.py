import json
import os
from http import HTTPStatus

FEATURES = (
    {"id": "bpm", "requiresAuth": False},
    {"id": "recording", "requiresAuth": False},
    {"id": "chords", "requiresAuth": True},
    {"id": "similarity", "requiresAuth": True},
    {"id": "library", "requiresAuth": True},
)
DEFAULT_ENABLED_FEATURES = {"bpm", "recording"}
KNOWN_FEATURES = {feature["id"] for feature in FEATURES}


def enabled_features():
    configured = os.environ.get("SONGO_ENABLED_FEATURES")
    if configured is None:
        enabled = DEFAULT_ENABLED_FEATURES
    else:
        enabled = {feature.strip() for feature in configured.split(",") if feature.strip()}
        unknown = enabled - KNOWN_FEATURES
        if unknown:
            raise ValueError(f"Unknown feature ids: {', '.join(sorted(unknown))}")

    return [
        {**feature, "enabled": feature["id"] in enabled}
        for feature in FEATURES
    ]


def application(environ, start_response):
    if environ.get("REQUEST_METHOD", "GET").upper() != "GET":
        body = json.dumps({"error": "Método no permitido."}).encode("utf-8")
        start_response(
            f"{HTTPStatus.METHOD_NOT_ALLOWED.value} {HTTPStatus.METHOD_NOT_ALLOWED.phrase}",
            [
                ("Content-Type", "application/json; charset=utf-8"),
                ("Content-Length", str(len(body))),
                ("Cache-Control", "no-store"),
                ("Allow", "GET"),
            ],
        )
        return [body]

    if environ.get("PATH_INFO", "") not in ("", "/", "/api/features"):
        body = json.dumps({"error": "Ruta no encontrada."}).encode("utf-8")
        start_response(
            f"{HTTPStatus.NOT_FOUND.value} {HTTPStatus.NOT_FOUND.phrase}",
            [
                ("Content-Type", "application/json; charset=utf-8"),
                ("Content-Length", str(len(body))),
                ("Cache-Control", "no-store"),
            ],
        )
        return [body]

    try:
        payload = {"version": 1, "features": enabled_features()}
    except ValueError:
        body = json.dumps({"error": "La configuración de funciones no es válida."}).encode("utf-8")
        start_response(
            f"{HTTPStatus.INTERNAL_SERVER_ERROR.value} {HTTPStatus.INTERNAL_SERVER_ERROR.phrase}",
            [
                ("Content-Type", "application/json; charset=utf-8"),
                ("Content-Length", str(len(body))),
                ("Cache-Control", "no-store"),
            ],
        )
        return [body]

    body = json.dumps(payload).encode("utf-8")
    start_response(
        f"{HTTPStatus.OK.value} {HTTPStatus.OK.phrase}",
        [
            ("Content-Type", "application/json; charset=utf-8"),
            ("Content-Length", str(len(body))),
            ("Cache-Control", "no-store"),
            ("X-Content-Type-Options", "nosniff"),
        ],
    )
    return [body]
