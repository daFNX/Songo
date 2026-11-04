import argparse
import os
import re
import sys

import psycopg
from dotenv import load_dotenv

EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
LOCK_NAMESPACE = 730014
LOCK_ID = 1


def promote_first_admin(email, confirmation):
    normalized_email = email.strip().lower()
    if len(normalized_email) > 254 or not EMAIL_PATTERN.fullmatch(normalized_email):
        raise ValueError("Indica un correo válido.")
    if confirmation != f"PROMOTE {normalized_email}":
        raise ValueError("La confirmación no coincide; no se modificó ninguna cuenta.")

    connection_string = os.environ.get("DATABASE_URL") or os.environ.get("POSTGRES_URL")
    if not connection_string:
        raise RuntimeError("Configura DATABASE_URL o POSTGRES_URL en el entorno.")

    with psycopg.connect(
        connection_string,
        connect_timeout=int(os.environ.get("DATABASE_CONNECT_TIMEOUT", "5")),
    ) as connection:
        with connection.cursor() as cursor:
            cursor.execute("SELECT pg_advisory_xact_lock(%s, %s)", (LOCK_NAMESPACE, LOCK_ID))
            cursor.execute("SELECT EXISTS (SELECT 1 FROM users WHERE role = 'admin')")
            if cursor.fetchone()[0]:
                raise RuntimeError("Ya existe un administrador; el bootstrap inicial está cerrado.")

            cursor.execute(
                """
                UPDATE users
                SET role = 'admin', updated_at = now()
                WHERE email = %s
                RETURNING email
                """,
                (normalized_email,),
            )
            row = cursor.fetchone()
            if row is None:
                raise RuntimeError("No existe una cuenta con ese correo; no se creó ningún usuario.")
            return row[0]


def main():
    load_dotenv()
    parser = argparse.ArgumentParser(
        description="Promueve una cuenta existente como primer administrador, una sola vez."
    )
    parser.add_argument("email", help="Correo de la cuenta que ya se registró en Songo")
    args = parser.parse_args()
    email = args.email.strip().lower()
    print(f"Se intentará promover la cuenta existente: {email}")
    confirmation = input(f"Escribe exactamente PROMOTE {email} para continuar: ")
    try:
        promoted_email = promote_first_admin(email, confirmation)
    except (ValueError, RuntimeError, psycopg.Error) as error:
        print(f"No se creó el administrador: {error}", file=sys.stderr)
        return 1
    print(f"Primer administrador configurado: {promoted_email}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
