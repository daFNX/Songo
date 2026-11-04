import unittest
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from psycopg import OperationalError

from backend.services.admin_metrics import get_admin_metrics
from backend.services.errors import ApiError


class AdminMetricsServiceTests(unittest.TestCase):
    def test_metrics_include_aggregate_counts_and_engine_configuration(self):
        generated_at = datetime.now(timezone.utc)
        connection = MagicMock()
        connection.__enter__.return_value = connection
        cursor = connection.cursor.return_value.__enter__.return_value
        cursor.fetchone.return_value = (10, 1, 3, 25, 2, generated_at)

        with patch("backend.services.admin_metrics.connect", return_value=connection):
            payload = get_admin_metrics(analyzer_enabled=True, analyzer_available=True)

        self.assertEqual(payload["users_total"], 10)
        self.assertEqual(payload["admins_total"], 1)
        self.assertEqual(payload["active_sessions"], 3)
        self.assertEqual(payload["saved_analyses_total"], 25)
        self.assertEqual(payload["saved_analyses_last_24h"], 2)
        self.assertEqual(payload["analyzer"]["status"], "operational")
        self.assertEqual(payload["generated_at"], generated_at.isoformat())
        self.assertIn("analysis_history", cursor.execute.call_args.args[0])

    def test_database_errors_are_reported_as_service_unavailable(self):
        with patch(
            "backend.services.admin_metrics.connect",
            side_effect=OperationalError("database unavailable"),
        ):
            with self.assertRaises(ApiError) as error:
                get_admin_metrics(analyzer_enabled=True, analyzer_available=True)

        self.assertEqual(error.exception.status, 503)
        self.assertIn("conexión", str(error.exception))


if __name__ == "__main__":
    unittest.main()
