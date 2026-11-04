from psycopg import Error as PsycopgError

from .database import connect
from .errors import ApiError


def get_admin_metrics(analyzer_enabled, analyzer_available):
    try:
        with connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT
                    (SELECT count(*) FROM users) AS users_total,
                    (SELECT count(*) FROM users WHERE role = 'admin') AS admins_total,
                    (
                        SELECT count(*)
                        FROM auth_sessions
                        WHERE revoked_at IS NULL AND expires_at > now()
                    ) AS active_sessions,
                    (SELECT count(*) FROM analysis_history WHERE deleted_at IS NULL) AS saved_analyses_total,
                    (
                        SELECT count(*)
                        FROM analysis_history
                        WHERE deleted_at IS NULL
                          AND created_at >= now() - interval '24 hours'
                    ) AS saved_analyses_last_24h,
                    now() AS generated_at
                """
            )
            row = cursor.fetchone()
    except PsycopgError as error:
        message = "No fue posible consultar las métricas. Revisa la conexión y el esquema de PostgreSQL."
        raise ApiError(503, message) from error

    return {
        "users_total": row[0],
        "admins_total": row[1],
        "active_sessions": row[2],
        "saved_analyses_total": row[3],
        "saved_analyses_last_24h": row[4],
        "analyzer": {
            "enabled": analyzer_enabled,
            "available": analyzer_available,
            "status": "operational" if analyzer_enabled and analyzer_available else "unavailable",
        },
        "generated_at": row[5].isoformat(),
    }
