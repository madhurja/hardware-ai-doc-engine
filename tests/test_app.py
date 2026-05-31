import unittest
import tempfile
from pathlib import Path

from fastapi.testclient import TestClient

import app as app_module
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
        self.assertIn("skill_review_gates", payload["analysis"])
        self.assertIn("adaptive_improvement", payload)
        self.assertIn("runs_total", payload["adaptive_improvement"])
        self.assertIn("quality_audit", payload)
        self.assertIn("release_status", payload["quality_audit"])
        self.assertIn("plugins", payload)
        self.assertIn("summary", payload["plugins"])

    def test_plugins_endpoint_returns_catalog(self) -> None:
        response = self.client.get("/api/plugins")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertIn("plugins", payload)
        self.assertIn("research_pack", payload)
        self.assertGreaterEqual(payload["summary"]["total"], 5)

    def test_upload_rejects_unsupported_file_type(self) -> None:
        response = self.client.post(
            "/api/upload",
            data={"target": "code"},
            files=[("files", ("malware.exe", b"nope", "application/octet-stream"))],
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("Unsupported file type", response.json()["detail"])

    def test_upload_streams_and_preserves_duplicate_names(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            original_targets = app_module.UPLOAD_TARGETS.copy()
            try:
                app_module.UPLOAD_TARGETS["code"] = Path(temp_dir)
                response = self.client.post(
                    "/api/upload",
                    data={"target": "code"},
                    files=[
                        ("files", ("main.c", b"#define LED GPIO_PIN_13", "text/plain")),
                        ("files", ("main.c", b"#define RELAY GPIO_PIN_5", "text/plain")),
                    ],
                )
            finally:
                app_module.UPLOAD_TARGETS.clear()
                app_module.UPLOAD_TARGETS.update(original_targets)

            self.assertEqual(response.status_code, 200)
            saved_names = [item["name"] for item in response.json()["saved"]]
            self.assertEqual(saved_names, ["main.c", "main_2.c"])


if __name__ == "__main__":
    unittest.main()
