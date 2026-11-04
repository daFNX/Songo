import io
import json
import math
import os
import struct
import unittest
import wave
from unittest.mock import MagicMock, patch

from api.analyze import application
from backend.gateway import _enforce_rate_limit, _MEMORY_RATE_LIMITS
from backend.services.errors import ApiError
from backend.services.tempo import AnalysisError, analyze_wav


def make_wav(bpm=120, duration=8, sample_rate=8000):
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(sample_rate)
        samples = bytearray()
        beat_interval = 60 / bpm
        for index in range(duration * sample_rate):
            time = index / sample_rate
            phase = time % beat_interval
            amplitude = 0.8 * math.exp(-phase * 35) if phase < 0.08 else 0.015
            value = int(32767 * amplitude * math.sin(2 * math.pi * 440 * time))
            samples.extend(struct.pack("<h", value))
        audio.writeframes(samples)
    return buffer.getvalue()


def request_api(method, path, body=b"", content_type=""):
    environ = {
        "REQUEST_METHOD": method,
        "PATH_INFO": path,
        "CONTENT_LENGTH": str(len(body)),
        "CONTENT_TYPE": content_type,
        "wsgi.input": io.BytesIO(body),
    }
    response = {}

    def start_response(status, headers):
        response["status"] = int(status.split(" ", 1)[0])
        response["headers"] = dict(headers)

    with patch.dict(os.environ, {"APP_ALLOWED_ORIGINS": "", "APP_BASE_URL": ""}):
        payload = b"".join(application(environ, start_response))
    return response["status"], response["headers"], json.loads(payload)


