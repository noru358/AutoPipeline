#!/usr/bin/env python3
"""Generic deterministic compositor for AutoPipeline toon projects.

The child project owns creative asset categories and scene semantics.
This program owns only approved-byte verification and deterministic placement.
Meaning-bearing lettering/UI remains a later editable layer.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

try:
    from PIL import Image, ImageOps
except ImportError as exc:  # pragma: no cover
    raise SystemExit("Pillow is required for composition: pip install pillow") from exc


class CompositionError(RuntimeError):
    pass


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_json(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise CompositionError(f"missing file: {path}") from exc
    except json.JSONDecodeError as exc:
        raise CompositionError(f"invalid JSON: {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise CompositionError(f"JSON root must be an object: {path}")
    return value


def approved_assets(project_root: Path, registry_path: Path) -> dict[str, dict]:
    registry = load_json(registry_path)
    if registry.get("schema_version") != "1.0":
        raise CompositionError("unsupported registry schema_version")
    result: dict[str, dict] = {}
    for item in registry.get("assets", []):
        asset_id = item.get("asset_id")
        if not asset_id or asset_id in result:
            raise CompositionError(f"missing or duplicate asset_id: {asset_id!r}")
        if item.get("status") != "APPROVED":
            continue
        path = (project_root / item["path"]).resolve()
        try:
            path.relative_to(project_root.resolve())
        except ValueError as exc:
            raise CompositionError(f"{asset_id}: asset path escapes project root") from exc
        if not path.is_file():
            raise CompositionError(f"{asset_id}: missing asset bytes: {item['path']}")
        if sha256_file(path) != item.get("sha256"):
            raise CompositionError(f"{asset_id}: SHA-256 mismatch")
        with Image.open(path) as image:
            if image.width != item.get("width") or image.height != item.get("height"):
                raise CompositionError(f"{asset_id}: dimensions do not match registry")
        result[asset_id] = {**item, "_path": path}
    return result


def transform(image: Image.Image, layer: dict) -> Image.Image:
    out = image.convert("RGBA")
    scale = float(layer["scale"])
    if scale != 1:
        out = out.resize(
            (max(1, round(out.width * scale)), max(1, round(out.height * scale))),
            Image.Resampling.LANCZOS,
        )
    if layer.get("flip_x"):
        out = ImageOps.mirror(out)
    rotation = float(layer.get("rotation_deg", 0))
    if rotation:
        out = out.rotate(rotation, resample=Image.Resampling.BICUBIC, expand=True)
    opacity = float(layer.get("opacity", 1))
    if opacity < 1:
        alpha = out.getchannel("A").point(lambda value: round(value * opacity))
        out.putalpha(alpha)
    return out


def compose(project_root: Path, registry_path: Path, scene_path: Path, output_path: Path, receipt_path: Path) -> dict:
    assets = approved_assets(project_root, registry_path)
    scene = load_json(scene_path)
    if scene.get("schema_version") != "1.0":
        raise CompositionError("unsupported scene schema_version")

    canvas = scene.get("canvas", {})
    width, height = int(canvas["width"]), int(canvas["height"])
    rgba = tuple(int(value) for value in canvas["background_rgba"])
    base = Image.new("RGBA", (width, height), rgba)

    used = []
    indexed_layers = list(enumerate(scene.get("layers", [])))
    for original_index, layer in sorted(indexed_layers, key=lambda pair: (int(pair[1]["z"]), pair[0])):
        asset_id = layer["asset_id"]
        asset = assets.get(asset_id)
        if asset is None:
            raise CompositionError(f"{asset_id}: not an APPROVED registered asset")
        x, y = int(layer["x"]), int(layer["y"])
        if x < 0 or y < 0:
            raise CompositionError("composition v1 requires non-negative x/y")
        with Image.open(asset["_path"]) as raw:
            rendered = transform(raw, layer)
        base.alpha_composite(rendered, dest=(x, y))
        used.append({
            "asset_id": asset_id,
            "asset_sha256": asset["sha256"],
            "layer_index": original_index,
            "z": int(layer["z"]),
        })

    output_path.parent.mkdir(parents=True, exist_ok=True)
    base.convert("RGB").save(output_path, "PNG", optimize=False, compress_level=9)
    receipt = {
        "schema_version": "1.0",
        "scene_id": scene["scene_id"],
        "scene_sha256": sha256_file(scene_path),
        "registry_sha256": sha256_file(registry_path),
        "output_path": str(output_path),
        "output_sha256": sha256_file(output_path),
        "used_assets": used,
    }
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    receipt_path.write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", required=True)
    parser.add_argument("--registry", default="assets/production/registry.json")
    parser.add_argument("--scene", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--receipt")
    args = parser.parse_args()

    root = Path(args.project_root).resolve()
    registry = (root / args.registry).resolve()
    scene = Path(args.scene).resolve()
    output = Path(args.output).resolve()
    receipt = Path(args.receipt).resolve() if args.receipt else Path(str(output) + ".composition.json")

    try:
        result = compose(root, registry, scene, output, receipt)
    except (CompositionError, KeyError, TypeError, ValueError) as exc:
        print(f"COMPOSITION_FAIL: {exc}")
        return 2
    print(f"COMPOSITION_PASS sha256={result['output_sha256']}")
    print(f"receipt={receipt}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
