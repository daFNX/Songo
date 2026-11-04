import os
import unittest
from unittest.mock import patch

from scripts.bootstrap_admin import promote_first_admin


class FakeCursor:
    def __init__(self, has_admin=False, account_email="musico@example.com"):
        self.has_admin = has_admin
        self.account_email = account_email
        self.query = ""
        self.parameters = None

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def execute(self, query, parameters=None):
        self.query = query
        self.parameters = parameters

    def fetchone(self):
        if "SELECT EXISTS" in self.query:
            return (self.has_admin,)
        if "RETURNING email" in self.query and self.account_email:
            return (self.account_email,)
        return None


class FakeConnection:
    def __init__(self, cursor):
        self.fake_cursor = cursor

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def cursor(self):
        return self.fake_cursor


class FirstAdminBootstrapTests(unittest.TestCase):
    def test_requires_exact_confirmation_before_database_access(self):
        with patch.dict(os.environ, {"DATABASE_URL": "postgresql://test"}):
            with patch("scripts.bootstrap_admin.psycopg.connect") as connect:
                with self.assertRaisesRegex(ValueError, "confirmación no coincide"):
                    promote_first_admin("Musico@example.com", "PROMOTE wrong@example.com")
        connect.assert_not_called()

    def test_promotes_existing_user_only_when_no_admin_exists(self):
        cursor = FakeCursor()
        connection = FakeConnection(cursor)
        with patch.dict(os.environ, {"DATABASE_URL": "postgresql://test"}):
            with patch("scripts.bootstrap_admin.psycopg.connect", return_value=connection) as connect:
                result = promote_first_admin(
                    "Musico@example.com",
                    "PROMOTE musico@example.com",
                )

        self.assertEqual(result, "musico@example.com")
        self.assertEqual(cursor.parameters, ("musico@example.com",))
        connect.assert_called_once()

    def test_refuses_to_promote_when_an_admin_already_exists(self):
        cursor = FakeCursor(has_admin=True)
        connection = FakeConnection(cursor)
        with patch.dict(os.environ, {"DATABASE_URL": "postgresql://test"}):
            with patch("scripts.bootstrap_admin.psycopg.connect", return_value=connection):
                with self.assertRaisesRegex(RuntimeError, "Ya existe un administrador"):
                    promote_first_admin("musico@example.com", "PROMOTE musico@example.com")

    def test_accepts_vercel_postgres_url_alias(self):
        cursor = FakeCursor()
        connection = FakeConnection(cursor)
        with patch.dict(os.environ, {"POSTGRES_URL": "postgresql://test"}, clear=True):
            with patch("scripts.bootstrap_admin.psycopg.connect", return_value=connection) as connect:
                promote_first_admin("musico@example.com", "PROMOTE musico@example.com")

        self.assertEqual(connect.call_args.args[0], "postgresql://test")


if __name__ == "__main__":
    unittest.main()
