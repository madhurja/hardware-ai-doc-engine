import unittest

from fastapi.testclient import TestClient

from app import app


class DashboardTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(app)

    def test_dashboard_page_loads(self) -> None:
        response = self.client.get("/")

        self.assertEqual(response.status_code, 200)
        self.assertIn("Hardware AI Documentation Engine", response.text)
        self.assertIn("Generate PDFs", response.text)

    def test_status_endpoint_returns_workspace_summary(self) -> None:
        response = self.client.get("/api/status")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertIn("metadata", payload)
        self.assertIn("analysis", payload)
        self.assertIn("outputs", payload)


if __name__ == "__main__":
    unittest.main()

