import os
import unittest
from unittest.mock import patch

from backend.services import auth
from backend.services.errors import ApiError


class SessionTokenTests(unittest.TestCase):
    def test_signed_token_round_trip_and_tamper_detection(self):
        with patch.dict(os.environ, {"JWT_SECRET": "s" * 48, "JWT_ISSUER": "songo"}):
            token = auth._encode_token({
                "iss": "songo",
                "sub": "user-123",
                "jti": "session-456",
                "iat": 1900000000,
                "exp": 2100000000,
            })
            self.assertEqual(auth._decode_token(token)["sub"], "user-123")
            altered = token[:-1] + ("A" if token[-1] != "A" else "B")
            self.assertIsNone(auth._decode_token(altered))

    def test_expired_or_wrong_issuer_token_is_rejected(self):
        with patch.dict(os.environ, {"JWT_SECRET": "s" * 48, "JWT_ISSUER": "songo"}):
            expired = auth._encode_token({
                "iss": "songo", "sub": "user", "jti": "session",
                "iat": 1, "exp": 2,
            })
            wrong_issuer = auth._encode_token({
                "iss": "other", "sub": "user", "jti": "session",
                "iat": 1900000000, "exp": 2100000000,
            })
            self.assertIsNone(auth._decode_token(expired))
            self.assertIsNone(auth._decode_token(wrong_issuer))

    def test_token_signing_requires_a_long_random_secret(self):
        with patch.dict(os.environ, {"JWT_SECRET": "short"}):
            with self.assertRaises(ApiError) as context:
                auth._encode_token({"iss": "songo"})
        self.assertIn("no está configurada", str(context.exception))

    def test_password_policy_requires_twelve_to_128_characters(self):
        with self.assertRaises(ApiError):
            auth._validate_password("short")
        self.assertEqual(auth._validate_password("correct horse battery"), "correct horse battery")

    def test_vercel_production_uses_secure_host_cookie(self):
        with patch.dict(os.environ, {"VERCEL_ENV": "production"}, clear=True):
            self.assertEqual(auth.cookie_name(), "__Host-songo_session")
            cookie = auth._session_cookie("signed-token", 600)

        self.assertIn("; Secure", cookie)
        self.assertIn("HttpOnly; SameSite=Strict", cookie)


if __name__ == "__main__":
    unittest.main()
