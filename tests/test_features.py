import json
import os
import unittest
from unittest.mock import patch

from api.features import application, enabled_features


def request_api(method="GET", path="/api/features"):
    environ = {
        "REQUEST_METHOD": method,
        "PATH_INFO": path,
    }
    response = {}

    def start_response(status, headers):
        response["status"] = int(status.split(" ", 1)[0])
        response["headers"] = dict(headers)

    body = b"".join(application(environ, start_response))
    response["body"] = json.loads(body)
    return response


class FeatureConfigTests(unittest.TestCase):
    def test_defaults_enable_only_implemented_audio_tools(self):
        with patch.dict(os.environ, {}, clear=True):
            features = enabled_features()

        self.assertEqual(
            {feature["id"] for feature in features if feature["enabled"]},
            {"bpm", "recording"},
        )
        self.assertTrue(next(feature for feature in features if feature["id"] == "chords")["requiresAuth"])

    def test_environment_can_toggle_known_feature_flags(self):
        with patch.dict(os.environ, {"SONGO_ENABLED_FEATURES": "bpm,chords"}):
            with patch.dict(os.environ, {"DATABASE_URL": "postgresql://test", "JWT_SECRET": "x" * 48}):
                features = enabled_features()

        self.assertEqual(
            {feature["id"] for feature in features if feature["enabled"]},
            {"bpm", "chords"},
        )

    def test_unknown_feature_flag_is_rejected(self):
        with patch.dict(os.environ, {"SONGO_ENABLED_FEATURES": "bpm,unknown"}):
            from backend.services.errors import ApiError
            with self.assertRaises(ApiError):
                enabled_features()

    def test_wsgi_returns_feature_manifest_without_caching(self):
        with patch.dict(os.environ, {}, clear=True):
            response = request_api()

        self.assertEqual(response["status"], 200)
        self.assertEqual(response["body"]["version"], 1)
        self.assertEqual(response["headers"]["Cache-Control"], "no-store")
        self.assertEqual(len(response["body"]["features"]), 5)

    def test_auth_session_is_explicitly_unconfigured_without_database(self):
        with patch.dict(os.environ, {}, clear=True):
            response = request_api(path="/api/auth/me")

        self.assertEqual(response["status"], 200)
        self.assertEqual(response["body"], {"user": None, "auth_configured": False})

    def test_wsgi_rejects_non_get_requests(self):
        response = request_api(method="POST")

        self.assertEqual(response["status"], 405)
        self.assertEqual(response["headers"]["Allow"], "GET")

    def test_wsgi_rejects_unknown_paths(self):
        response = request_api(path="/unknown")

        self.assertEqual(response["status"], 404)
        self.assertEqual(response["body"], {"error": "Ruta no encontrada."})

    def test_wsgi_hides_invalid_feature_configuration_details(self):
        with patch.dict(os.environ, {"SONGO_ENABLED_FEATURES": "bpm,unknown"}):
            response = request_api()

        self.assertEqual(response["status"], 500)
        self.assertIn("identificadores desconocidos", response["body"]["error"])


if __name__ == "__main__":
    unittest.main()
