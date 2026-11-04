import math
import os

from .database import connect
from .errors import ApiError


def _cosine(left, right):
    left_energy = math.sqrt(sum(value * value for value in left))
    right_energy = math.sqrt(sum(value * value for value in right))
    if not left_energy or not right_energy:
        return 0.0
    return sum(a * b for a, b in zip(left, right)) / (left_energy * right_energy)


def add_authorized_entry(payload, user):
    required = ("title", "artist", "source_url", "license_name", "authorization_reference", "audio_fingerprint", "chroma_profile")
    if any(not isinstance(payload.get(key), str) or not payload[key].strip() for key in required[:-1]):
        raise ApiError(400, "Faltan datos de la obra o su autorización.")
    if not payload["source_url"].startswith("https://"):
        raise ApiError(400, "La fuente del catálogo debe usar HTTPS.")
    if payload.get("authorized") is not True:
        raise ApiError(400, "Confirma que existe autorización documentada antes de agregar la obra.")
    profile = payload.get("chroma_profile")
    if (
        not isinstance(profile, list)
        or len(profile) != 12
        or any(not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0 for value in profile)
    ):
        raise ApiError(400, "La huella debe incluir un perfil cromático válido de 12 valores.")
    fingerprint = payload["audio_fingerprint"].strip().lower()
    if len(fingerprint) != 64 or any(character not in "0123456789abcdef" for character in fingerprint):
        raise ApiError(400, "La huella acústica no tiene un formato válido.")

    with connect() as connection, connection.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO authorized_catalog (
                title, artist, source_url, license_name, authorization_reference,
                audio_fingerprint, chroma_profile, authorized, created_by
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, true, %s)
            RETURNING id, created_at
            """,
            (
                payload["title"].strip()[:200],
                payload["artist"].strip()[:200],
                payload["source_url"].strip()[:2048],
                payload["license_name"].strip()[:200],
                payload["authorization_reference"].strip()[:500],
                fingerprint,
                profile,
                user["id"],
            ),
        )
        entry_id, created_at = cursor.fetchone()
    return {"id": str(entry_id), "created_at": created_at.isoformat()}


def find_similar(profile):
    try:
        max_results = int(os.environ.get("SONGO_CATALOG_MAX_RESULTS", "5"))
    except ValueError:
        raise ApiError(503, "SONGO_CATALOG_MAX_RESULTS debe ser un entero.")
    if not 1 <= max_results <= 20:
        raise ApiError(503, "SONGO_CATALOG_MAX_RESULTS debe estar entre 1 y 20.")
    with connect() as connection, connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT id, title, artist, source_url, license_name, chroma_profile
            FROM authorized_catalog
            WHERE authorized IS TRUE
            ORDER BY created_at DESC
            LIMIT 1000
            """
        )
        tracks = cursor.fetchall()
    matches = []
    for row in tracks:
        score = _cosine(profile, row[5])
        if score >= 0.88:
            matches.append({
                "id": str(row[0]),
                "title": row[1],
                "artist": row[2],
                "source_url": row[3],
                "license": row[4],
                "similarity_percent": round(score * 100, 1),
            })
    matches.sort(key=lambda item: item["similarity_percent"], reverse=True)
    return matches[:max_results]
