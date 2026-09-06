#!/usr/bin/env python3
"""Deterministic editable-text renderer for AutoPipeline toon projects.

Children own copy, typography choices and placement semantics. The parent owns
hash verification, deterministic rasterization and a receipt that binds the
editable JSON plan to the rendered preview.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError as exc:  # pragma: no cover
    raise SystemExit("Pillow is required for lettering: pip install pillow") from exc


class LetteringError(RuntimeError):
    pass


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_json(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise LetteringError(f"missing file: {path}") from exc
    except json.JSONDecodeError as exc:
        raise LetteringError(f"invalid JSON: {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise LetteringError(f"JSON root must be an object: {path}")
    return value


def _inside(root: Path, relative: str, label: str) -> Path:
    path = (root / relative).resolve()
    try:
        path.relative_to(root.resolve())
    except ValueError as exc:
        raise LetteringError(f"{label} path escapes project root") from exc
    return path


def _rgba(value, label: str) -> tuple[int, int, int, int]:
    if not isinstance(value, list) or len(value) != 4:
        raise LetteringError(f"{label} must be RGBA[4]")
    rgba = tuple(int(v) for v in value)
    if any(v < 0 or v > 255 for v in rgba):
        raise LetteringError(f"{label} values must be 0..255")
    return rgba


def _font(project_root: Path, plan: dict, layer: dict):
    spec = layer.get("font")
    if not isinstance(spec, dict):
        raise LetteringError(f"{layer.get('layer_id')}: font object required")
    mode = spec.get("mode")
    size = int(spec.get("size", 0))
    if size <= 0:
        raise LetteringError(f"{layer.get('layer_id')}: font size must be positive")

    if mode == "PIL_DEFAULT":
        if plan.get("purpose") != "CALIBRATION_PLACEHOLDER":
            raise LetteringError("PIL_DEFAULT font is calibration-placeholder only")
        return ImageFont.load_default(size=size), None

    if mode == "PROJECT_FILE":
        rel = spec.get("path")
        expected = spec.get("sha256")
        if not isinstance(rel, str) or not rel:
            raise LetteringError(f"{layer.get('layer_id')}: project font path required")
        if not isinstance(expected, str) or len(expected) != 64:
            raise LetteringError(f"{layer.get('layer_id')}: project font sha256 required")
        path = _inside(project_root, rel, "font")
        if not path.is_file():
            raise LetteringError(f"{layer.get('layer_id')}: missing font bytes: {rel}")
        actual = sha256_file(path)
        if actual != expected:
            raise LetteringError(f"{layer.get('layer_id')}: font SHA-256 mismatch")
        return ImageFont.truetype(path, size=size), actual

    raise LetteringError(f"{layer.get('layer_id')}: unsupported font mode {mode!r}")


def _load_base(project_root: Path, plan: dict) -> tuple[Image.Image, str | None]:
    canvas = plan.get("canvas")
    if not isinstance(canvas, dict):
        raise LetteringError("canvas object required")
    width = int(canvas.get("width", 0))
    height = int(canvas.get("height", 0))
    if width <= 0 or height <= 0:
        raise LetteringError("canvas width/height must be positive")
    background = _rgba(canvas.get("background_rgba"), "canvas.background_rgba")
    base_spec = plan.get("base_image")
    if base_spec is None:
        return Image.new("RGBA", (width, height), background), None

    if not isinstance(base_spec, dict):
        raise LetteringError("base_image must be object or null")
    rel = base_spec.get("path")
    expected = base_spec.get("sha256")
    if not isinstance(rel, str) or not rel:
        raise LetteringError("base_image.path required")
    if not isinstance(expected, str) or len(expected) != 64:
        raise LetteringError("base_image.sha256 required")
    path = _inside(project_root, rel, "base image")
    if not path.is_file():
        raise LetteringError(f"missing base image bytes: {rel}")
    actual = sha256_file(path)
    if actual != expected:
        raise LetteringError("base image SHA-256 mismatch")
    with Image.open(path) as raw:
        if raw.size != (width, height):
            raise LetteringError("base image dimensions must match canvas")
        return raw.convert("RGBA"), actual


def _measure_lines(draw: ImageDraw.ImageDraw, lines: list[str], font, stroke_width: int, spacing: int):
    metrics = []
    for line in lines:
        bbox = draw.textbbox((0, 0), line, font=font, stroke_width=stroke_width)
        metrics.append((bbox, bbox[2] - bbox[0], bbox[3] - bbox[1]))
    width = max((m[1] for m in metrics), default=0)
    height = sum(m[2] for m in metrics) + max(0, len(metrics) - 1) * spacing
    return metrics, width, height


def _draw_layer(project_root: Path, plan: dict, image: Image.Image, layer: dict) -> dict:
    layer_id = layer.get("layer_id")
    if not isinstance(layer_id, str) or not layer_id:
        raise LetteringError("text layer_id required")
    lines = layer.get("lines")
    if not isinstance(lines, list) or not lines or not all(isinstance(x, str) for x in lines):
        raise LetteringError(f"{layer_id}: lines must be non-empty string list")

    font, font_hash = _font(project_root, plan, layer)
    draw = ImageDraw.Draw(image)
    stroke_width = int(layer.get("stroke_width", 0))
    spacing = int(layer.get("line_spacing", 0))
    if stroke_width < 0 or spacing < 0:
        raise LetteringError(f"{layer_id}: stroke_width/line_spacing must be non-negative")
    metrics, text_w, text_h = _measure_lines(draw, lines, font, stroke_width, spacing)

    x = int(layer.get("x", 0))
    y = int(layer.get("y", 0))
    anchor = layer.get("anchor", "LEFT")
    if anchor == "LEFT":
        left = x
    elif anchor == "CENTER":
        left = x - text_w // 2
    elif anchor == "RIGHT":
        left = x - text_w
    else:
        raise LetteringError(f"{layer_id}: invalid anchor")

    box = layer.get("box", {"type": "NONE"})
    if not isinstance(box, dict):
        raise LetteringError(f"{layer_id}: box must be object")
    box_type = box.get("type", "NONE")
    if box_type not in {"NONE", "RECT"}:
        raise LetteringError(f"{layer_id}: invalid box type")

    if box_type == "RECT":
        padding = box.get("padding", [0, 0, 0, 0])
        if not isinstance(padding, list) or len(padding) != 4:
            raise LetteringError(f"{layer_id}: box.padding must be [l,t,r,b]")
        pl, pt, pr, pb = (int(v) for v in padding)
        if min(pl, pt, pr, pb) < 0:
            raise LetteringError(f"{layer_id}: box padding must be non-negative")
        fill = _rgba(box.get("fill_rgba"), f"{layer_id}.box.fill_rgba")
        outline_value = box.get("outline_rgba")
        outline = _rgba(outline_value, f"{layer_id}.box.outline_rgba") if outline_value is not None else None
        outline_width = int(box.get("outline_width", 0))
        if outline_width < 0:
            raise LetteringError(f"{layer_id}: outline_width must be non-negative")
        draw.rectangle(
            (left - pl, y - pt, left + text_w + pr, y + text_h + pb),
            fill=fill,
            outline=outline,
            width=outline_width,
        )

    fill = _rgba(layer.get("fill_rgba"), f"{layer_id}.fill_rgba")
    stroke_value = layer.get("stroke_fill_rgba")
    stroke_fill = _rgba(stroke_value, f"{layer_id}.stroke_fill_rgba") if stroke_value is not None else None

    cursor_y = y
    for line, (bbox, line_w, line_h) in zip(lines, metrics):
        if anchor == "LEFT":
            line_x = left
        elif anchor == "CENTER":
            line_x = x - line_w // 2
        else:
            line_x = x - line_w
        draw.text(
            (line_x - bbox[0], cursor_y - bbox[1]),
            line,
            font=font,
            fill=fill,
            stroke_width=stroke_width,
            stroke_fill=stroke_fill,
        )
        cursor_y += line_h + spacing

    return {
        "layer_id": layer_id,
        "font_sha256": font_hash,
        "bounds": [left, y, left + text_w, y + text_h],
    }


def render_lettering(project_root: Path, plan_path: Path, output_path: Path, receipt_path: Path) -> dict:
    plan = load_json(plan_path)
    if plan.get("schema_version") != "1.0":
        raise LetteringError("unsupported lettering schema_version")
    if plan.get("purpose") not in {"CALIBRATION_PLACEHOLDER", "PRODUCTION"}:
        raise LetteringError("purpose must be CALIBRATION_PLACEHOLDER or PRODUCTION")

    image, base_hash = _load_base(project_root, plan)
    layers = plan.get("text_layers")
    if not isinstance(layers, list):
        raise LetteringError("text_layers must be a list")

    seen = set()
    rendered = []
    indexed = list(enumerate(layers))
    for original_index, layer in sorted(indexed, key=lambda p: (int(p[1].get("z", 0)), p[0])):
        layer_id = layer.get("layer_id")
        if layer_id in seen:
            raise LetteringError(f"duplicate text layer_id: {layer_id!r}")
        seen.add(layer_id)
        info = _draw_layer(project_root, plan, image, layer)
        info["layer_index"] = original_index
        info["z"] = int(layer.get("z", 0))
        rendered.append(info)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    image.save(output_path, "PNG", optimize=False, compress_level=9)
    receipt = {
        "schema_version": "1.0",
        "plan_id": plan.get("plan_id"),
        "purpose": plan["purpose"],
        "plan_sha256": sha256_file(plan_path),
        "base_image_sha256": base_hash,
        "output_path": str(output_path),
        "output_sha256": sha256_file(output_path),
        "text_layers": rendered,
    }
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    receipt_path.write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", required=True)
    parser.add_argument("--plan", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--receipt")
    args = parser.parse_args()

    root = Path(args.project_root).resolve()
    plan = Path(args.plan).resolve()
    output = Path(args.output).resolve()
    receipt = Path(args.receipt).resolve() if args.receipt else Path(str(output) + ".lettering.json")

    try:
        result = render_lettering(root, plan, output, receipt)
    except (LetteringError, KeyError, TypeError, ValueError) as exc:
        print(f"LETTERING_FAIL: {exc}")
        return 2
    print(f"LETTERING_PASS sha256={result['output_sha256']}")
    print(f"receipt={receipt}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
