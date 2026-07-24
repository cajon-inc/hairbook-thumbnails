"""Manifest-driven renderer for the approved person-first V3 catalog banner.

The renderer intentionally does not generate or alter people. It:

1. loads an existing salon-page person/style image;
2. applies deterministic crop and light color correction;
3. draws the approved layered V3 layout;
4. writes an exact-text 1080x1350 JPEG and a 360x450 review preview;
5. records source/copy/output hashes for QA and preflight.

Usage:
    python3 person_v3.py \
      --manifest ../dashboard/source_images/person_v3_manifest.sample.json \
      --output-dir ../dashboard/rollout_output/person-v3-sample
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image, ImageDraw, ImageEnhance, ImageFont, ImageOps

W = 1080
H = 1350
MOBILE_W = 360
MOBILE_H = 450
DESIGN_VERSION = "person_v3_layered_v1"
SCHEMA_VERSION = "hairbook.person_v3_manifest.v1"

ROOT = Path(__file__).resolve().parent

THEMES: dict[str, dict[str, Any]] = {
    "ink_gold": {
        "scrim": "#17130f",
        "plate": "#f7f2e8",
        "plate_opacity": 0.92,
        "plate_text": "#221c15",
        "body_text": "#fffaf2",
        "secondary_text": "#e6d7c7",
        "accent": "#d2a56c",
        "cta_fill": "#f7f2e8",
        "cta_text": "#221c15",
    },
    "sage": {
        "scrim": "#24301f",
        "plate": "#f4f6f1",
        "plate_opacity": 0.96,
        "plate_text": "#273021",
        "body_text": "#ffffff",
        "secondary_text": "#dbe4d4",
        "accent": "#b4c5a7",
        "cta_fill": "#b4c5a7",
        "cta_text": "#273021",
    },
}


class ManifestError(ValueError):
    """The source manifest cannot safely be rendered."""


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _canonical_sha(value: Any) -> str:
    data = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return _sha256_bytes(data)


def _hex_rgba(value: str, alpha: int = 255) -> tuple[int, int, int, int]:
    value = value.lstrip("#")
    if len(value) != 6:
        raise ManifestError(f"invalid color: {value!r}")
    return (
        int(value[0:2], 16),
        int(value[2:4], 16),
        int(value[4:6], 16),
        alpha,
    )


def _font_globs(role: str) -> list[Path]:
    local = ROOT / "fonts"
    if role == "mincho":
        exact = [
            local / "NotoSerifJP-Bold.otf",
            Path("/usr/share/fonts/opentype/noto/NotoSerifCJK-Bold.ttc"),
            Path("/usr/share/fonts/opentype/noto/NotoSerifCJK-Regular.ttc"),
            Path("/System/Library/Fonts/ヒラギノ明朝 ProN.ttc"),
        ]
        patterns = [
            "/System/Library/AssetsV2/**/YuMincho*.ttc",
            "/System/Library/AssetsV2/**/*Mincho*.otf",
        ]
    elif role == "gothic_regular":
        exact = [
            local / "NotoSansJP-Regular.otf",
            Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"),
            Path("/System/Library/Fonts/ヒラギノ角ゴシック W4.ttc"),
            Path("/Library/Fonts/Arial Unicode.ttf"),
        ]
        patterns = [
            "/System/Library/AssetsV2/**/YuGothic-Medium.otf",
            "/System/Library/Fonts/*角ゴシック*W4*.ttc",
        ]
    else:
        exact = [
            local / "NotoSansJP-Bold.otf",
            Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc"),
            Path("/System/Library/Fonts/ヒラギノ角ゴシック W6.ttc"),
        ]
        patterns = [
            "/System/Library/AssetsV2/**/YuGothic-Bold.otf",
            "/System/Library/Fonts/*角ゴシック*W6*.ttc",
        ]

    found = list(exact)
    for pattern in patterns:
        # pathlib cannot glob an absolute pattern directly.
        root = Path("/")
        found.extend(root.glob(pattern.lstrip("/")))
    return found


def _fc_match(role: str) -> Path | None:
    if not shutil.which("fc-match"):
        return None
    family = {
        "mincho": "Noto Serif CJK JP:style=Bold",
        "gothic_regular": "Noto Sans CJK JP:style=Regular",
        "gothic_bold": "Noto Sans CJK JP:style=Bold",
    }[role]
    try:
        result = subprocess.run(
            ["fc-match", "-f", "%{file}", family],
            check=True,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    candidate = Path(result.stdout.strip())
    return candidate if candidate.exists() else None


@lru_cache(maxsize=None)
def _font_path(role: str) -> Path:
    candidates = _font_globs(role)
    match = _fc_match(role)
    if match:
        # fontconfig may silently fall back to a Latin-only font when the
        # requested Noto family is unavailable (notably on macOS). Prefer the
        # explicit Japanese candidates and use fc-match only as a last resort.
        candidates.append(match)
    for candidate in candidates:
        if candidate.exists() and candidate.is_file():
            return candidate
    raise RuntimeError(
        f"Japanese {role} font not found. Install fonts-noto-cjk or add fonts under {ROOT / 'fonts'}."
    )


@lru_cache(maxsize=256)
def _font(role: str, size: int) -> ImageFont.FreeTypeFont:
    path = _font_path(role)
    if path.suffix.lower() == ".ttc":
        fallback: ImageFont.FreeTypeFont | None = None
        for index in range(10):
            try:
                candidate = ImageFont.truetype(str(path), size=size, index=index)
            except OSError:
                break
            fallback = fallback or candidate
            name = " ".join(str(part) for part in candidate.getname())
            if "JP" in name or "Japanese" in name or "ヒラギノ" in name:
                return candidate
        if fallback:
            return fallback
    return ImageFont.truetype(str(path), size=size)


def _text_width(draw: ImageDraw.ImageDraw, value: str, font: ImageFont.FreeTypeFont) -> int:
    box = draw.textbbox((0, 0), value, font=font)
    return box[2] - box[0]


def _fit_font(
    draw: ImageDraw.ImageDraw,
    lines: list[str],
    role: str,
    start_size: int,
    min_size: int,
    max_width: int,
) -> tuple[ImageFont.FreeTypeFont, int]:
    if not lines or any(not str(line).strip() for line in lines):
        raise ManifestError("text lines must be non-empty")
    for size in range(start_size, min_size - 1, -2):
        font = _font(role, size)
        if all(_text_width(draw, line, font) <= max_width for line in lines):
            return font, size
    longest = max(lines, key=len)
    raise ManifestError(
        f"text does not fit at minimum size {min_size}: {longest!r}"
    )


def _draw_lines(
    draw: ImageDraw.ImageDraw,
    xy: tuple[int, int],
    lines: list[str],
    font: ImageFont.FreeTypeFont,
    fill: tuple[int, int, int, int],
    line_height: int,
) -> None:
    x, y = xy
    for index, line in enumerate(lines):
        draw.text(
            (x, y + index * line_height),
            line,
            font=font,
            fill=fill,
            anchor="lt",
        )


def _gradient_layer(
    size: tuple[int, int],
    y0: int,
    y1: int,
    color: tuple[int, int, int],
    stops: list[tuple[float, float]],
) -> Image.Image:
    width, height = size
    positions = np.array([stop[0] for stop in stops], dtype=np.float32)
    alphas = np.array([stop[1] for stop in stops], dtype=np.float32)
    y = np.arange(height, dtype=np.float32)
    progress = np.clip((y - y0) / max(1, y1 - y0), 0, 1)
    alpha = np.interp(progress, positions, alphas)
    alpha[y < y0] = 0
    alpha[y > y1] = alphas[-1]
    arr = np.zeros((height, width, 4), dtype=np.uint8)
    arr[..., 0] = color[0]
    arr[..., 1] = color[1]
    arr[..., 2] = color[2]
    arr[..., 3] = np.round(alpha[:, None] * 255).astype(np.uint8)
    return Image.fromarray(arr)


def _rounded_shadow(
    base: Image.Image,
    box: tuple[int, int, int, int],
    radius: int,
    offset: tuple[int, int] = (8, 9),
    alpha: int = 72,
) -> None:
    x0, y0, x1, y1 = box
    layer = Image.new("RGBA", base.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer, "RGBA")
    dx, dy = offset
    draw.rounded_rectangle(
        (x0 + dx, y0 + dy, x1 + dx, y1 + dy),
        radius=radius,
        fill=(0, 0, 0, alpha),
    )
    base.alpha_composite(layer)


def _resolve_source(manifest_path: Path, asset: dict[str, Any]) -> Path:
    source = asset.get("source") or {}
    raw = str(source.get("path") or "").strip()
    if not raw:
        raise ManifestError(f"{asset.get('asset_id')}: source.path is required")
    path = Path(raw)
    if not path.is_absolute():
        path = (manifest_path.parent / path).resolve()
    if not path.is_file():
        raise ManifestError(f"{asset.get('asset_id')}: source file not found: {path}")
    expected = str(source.get("sha256") or "").lower()
    actual = sha256_file(path)
    if not expected:
        raise ManifestError(f"{asset.get('asset_id')}: source.sha256 is required")
    if actual != expected:
        raise ManifestError(
            f"{asset.get('asset_id')}: source hash mismatch: expected {expected}, got {actual}"
        )
    return path


def load_manifest(path: Path) -> dict[str, Any]:
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ManifestError(f"cannot read manifest {path}: {exc}") from exc
    if manifest.get("schema_version") != SCHEMA_VERSION:
        raise ManifestError(
            f"schema_version must be {SCHEMA_VERSION!r}"
        )
    if manifest.get("design_version") != DESIGN_VERSION:
        raise ManifestError(
            f"design_version must be {DESIGN_VERSION!r}"
        )
    assets = manifest.get("assets")
    if not isinstance(assets, list) or not assets:
        raise ManifestError("manifest.assets must be a non-empty list")
    ids: set[str] = set()
    for asset in assets:
        asset_id = str(asset.get("asset_id") or "").strip()
        if not asset_id:
            raise ManifestError("every asset requires asset_id")
        if asset_id in ids:
            raise ManifestError(f"duplicate asset_id: {asset_id}")
        ids.add(asset_id)
        copy = asset.get("copy") or {}
        for field in ("area", "salon_name", "access", "headline", "cta"):
            if not copy.get(field):
                raise ManifestError(f"{asset_id}: copy.{field} is required")
        for field in ("access", "headline"):
            lines = copy[field]
            if not isinstance(lines, list) or not 1 <= len(lines) <= 2:
                raise ManifestError(
                    f"{asset_id}: copy.{field} must contain 1 or 2 explicit lines"
                )
        if asset.get("theme", "ink_gold") not in THEMES:
            raise ManifestError(f"{asset_id}: unknown theme {asset.get('theme')!r}")
    return manifest


def _render_asset(
    manifest_path: Path,
    manifest_sha256: str,
    design_version: str,
    asset: dict[str, Any],
    output_dir: Path,
) -> dict[str, Any]:
    asset_id = str(asset["asset_id"])
    source_path = _resolve_source(manifest_path, asset)
    source_sha256 = sha256_file(source_path)
    copy = asset["copy"]
    theme = dict(THEMES[asset.get("theme", "ink_gold")])
    theme.update(asset.get("theme_overrides") or {})
    image_cfg = asset.get("image") or {}

    focal_x = float(image_cfg.get("focal_x", 0.5))
    focal_y = float(image_cfg.get("focal_y", 0.5))
    if not (0 <= focal_x <= 1 and 0 <= focal_y <= 1):
        raise ManifestError(f"{asset_id}: focal point must be between 0 and 1")

    with Image.open(source_path) as opened:
        source = ImageOps.exif_transpose(opened).convert("RGB")
        source_size = source.size
        base = ImageOps.fit(
            source,
            (W, H),
            method=Image.Resampling.LANCZOS,
            centering=(focal_x, focal_y),
        )
    brightness = float(image_cfg.get("brightness", 1.0))
    saturation = float(image_cfg.get("saturation", 1.0))
    contrast = float(image_cfg.get("contrast", 1.0))
    zoom = float(image_cfg.get("zoom", 1.0))
    if not (0.75 <= brightness <= 1.25):
        raise ManifestError(f"{asset_id}: brightness outside safe range")
    if not (0.65 <= saturation <= 1.25):
        raise ManifestError(f"{asset_id}: saturation outside safe range")
    if not (0.8 <= contrast <= 1.2):
        raise ManifestError(f"{asset_id}: contrast outside safe range")
    if not (1.0 <= zoom <= 1.35):
        raise ManifestError(f"{asset_id}: zoom outside safe range")
    if zoom > 1:
        zoomed_width = round(W * zoom)
        zoomed_height = round(H * zoom)
        zoomed = base.resize(
            (zoomed_width, zoomed_height),
            Image.Resampling.LANCZOS,
        )
        left = round((zoomed_width - W) * focal_x)
        top = round((zoomed_height - H) * focal_y)
        base = zoomed.crop((left, top, left + W, top + H))
    base = ImageEnhance.Brightness(base).enhance(brightness)
    base = ImageEnhance.Color(base).enhance(saturation)
    base = ImageEnhance.Contrast(base).enhance(contrast).convert("RGBA")

    scrim = _hex_rgba(theme["scrim"])[:3]
    base.alpha_composite(
        _gradient_layer(
            (W, H),
            0,
            300,
            (0, 0, 0),
            [(0.0, 0.20), (1.0, 0.0)],
        )
    )
    base.alpha_composite(
        _gradient_layer(
            (W, H),
            390,
            H,
            scrim,
            [(0.0, 0.0), (0.34, 0.08), (0.58, 0.74), (1.0, 0.98)],
        )
    )

    draw = ImageDraw.Draw(base, "RGBA")
    measure = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    accent = _hex_rgba(theme["accent"])
    plate = _hex_rgba(
        theme["plate"],
        round(float(theme["plate_opacity"]) * 255),
    )
    plate_text = _hex_rgba(theme["plate_text"])
    body_text = _hex_rgba(theme["body_text"])
    secondary_text = _hex_rgba(theme["secondary_text"])

    draw.rounded_rectangle(
        (28, 28, 1052, 1322),
        radius=18,
        outline=accent[:3] + (133,),
        width=2,
    )

    area_text = str(copy["area"]).strip()
    salon_name = str(copy["salon_name"]).strip()
    area_font, _ = _fit_font(measure, [area_text], "gothic_bold", 30, 26, 850)
    name_font, name_size = _fit_font(
        measure,
        [salon_name],
        "mincho",
        int(asset.get("name_size", 56)),
        38,
        850,
    )
    area_width = _text_width(measure, area_text, area_font)
    name_width = _text_width(measure, salon_name, name_font)
    header_width = max(520, min(956, max(area_width, name_width) + 58))
    header_height = 150
    header_box = (48, 48, 48 + header_width, 48 + header_height)
    _rounded_shadow(base, header_box, 16, offset=(10, 12), alpha=58)
    draw = ImageDraw.Draw(base, "RGBA")
    draw.rounded_rectangle(header_box, radius=16, fill=plate)
    draw.rounded_rectangle(
        (48, 48, 48 + header_width, 55),
        radius=4,
        fill=accent,
    )
    draw.text((74, 70), area_text, font=area_font, fill=accent, anchor="lt")
    name_y = 111 if name_size >= 50 else 116
    draw.text(
        (72, name_y),
        salon_name,
        font=name_font,
        fill=plate_text,
        anchor="lt",
    )

    access_lines = [str(line).strip() for line in copy["access"]]
    has_two_access_lines = len(access_lines) > 1
    access_top = 792 if has_two_access_lines else 820
    access_height = 112 if has_two_access_lines else 80
    access_font, access_size = _fit_font(
        measure,
        access_lines,
        "gothic_bold",
        36,
        30,
        890,
    )
    access_box = (58, access_top, 1006, access_top + access_height)
    _rounded_shadow(base, access_box, 14, offset=(8, 9), alpha=72)
    draw = ImageDraw.Draw(base, "RGBA")
    draw.rounded_rectangle(
        access_box,
        radius=14,
        fill=_hex_rgba(theme["scrim"], 118),
        outline=accent,
        width=3,
    )
    access_line_height = max(42, access_size + 8)
    access_y = access_top + (18 if has_two_access_lines else 20)
    _draw_lines(
        draw,
        (86, access_y),
        access_lines,
        access_font,
        accent,
        access_line_height,
    )

    draw.rounded_rectangle((58, 932, 140, 937), radius=3, fill=accent)
    headline_lines = [str(line).strip() for line in copy["headline"]]
    headline_font, headline_size = _fit_font(
        measure,
        headline_lines,
        "mincho",
        int(asset.get("headline_size", 60)),
        46,
        930,
    )
    headline_line_height = max(66, headline_size + 12)
    headline_y = 970
    _draw_lines(
        draw,
        (58, headline_y),
        headline_lines,
        headline_font,
        body_text,
        headline_line_height,
    )

    support = str(copy.get("support") or "").strip()
    if support:
        support_font, support_size = _fit_font(
            measure,
            [support],
            "gothic_regular",
            34,
            28,
            930,
        )
        support_y = headline_y + len(headline_lines) * headline_line_height + 8
        if support_y + support_size > 1180:
            raise ManifestError(f"{asset_id}: support text collides with CTA")
        draw.text(
            (58, support_y),
            support,
            font=support_font,
            fill=secondary_text,
            anchor="lt",
        )

    cta = str(copy["cta"]).strip()
    cta_font, _ = _fit_font(
        measure,
        [cta],
        "gothic_bold",
        36,
        30,
        300,
    )
    cta_box = (58, 1196, 418, 1282)
    _rounded_shadow(base, cta_box, 15, offset=(8, 8), alpha=76)
    draw = ImageDraw.Draw(base, "RGBA")
    draw.rounded_rectangle(
        cta_box,
        radius=15,
        fill=_hex_rgba(theme["cta_fill"]),
        outline=accent,
        width=2,
    )
    cta_bbox = draw.textbbox((0, 0), cta, font=cta_font)
    cta_width = cta_bbox[2] - cta_bbox[0]
    cta_height = cta_bbox[3] - cta_bbox[1]
    draw.text(
        (
            (cta_box[0] + cta_box[2] - cta_width) / 2 - cta_bbox[0],
            (cta_box[1] + cta_box[3] - cta_height) / 2 - cta_bbox[1],
        ),
        cta,
        font=cta_font,
        fill=_hex_rgba(theme["cta_text"]),
    )

    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"{asset_id}.jpg"
    preview_path = output_dir / f"{asset_id}--mobile.jpg"
    rgb = base.convert("RGB")
    rgb.save(
        output_path,
        "JPEG",
        quality=92,
        subsampling=0,
        optimize=True,
    )
    rgb.resize(
        (MOBILE_W, MOBILE_H),
        Image.Resampling.LANCZOS,
    ).save(
        preview_path,
        "JPEG",
        quality=90,
        subsampling=0,
        optimize=True,
    )

    copy_sha256 = _canonical_sha(copy)
    return {
        "asset_id": asset_id,
        "salon_id": str(asset.get("salon_id") or ""),
        "product_ids": [str(value) for value in asset.get("product_ids") or []],
        "design_version": design_version,
        "representation": "salon_page_person_image_edit",
        "render_mode": "complete_banner",
        "source_path": str(source_path),
        "source_page_url": str((asset.get("source") or {}).get("page_url") or ""),
        "source_image_url": str((asset.get("source") or {}).get("image_url") or ""),
        "source_sha256": source_sha256,
        "source_width": source_size[0],
        "source_height": source_size[1],
        "copy_sha256": copy_sha256,
        "manifest_sha256": manifest_sha256,
        "output_path": str(output_path.resolve()),
        "output_sha256": sha256_file(output_path),
        "preview_path": str(preview_path.resolve()),
        "preview_sha256": sha256_file(preview_path),
        "public_url": str(asset.get("public_url") or ""),
        "width": W,
        "height": H,
        "theme": str(asset.get("theme", "ink_gold")),
    }


def render_manifest(
    manifest_path: Path,
    output_dir: Path,
    only: set[str] | None = None,
) -> dict[str, Any]:
    manifest_path = manifest_path.resolve()
    manifest = load_manifest(manifest_path)
    manifest_sha256 = sha256_file(manifest_path)
    records = []
    for asset in manifest["assets"]:
        asset_id = str(asset["asset_id"])
        if only and asset_id not in only:
            continue
        records.append(
            _render_asset(
                manifest_path,
                manifest_sha256,
                manifest["design_version"],
                asset,
                output_dir.resolve(),
            )
        )
    if not records:
        raise ManifestError("no assets selected for rendering")
    payload = {
        "schema_version": "hairbook.person_v3_render_index.v1",
        "environment": str(manifest.get("environment") or "production"),
        "design_version": manifest["design_version"],
        "manifest_path": str(manifest_path),
        "manifest_sha256": manifest_sha256,
        "rendered_at": datetime.now(timezone.utc).isoformat(),
        "assets": records,
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    index_path = output_dir / "render_index.json"
    index_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Render approved person-first V3 catalog banners from a manifest."
    )
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument(
        "--only",
        action="append",
        default=[],
        help="Render only this asset_id. Repeat for multiple assets.",
    )
    args = parser.parse_args()
    payload = render_manifest(
        args.manifest,
        args.output_dir,
        set(args.only) or None,
    )
    print(
        json.dumps(
            {
                "status": "rendered",
                "design_version": payload["design_version"],
                "asset_count": len(payload["assets"]),
                "output_dir": str(args.output_dir.resolve()),
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
