import io
import json
import unittest
from unittest.mock import MagicMock, patch

from psycopg.errors import UndefinedTable

from backend.gateway import application
from backend.services.errors import ApiError
from backend.services.tips import _validate_tip, delete_tip, list_tips


def request_api(method, path, body=b"", content_type="", extra=None):
    environ = {
        "REQUEST_METHOD": method,
        "PATH_INFO": path,
        "CONTENT_LENGTH": str(len(body)),
        "CONTENT_TYPE": content_type,
        "wsgi.input": io.BytesIO(body),
    }
    if extra:
        environ.update(extra)
    response = {}

    def start_response(status, headers):
        response["status"] = int(status.split(" ", 1)[0])
        response["headers"] = dict(headers)

    payload = b"".join(application(environ, start_response))
    return response["status"], response["headers"], json.loads(payload)


class TipsApiTests(unittest.TestCase):
    def test_public_tips_are_available_without_database(self):
        with patch("backend.gateway.configured", return_value=False):
            status, _, payload = request_api("GET", "/api/tips")

        self.assertEqual(status, 200)
        self.assertGreaterEqual(len(payload["items"]), 3)
        self.assertIn("exercise", payload["items"][0])

    def test_public_tips_fall_back_while_schema_migration_is_pending(self):
        with patch("backend.services.tips.configured", return_value=True):
            with patch("backend.services.tips.connect", side_effect=UndefinedTable("table missing")):
                status, _, payload = request_api("GET", "/api/tips")

        self.assertEqual(status, 200)
        self.assertGreaterEqual(len(payload["items"]), 3)

    def test_admin_get_reports_pending_schema_migration(self):
        with patch("backend.gateway.configured", return_value=True):
            with patch("backend.gateway.auth.current_user", return_value={"id": "admin-id", "role": "admin"}):
                with patch("backend.services.tips.configured", return_value=True):
                    with patch("backend.services.tips.connect", side_effect=UndefinedTable("table missing")):
                        status, _, payload = request_api("GET", "/api/tips")

        self.assertEqual(status, 503)
        self.assertIn("db/schema.sql", payload["error"])

    def test_admin_can_save_tip(self):
        tip = {
            "id": "30cda301-87b9-4ad0-98ba-3ce235c92201",
            "title": "Consejo de prueba",
            "category": "Producción",
            "content": "Una idea útil para probar una mezcla con atención.",
            "exercise": "Escucha una pista y ajusta una sola decisión de mezcla.",
            "published": True,
        }
        with patch("backend.gateway.auth.require_user", return_value={"id": "admin-id", "role": "admin"}):
            with patch("backend.gateway.tips.save_tip", return_value=tip) as save:
                status, _, payload = request_api(
                    "POST",
                    "/api/tips",
                    json.dumps({"action": "save", "item": tip}).encode(),
                    "application/json",
                )

        self.assertEqual(status, 200)
        self.assertEqual(payload["item"], tip)
        save.assert_called_once_with(tip, {"id": "admin-id", "role": "admin"})

    def test_tips_admin_mutations_require_admin_role(self):
        with patch(
            "backend.gateway.auth.require_user",
            side_effect=ApiError(403, "Esta operación requiere permisos de administración."),
        ):
            status, _, payload = request_api(
                "POST",
                "/api/tips",
                json.dumps({"action": "delete", "id": "30cda301-87b9-4ad0-98ba-3ce235c92201"}).encode(),
                "application/json",
            )

        self.assertEqual(status, 403)
        self.assertIn("administración", payload["error"])

    def test_tips_mutations_reject_cross_origin_requests(self):
        status, _, payload = request_api(
            "POST",
            "/api/tips",
            json.dumps({"action": "delete", "id": "30cda301-87b9-4ad0-98ba-3ce235c92201"}).encode(),
            "application/json",
            {"HTTP_HOST": "songo.example", "HTTP_ORIGIN": "https://attacker.example"},
        )

        self.assertEqual(status, 403)
        self.assertIn("origen", payload["error"])

    def test_tip_deletion_is_a_soft_delete(self):
        tip_id = "30cda301-87b9-4ad0-98ba-3ce235c92201"
        connection = MagicMock()
        connection.__enter__.return_value = connection
        cursor = connection.cursor.return_value.__enter__.return_value
        cursor.fetchone.return_value = (tip_id,)
        with patch("backend.services.tips.connect", return_value=connection):
            self.assertTrue(delete_tip(tip_id))

        statement = cursor.execute.call_args.args[0]
        self.assertIn("SET deleted_at = now()", statement)
        self.assertIn("UPDATE musical_tips", statement)

    def test_empty_configured_tips_table_does_not_restore_archived_entries(self):
        connection = MagicMock()
        connection.__enter__.return_value = connection
        cursor = connection.cursor.return_value.__enter__.return_value
        cursor.fetchall.return_value = []
        cursor.fetchone.return_value = (True,)
        with patch("backend.services.tips.configured", return_value=True):
            with patch("backend.services.tips.connect", return_value=connection):
                self.assertEqual(list_tips(), [])

    def test_tips_method_allow_header(self):
        status, headers, _ = request_api("DELETE", "/api/tips")

        self.assertEqual(status, 405)
        self.assertEqual(headers["Allow"], "GET, POST")

    def test_tip_content_is_trimmed_and_bounded(self):
        tip = _validate_tip({
            "title": "  Un consejo  ",
            "category": " Armonía ",
            "content": " Una explicación útil y suficientemente clara. ",
            "exercise": " Prueba este ejercicio durante tu próxima sesión. ",
            "published": False,
        })

        self.assertEqual(tip["title"], "Un consejo")
        self.assertEqual(tip["category"], "Armonía")
        self.assertFalse(tip["published"])

    def test_tip_content_rejects_invalid_length(self):
        with self.assertRaises(ApiError):
            _validate_tip({
                "title": "ok",
                "category": "Armonía",
                "content": "Texto suficientemente largo.",
                "exercise": "Ejercicio suficientemente largo.",
            })


if __name__ == "__main__":
    unittest.main()
