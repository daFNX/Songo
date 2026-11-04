import os
import unittest
from unittest.mock import patch

import psycopg

from backend.services import database
from backend.services.errors import ApiError


class DatabaseConnectionTests(unittest.TestCase):
    def test_prefers_database_url_over_vercel_alias(self):
        connection = object()
        with patch.dict(
            os.environ,
            {
                "DATABASE_URL": "postgresql://primary/db",
                "POSTGRES_URL": "postgresql://fallback/db",
            },
            clear=True,
        ):
            with patch("backend.services.database.psycopg.connect", return_value=connection) as connect:
                self.assertIs(database.connect(), connection)
        self.assertEqual(connect.call_args.args[0], "postgresql://primary/db")

    def test_falls_back_to_vercel_components_only_for_malformed_url(self):
        connection = object()
        environment = {
            "POSTGRES_URL": "invalid connection string",
            "POSTGRES_HOST": "db.example.test",
            "POSTGRES_DATABASE": "songo",
            "POSTGRES_USER": "songo_user",
            "POSTGRES_PASSWORD": "private",
            "POSTGRES_PORT": "5432",
        }
        with patch.dict(os.environ, environment, clear=True):
            with patch(
                "backend.services.database.psycopg.connect",
                side_effect=[psycopg.ProgrammingError("invalid conninfo"), connection],
            ) as connect:
                self.assertIs(database.connect(), connection)

        self.assertEqual(connect.call_args.kwargs["host"], "db.example.test")
        self.assertEqual(connect.call_args.kwargs["dbname"], "songo")
        self.assertEqual(connect.call_args.kwargs["sslmode"], "require")
        self.assertEqual(connect.call_args.kwargs["password"], "private")

    def test_decodes_postgres_url_credentials_when_driver_rejects_raw_connection_info(self):
        connection = object()
        with patch.dict(
            os.environ,
            {"POSTGRES_URL": "postgresql://user:p%40ss%3Aword@db.example.test:6543/songo?sslmode=require"},
            clear=True,
        ):
            with patch(
                "backend.services.database.psycopg.connect",
                side_effect=[psycopg.ProgrammingError("invalid conninfo"), connection],
            ) as connect:
                self.assertIs(database.connect(), connection)

        self.assertEqual(connect.call_args.kwargs["host"], "db.example.test")
        self.assertEqual(connect.call_args.kwargs["port"], 6543)
        self.assertEqual(connect.call_args.kwargs["password"], "p@ss:word")

    def test_does_not_fallback_when_connection_string_is_valid_but_unreachable(self):
        environment = {
            "POSTGRES_URL": "postgresql://user:pass@db.example.test/songo",
            "POSTGRES_HOST": "db.example.test",
            "POSTGRES_DATABASE": "songo",
            "POSTGRES_USER": "user",
            "POSTGRES_PASSWORD": "pass",
        }
        with patch.dict(os.environ, environment, clear=True):
            with patch(
                "backend.services.database.psycopg.connect",
                side_effect=psycopg.OperationalError("unavailable"),
            ) as connect:
                with self.assertRaises(ApiError):
                    database.connect()

        connect.assert_called_once()

    def test_rejects_bad_timeout_without_connecting(self):
        with patch.dict(
            os.environ,
            {"POSTGRES_URL": "postgresql://user:pass@db.example.test/songo", "DATABASE_CONNECT_TIMEOUT": "bad"},
            clear=True,
        ):
            with patch("backend.services.database.psycopg.connect") as connect:
                with self.assertRaises(ApiError):
                    database.connect()
        connect.assert_not_called()


if __name__ == "__main__":
    unittest.main()
