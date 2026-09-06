import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from pipeline.compositor import CompositionError, compose


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class CompositorTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        (self.root / "assets").mkdir()
        self.asset_path = self.root / "assets" / "red.png"
        Image.new("RGBA", (20, 20), (255, 0, 0, 255)).save(self.asset_path)

        self.registry = self.root / "registry.json"
        self.registry.write_text(
            json.dumps({
                "schema_version": "1.0",
                "assets": [{
                    "asset_id": "approved:red",
                    "status": "APPROVED",
                    "path": "assets/red.png",
                    "sha256": sha256_file(self.asset_path),
                    "width": 20,
                    "height": 20,
                }],
            }),
            encoding="utf-8",
        )

    def tearDown(self):
        self.temp.cleanup()

    def _scene(self, x=0, y=0, asset_id="approved:red"):
        path = self.root / "scene.json"
        path.write_text(
            json.dumps({
                "schema_version": "1.0",
                "scene_id": "scene-test",
                "canvas": {
                    "width": 10,
                    "height": 10,
                    "background_rgba": [255, 255, 255, 255],
                },
                "layers": [{
                    "asset_id": asset_id,
                    "x": x,
                    "y": y,
                    "z": 0,
                    "scale": 1,
                    "flip_x": False,
                    "rotation_deg": 0,
                    "opacity": 1,
                }],
            }),
            encoding="utf-8",
        )
        return path

    def _compose(self, scene):
        output = self.root / "out.png"
        receipt = self.root / "receipt.json"
        return compose(self.root, self.registry, scene, output, receipt), output, receipt

    def test_negative_xy_clip_is_allowed(self):
        result, output, receipt = self._compose(self._scene(x=-5, y=-5))
        self.assertTrue(output.is_file())
        self.assertTrue(receipt.is_file())
        with Image.open(output) as image:
            self.assertEqual(image.getpixel((0, 0)), (255, 0, 0))
            self.assertEqual(image.getpixel((9, 9)), (255, 0, 0))
        self.assertEqual(result["used_assets"][0]["asset_id"], "approved:red")

    def test_right_bottom_overflow_is_allowed(self):
        _, output, _ = self._compose(self._scene(x=5, y=5))
        with Image.open(output) as image:
            self.assertEqual(image.getpixel((5, 5)), (255, 0, 0))
            self.assertEqual(image.getpixel((0, 0)), (255, 255, 255))

    def test_hash_mismatch_fails_closed(self):
        data = json.loads(self.registry.read_text(encoding="utf-8"))
        data["assets"][0]["sha256"] = "0" * 64
        self.registry.write_text(json.dumps(data), encoding="utf-8")
        with self.assertRaisesRegex(CompositionError, "SHA-256 mismatch"):
            self._compose(self._scene())

    def test_rejected_asset_cannot_compose(self):
        data = json.loads(self.registry.read_text(encoding="utf-8"))
        data["assets"][0]["status"] = "REJECTED"
        self.registry.write_text(json.dumps(data), encoding="utf-8")
        with self.assertRaisesRegex(CompositionError, "not an APPROVED registered asset"):
            self._compose(self._scene())

    def test_asset_id_is_unique_across_all_statuses(self):
        data = json.loads(self.registry.read_text(encoding="utf-8"))
        data["assets"].append({
            **data["assets"][0],
            "status": "RETIRED",
        })
        self.registry.write_text(json.dumps(data), encoding="utf-8")
        with self.assertRaisesRegex(CompositionError, "duplicate asset_id"):
            self._compose(self._scene())


if __name__ == "__main__":
    unittest.main()
