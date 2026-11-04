import os

import psycopg

from .errors import ApiError


def configured():
    return bool(os.environ.get("DATABASE_URL") or os.environ.get("POSTGRES_URL"))


def connect():
    connection_string = os.environ.get("DATABASE_URL") or os.environ.get("POSTGRES_URL")
    if not connection_string:
        raise ApiError(503, "La cuenta requiere una base PostgreSQL configurada.")
    try:
        return psycopg.connect(
            connection_string,
            connect_timeout=int(os.environ.get("DATABASE_CONNECT_TIMEOUT", "5")),
        )
    except (psycopg.OperationalError, ValueError):
        raise ApiError(503, "No fue posible conectar con la base de datos.")