class AnalyzeWavTests(unittest.TestCase):
    def test_in_memory_rate_limit_blocks_requests_after_limit(self):
        _MEMORY_RATE_LIMITS.clear()
        environ = {"REMOTE_ADDR": "192.0.2.10"}
        with patch.dict(os.environ, {}, clear=True):
            _enforce_rate_limit(environ, "test", limit=1)
            with self.assertRaises(ApiError) as error:
                _enforce_rate_limit(environ, "test", limit=1)

        self.assertEqual(error.exception.status, 429)

    def test_rate_limit_scopes_do_not_share_counters(self):
        _MEMORY_RATE_LIMITS.clear()
        environ = {"REMOTE_ADDR": "192.0.2.11"}
        with patch.dict(os.environ, {}, clear=True):
            _enforce_rate_limit(environ, "analysis", limit=1)
            _enforce_rate_limit(environ, "login", limit=1)

    def test_persistent_rate_limit_uses_database_counter(self):
        connection = MagicMock()
        connection.__enter__.return_value = connection
        cursor_context = connection.cursor.return_value
        cursor = cursor_context.__enter__.return_value
        cursor.fetchone.return_value = (1, False)
        with patch("backend.gateway.configured", return_value=True):
            with patch("backend.gateway.connect", return_value=connection):
                with patch.dict(os.environ, {"APP_RATE_LIMIT_SECRET": "k" * 48}, clear=True):
                    _enforce_rate_limit({"REMOTE_ADDR": "192.0.2.12"}, "analysis", limit=20)

        statement, parameters = cursor.execute.call_args.args
        self.assertIn("INSERT INTO auth_rate_limits", statement)
        self.assertEqual(parameters[1:], (900, 900, 900, 20, 900))

    def test_history_delete_is_owner_authenticated_and_reversible(self):
        record_id = "3a37d640-3c88-498e-bfde-064cd51fbc65"
        with patch("backend.gateway.auth.require_user", return_value={"id": "owner-id"}):
            with patch("backend.gateway._enabled_feature_ids", return_value={"library"}):
                with patch("backend.gateway._update_history_visibility", return_value=True) as update:
                    response = request_api(
                        "POST",
                        "/api/history",
                        json.dumps({"action": "delete", "id": record_id}).encode(),
                        "application/json",
                    )

        self.assertEqual(response[0], 200)
        update.assert_called_once_with(record_id, {"id": "owner-id"}, restore=False)

    def test_history_restore_requires_valid_identifier(self):
        with patch("backend.gateway.auth.require_user", return_value={"id": "owner-id"}):
            with patch("backend.gateway._enabled_feature_ids", return_value={"library"}):
                response = request_api(
                    "POST",
                    "/api/history",
                    json.dumps({"action": "restore", "id": "not-a-uuid"}).encode(),
                    "application/json",
                )

        self.assertEqual(response[0], 400)

    def test_history_write_endpoint_rejects_other_http_methods(self):
        response = request_api("DELETE", "/api/history")

        self.assertEqual(response[0], 405)
        self.assertEqual(response[1]["Allow"], "GET, POST")

    def test_estimates_synthetic_120_bpm(self):
        result = analyze_wav(make_wav())
        self.assertEqual(result["bpm"], 120)

    def test_estimates_synthetic_90_bpm(self):
        result = analyze_wav(make_wav(bpm=90))
        self.assertEqual(result["bpm"], 90)

    def test_rejects_non_wav_input(self):
        with self.assertRaises(AnalysisError):
            analyze_wav(b"not a wav file")

    def test_rejects_silence(self):
        buffer = io.BytesIO()
        with wave.open(buffer, "wb") as audio:
            audio.setnchannels(1)
            audio.setsampwidth(2)
            audio.setframerate(8000)
            audio.writeframes(bytes(8000 * 4))
        with self.assertRaises(AnalysisError):
            analyze_wav(buffer.getvalue())

    def test_rejects_oversized_input(self):
        with self.assertRaises(AnalysisError) as error:
            analyze_wav(bytes(4 * 1024 * 1024 + 1))
        self.assertEqual(error.exception.status, 413)

    def test_wsgi_health_route(self):
        status, headers, payload = request_api("GET", "/api/health")
        self.assertEqual(status, 200)
        self.assertEqual(payload, {"status": "ok"})
        self.assertEqual(headers["Cache-Control"], "no-store")

    def test_wsgi_feature_manifest_route(self):
        status, _, payload = request_api("GET", "/api/features")
        self.assertEqual(status, 200)
        self.assertEqual(payload["version"], 1)
        self.assertEqual(len(payload["features"]), 5)

    def test_wsgi_feature_manifest_rejects_non_get_requests(self):
        status, headers, payload = request_api("POST", "/api/features")
        self.assertEqual(status, 405)
        self.assertEqual(headers["Allow"], "GET")
        self.assertEqual(payload["error"], "Método no permitido.")

    def test_wsgi_analyze_route_returns_bpm(self):
        status, _, payload = request_api("POST", "/api/analyze", make_wav(), "audio/wav")
        self.assertEqual(status, 200)
        self.assertEqual(payload["bpm"], 120)

    def test_wsgi_rejects_unsupported_content_type(self):
        status, _, payload = request_api("POST", "/api/analyze", b"invalid", "text/plain")
        self.assertEqual(status, 415)
        self.assertIn("WAV", payload["error"])

    def test_wsgi_respects_disabled_bpm_feature(self):
        with patch.dict(os.environ, {"SONGO_ENABLED_FEATURES": "recording"}):
            status, _, payload = request_api("POST", "/api/analyze", make_wav(), "audio/wav")

        self.assertEqual(status, 503)
        self.assertIn("desactivado", payload["error"])

    def test_wsgi_rejects_oversized_request_before_reading_body(self):
        environ = {
            "REQUEST_METHOD": "POST",
            "PATH_INFO": "/api/analyze",
            "CONTENT_LENGTH": str(4 * 1024 * 1024 + 1),
            "CONTENT_TYPE": "audio/wav",
            "wsgi.input": io.BytesIO(b""),
        }
        response = {}

        def start_response(status, headers):
            response["status"] = int(status.split(" ", 1)[0])

        payload = b"".join(application(environ, start_response))
        self.assertEqual(response["status"], 413)
        self.assertIn("4 MB", json.loads(payload)["error"])

    def test_wsgi_rejects_cross_origin_analysis(self):
        wav = make_wav()
        environ = {
            "REQUEST_METHOD": "POST",
            "PATH_INFO": "/api/analyze",
            "CONTENT_LENGTH": str(len(wav)),
            "CONTENT_TYPE": "audio/wav",
            "HTTP_HOST": "songo.example",
            "HTTP_ORIGIN": "https://attacker.example",
            "wsgi.input": io.BytesIO(wav),
        }
        response = {}

        def start_response(status, headers):
            response["status"] = int(status.split(" ", 1)[0])

        with patch.dict(os.environ, {"APP_ALLOWED_ORIGINS": "", "APP_BASE_URL": ""}):
            with patch("backend.gateway.auth.current_user", return_value={"id": "test-user"}):
                payload = b"".join(application(environ, start_response))
        self.assertEqual(response["status"], 403)
        self.assertEqual(json.loads(payload)["error"], "El origen de la solicitud no está permitido.")


if __name__ == "__main__":
    unittest.main()
