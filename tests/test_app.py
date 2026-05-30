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
        self.assertIn("manifest.webmanifest", response.text)
        self.assertIn('id="app"', response.text)

    def test_pwa_assets_load(self) -> None:
        manifest = self.client.get("/manifest.webmanifest")
        service_worker = self.client.get("/service-worker.js")

        self.assertEqual(manifest.status_code, 200)
        self.assertIn("Hardware AI Documentation Engine", manifest.text)
        self.assertEqual(service_worker.status_code, 200)
        self.assertIn("CACHE_NAME", service_worker.text)

    def test_status_endpoint_returns_workspace_summary(self) -> None:
        response = self.client.get("/api/status")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertIn("metadata", payload)
        self.assertIn("analysis", payload)
        self.assertIn("outputs", payload)
        self.assertIn("runtime", payload)
        self.assertIn("local_url", payload["runtime"])


if __name__ == "__main__":
    unittest.main()
