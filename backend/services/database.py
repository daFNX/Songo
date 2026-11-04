import os
from urllib.parse import parse_qs, unquote, urlsplit

import psycopg

from .errors import ApiError


def configured():
    return bool(os.environ.get("DATABASE_URL") or os.environ.get("POSTGRES_URL"))


def connect():
    connection_string = os.environ.get("DATABASE_URL") or os.environ.get("POSTGRES_URL")
    if not connection_string:
        raise ApiError(503, "La cuenta requiere una base PostgreSQL configurada.")
    try:
        timeout = int(os.environ.get("DATABASE_CONNECT_TIMEOUT", "5"))
    except ValueError:
        raise ApiError(503, "El tiempo máximo de conexión a la base no es válido.")
    try:
        return psycopg.connect(
            connection_string,
            connect_timeout=timeout,
        )
    except psycopg.ProgrammingError:
        parsed_url = urlsplit(connection_string)
        if parsed_url.scheme in ("postgres", "postgresql") and parsed_url.hostname and parsed_url.username and parsed_url.path:
            try:
                options = parse_qs(parsed_url.query)
                return psycopg.connect(
                    host=parsed_url.hostname,
                    port=parsed_url.port or 5432,
                    dbname=unquote(parsed_url.path.lstrip("/")),
                    user=unquote(parsed_url.username),
                    password=unquote(parsed_url.password or ""),
                    sslmode=options.get("sslmode", ["require"])[0],
                    connect_timeout=timeout,
                )
            except ValueError:
                pass
            except (psycopg.OperationalError, psycopg.ProgrammingError):
                pass
        components = {
            "host": os.environ.get("POSTGRES_HOST"),
            "dbname": os.environ.get("POSTGRES_DATABASE"),
            "user": os.environ.get("POSTGRES_USER"),
            "password": os.environ.get("POSTGRES_PASSWORD"),
        }
        if not all(components.values()):
            raise ApiError(503, "La URL de PostgreSQL no es válida.")
        try:
            return psycopg.connect(
                **components,
                port=int(os.environ.get("POSTGRES_PORT", "5432")),
                sslmode=os.environ.get("POSTGRES_SSLMODE", "require"),
                connect_timeout=timeout,
            )
        except (psycopg.OperationalError, psycopg.ProgrammingError, ValueError):
            raise ApiError(503, "No fue posible conectar con la base de datos.")
    except (psycopg.OperationalError, ValueError):
        raise ApiError(503, "No fue posible conectar con la base de datos.")
