import uuid

from .database import configured, connect
from .errors import ApiError

STARTER_TIPS = (
    {
        "id": "30cda301-87b9-4ad0-98ba-3ce235c92201",
        "title": "Usa el BPM como punto de partida",
        "category": "Producción",
        "content": "El tempo detectado es una referencia. Escucha el pulso con el metrónomo y decide si la canción se siente mejor a la mitad o al doble de esa velocidad.",
        "exercise": "Prueba a tocar el mismo fragmento a BPM detectado, a la mitad y al doble. Anota cuál conserva mejor el groove.",
        "published": True,
    },
    {
        "id": "30cda301-87b9-4ad0-98ba-3ce235c92202",
        "title": "Comprueba la tonalidad con el bajo",
        "category": "Armonía",
        "content": "La tonalidad estimada puede confundirse en pasajes breves o con muchos instrumentos. Aísla la nota que se siente como reposo y compárala con el bajo y la melodía.",
        "exercise": "Tararea la nota de reposo y tócala en tu instrumento. Después prueba la escala mayor y su relativa menor.",
        "published": True,
    },
    {
        "id": "30cda301-87b9-4ad0-98ba-3ce235c92203",
        "title": "Convierte una secuencia en una canción",
        "category": "Composición",
        "content": "Una progresión de acordes es un mapa, no una regla. El ritmo armónico, la inversión y la melodía cambian por completo cómo se percibe una misma secuencia.",
        "exercise": "Mantén los acordes detectados y cambia el patrón rítmico; luego conserva el ritmo y prueba inversiones distintas.",
        "published": True,
    },
    {
        "id": "30cda301-87b9-4ad0-98ba-3ce235c92204",
        "title": "Contrasta el análisis con tu oído",
        "category": "Entrenamiento auditivo",
        "content": "Los detectores automáticos ofrecen hipótesis, no una transcripción definitiva. Un cambio de sección o una síncopa puede alterar la lectura del pulso y la armonía.",
        "exercise": "Escucha el fragmento sin mirar el resultado, marca el pulso con la mano y después compara tu estimación con Songo.",
        "published": True,
    },
)

TIP_FIELDS = {
    "title": (3, 100),
    "category": (2, 40),
    "content": (10, 1200),
    "exercise": (10, 500),
}


def _validate_tip(payload):
    values = {}
    for field, (minimum, maximum) in TIP_FIELDS.items():
        value = payload.get(field)
        if not isinstance(value, str):
            raise ApiError(400, f"El campo {field} es obligatorio.")
        value = value.strip()
        if not minimum <= len(value) <= maximum:
            raise ApiError(400, f"El campo {field} debe tener entre {minimum} y {maximum} caracteres.")
        values[field] = value
    published = payload.get("published", True)
    if not isinstance(published, bool):
        raise ApiError(400, "El estado de publicación no es válido.")
    values["published"] = published
    return values


def _ensure_starter_tips(cursor, admin_id):
    cursor.executemany(
        """
        INSERT INTO musical_tips (id, title, category, content, exercise, published, created_by)
        VALUES (%s, %s, %s, %s, %s, true, %s)
        ON CONFLICT (id) DO NOTHING
        """,
        [
            (
                tip["id"],
                tip["title"],
                tip["category"],
                tip["content"],
                tip["exercise"],
                admin_id,
            )
            for tip in STARTER_TIPS
        ],
    )


def list_tips(user=None):
    if not configured():
        return list(STARTER_TIPS)
    with connect() as connection, connection.cursor() as cursor:
        if user and user["role"] == "admin":
            _ensure_starter_tips(cursor, user["id"])
        cursor.execute(
            """
            SELECT id, title, category, content, exercise, published, updated_at
            FROM musical_tips
            WHERE deleted_at IS NULL AND (published IS TRUE OR %s)
            ORDER BY category, title
            """,
            (bool(user and user["role"] == "admin"),),
        )
        rows = cursor.fetchall()
    if not rows:
        with connect() as connection, connection.cursor() as cursor:
            cursor.execute("SELECT EXISTS (SELECT 1 FROM musical_tips)")
            if not cursor.fetchone()[0]:
                return list(STARTER_TIPS)
        return []
    return [
        {
            "id": str(row[0]),
            "title": row[1],
            "category": row[2],
            "content": row[3],
            "exercise": row[4],
            "published": row[5],
            "updated_at": row[6].isoformat(),
        }
        for row in rows
    ]


def save_tip(payload, user):
    if not isinstance(payload, dict):
        raise ApiError(400, "El cuerpo debe ser un objeto JSON.")
    values = _validate_tip(payload)
    tip_id = payload.get("id")
    if tip_id:
        try:
            tip_id = str(uuid.UUID(tip_id))
        except (ValueError, TypeError, AttributeError):
            raise ApiError(400, "El identificador del consejo no es válido.")
    else:
        tip_id = str(uuid.uuid4())
    with connect() as connection, connection.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO musical_tips (id, title, category, content, exercise, published, created_by)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (id) DO UPDATE SET
                title = EXCLUDED.title,
                category = EXCLUDED.category,
                content = EXCLUDED.content,
                exercise = EXCLUDED.exercise,
                published = EXCLUDED.published,
                updated_at = now(),
                deleted_at = NULL
            RETURNING id, title, category, content, exercise, published, updated_at
            """,
            (
                tip_id,
                values["title"],
                values["category"],
                values["content"],
                values["exercise"],
                values["published"],
                user["id"],
            ),
        )
        row = cursor.fetchone()
        if row is None:
            raise ApiError(404, "El consejo no está disponible para editar.")
    return {
        "id": str(row[0]),
        "title": row[1],
        "category": row[2],
        "content": row[3],
        "exercise": row[4],
        "published": row[5],
        "updated_at": row[6].isoformat(),
    }


def delete_tip(tip_id):
    try:
        normalized_id = str(uuid.UUID(tip_id))
    except (ValueError, TypeError, AttributeError):
        raise ApiError(400, "El identificador del consejo no es válido.")
    with connect() as connection, connection.cursor() as cursor:
        cursor.execute(
            """
            UPDATE musical_tips
            SET deleted_at = now(), updated_at = now()
            WHERE id = %s AND deleted_at IS NULL
            RETURNING id
            """,
            (normalized_id,),
        )
        return cursor.fetchone() is not None
