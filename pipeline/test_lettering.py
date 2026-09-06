import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from pipeline.lettering import LetteringError, render_lettering


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class LetteringTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def _plan(self, purpose="CALIBRATION_PLACEHOLDER", base_image=None):
        path = self.root / "plan.json"
        path.write_text(
            json.dumps({
                "schema_version": "1.0",
                "plan_id": "lettering-test",
                "purpose": purpose,
                "canvas": {
                    "width": 240,
                    "height": 120,
                    "background_rgba": [255, 255, 255, 255],
                },
                "base_image": base_image,
                "text_layers": [{
                    "layer_id": "title",
                    "z": 0,
                    "lines": ["TITLE", "SECOND LINE"],
                    "x": 120,
                    "y": 20,
                    "anchor": "CENTER",
                    "font": {
                        "mode": "PIL_DEFAULT",
                        "size": 24,
                    },
                    "fill_rgba": [0, 0, 0, 255],
                    "stroke_width": 0,
                    "line_spacing": 4,
                    "box": {
                        "type": "RECT",
                        "padding": [8, 6, 8, 6],
                        "fill_rgba": [245, 245, 240, 255],
                        "outline_rgba": [80, 80, 80, 255],
                        "outline_width": 1,
                    },
                }],
            }),
            encoding="utf-8",
        )
        return path

    def _render(self, plan, suffix=""):
        output = self.root / f"out{suffix}.png"
        receipt = self.root / f"receipt{suffix}.json"
        return render_lettering(self.root, plan, output, receipt), output, receipt

    def test_calibration_placeholder_renders_with_receipt(self):
        result, output, receipt = self._render(self._plan())
        self.assertTrue(output.is_file())
        self.assertTrue(receipt.is_file())
        self.assertEqual(result["purpose"], "CALIBRATION_PLACEHOLDER")
        self.assertEqual(result["text_layers"][0]["layer_id"], "title")

    def test_same_plan_renders_same_pixels(self):
        plan = self._plan()
        first, _, _ = self._render(plan, "1")
        second, _, _ = self._render(plan, "2")
        self.assertEqual(first["output_sha256"], second["output_sha256"])

    def test_default_font_is_forbidden_in_production(self):
        with self.assertRaisesRegex(LetteringError, "calibration-placeholder only"):
            self._render(self._plan(purpose="PRODUCTION"))

    def test_base_image_hash_is_verified(self):
        base = self.root / "base.png"
        Image.new("RGBA", (240, 120), (10, 20, 30, 255)).save(base)
        spec = {
            "path": "base.png",
            "sha256": "0" * 64,
        }
        with self.assertRaisesRegex(LetteringError, "base image SHA-256 mismatch"):
            self._render(self._plan(base_image=spec))

    def test_project_font_path_is_hash_bound(self):
        data = json.loads(self._plan(purpose="PRODUCTION").read_text(encoding="utf-8"))
        data["text_layers"][0]["font"] = {
            "mode": "PROJECT_FILE",
            "size": 24,
            "path": "fonts/missing.ttf",
            "sha256": "0" * 64,
        }
        path = self.root / "project-font-plan.json"
        path.write_text(json.dumps(data), encoding="utf-8")
        with self.assertRaisesRegex(LetteringError, "missing font bytes"):
            self._render(path)


if __name__ == "__main__":
    unittest.main()
