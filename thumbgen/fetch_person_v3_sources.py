"""Fetch and verify private source images referenced by a Person V3 manifest.

The source image binaries are intentionally git-ignored. Their provenance,
canonical URL and SHA-256 remain in the manifest, so CI and operators can
recreate the exact input without committing salon-page photographs.

Usage:
    python3 thumbgen/fetch_person_v3_sources.py \
      --manifest dashboard/source_images/person_v3_manifest.sample.json
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from PIL import Image

from person_v3 import ManifestError, load_manifest, sha256_file

DEFAULT_MAX_BYTES = 25 * 1024 * 1024
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
USER_AGENT = (
    "Mozilla/5.0 (compatible; HairbookCreativeQA/1.0; "
    "+https://hairbook.jp/)"
)


class SourceFetchError(RuntimeError):
    """A source image could not be fetched or verified safely."""


def _target_path(manifest_path: Path, asset: dict[str, Any]) -> Path:
    asset_id = str(asset.get("asset_id") or "<unknown>")
    source = asset.get("source") or {}
    raw = str(source.get("path") or "").strip()
    if not raw:
        raise SourceFetchError(f"{asset_id}: source.path is required")
    candidate = Path(raw)
    if candidate.is_absolute():
        raise SourceFetchError(
            f"{asset_id}: absolute source.path is not allowed for downloads"
        )
    root = manifest_path.parent.resolve()
    target = (root / candidate).resolve()
    try:
        target.relative_to(root)
    except ValueError as exc:
        raise SourceFetchError(
            f"{asset_id}: source.path escapes the manifest directory"
        ) from exc
    return target


def _expected_sha(asset: dict[str, Any]) -> str:
    asset_id = str(asset.get("asset_id") or "<unknown>")
    expected = str((asset.get("source") or {}).get("sha256") or "").lower()
    if not SHA256_RE.fullmatch(expected):
        raise SourceFetchError(
            f"{asset_id}: source.sha256 must be a lowercase 64-character SHA-256"
        )
    return expected


def _source_url(asset: dict[str, Any]) -> str:
    asset_id = str(asset.get("asset_id") or "<unknown>")
    raw = str((asset.get("source") or {}).get("image_url") or "").strip()
    parsed = urllib.parse.urlparse(raw)
    if parsed.scheme != "https" or not parsed.netloc:
        raise SourceFetchError(
            f"{asset_id}: source.image_url must be an absolute HTTPS URL"
        )
    return raw


def _verify_decodable_image(path: Path, asset_id: str) -> tuple[int, int, str]:
    try:
        with Image.open(path) as image:
            image.verify()
        with Image.open(path) as image:
            width, height = image.size
            image_format = str(image.format or "").upper()
    except (OSError, ValueError) as exc:
        raise SourceFetchError(
            f"{asset_id}: downloaded file is not a valid image"
        ) from exc
    if width < 360 or height < 450:
        raise SourceFetchError(
            f"{asset_id}: source is too small ({width}x{height}); minimum is 360x450"
        )
    return width, height, image_format


def _download(
    url: str,
    target: Path,
    expected_sha: str,
    asset_id: str,
    max_bytes: int,
    timeout: float,
) -> dict[str, Any]:
    target.parent.mkdir(parents=True, exist_ok=True)
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
        },
    )
    temp_name: str | None = None
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            final_url = response.geturl()
            final_scheme = urllib.parse.urlparse(final_url).scheme
            if final_scheme != "https":
                raise SourceFetchError(
                    f"{asset_id}: redirect ended on a non-HTTPS URL"
                )
            content_type = str(response.headers.get_content_type() or "").lower()
            if not content_type.startswith("image/"):
                raise SourceFetchError(
                    f"{asset_id}: unexpected Content-Type {content_type!r}"
                )
            declared = response.headers.get("Content-Length")
            if declared and int(declared) > max_bytes:
                raise SourceFetchError(
                    f"{asset_id}: source exceeds {max_bytes} bytes"
                )

            digest = hashlib.sha256()
            received = 0
            with tempfile.NamedTemporaryFile(
                mode="wb",
                prefix=f".{target.name}.",
                suffix=".download",
                dir=target.parent,
                delete=False,
            ) as temp:
                temp_name = temp.name
                while True:
                    chunk = response.read(1024 * 1024)
                    if not chunk:
                        break
                    received += len(chunk)
                    if received > max_bytes:
                        raise SourceFetchError(
                            f"{asset_id}: source exceeds {max_bytes} bytes"
                        )
                    digest.update(chunk)
                    temp.write(chunk)

        actual_sha = digest.hexdigest()
        if actual_sha != expected_sha:
            raise SourceFetchError(
                f"{asset_id}: source hash mismatch: expected {expected_sha}, got {actual_sha}"
            )
        temp_path = Path(temp_name)
        width, height, image_format = _verify_decodable_image(temp_path, asset_id)
        os.replace(temp_path, target)
        temp_name = None
        return {
            "status": "downloaded",
            "path": str(target),
            "sha256": actual_sha,
            "bytes": received,
            "width": width,
            "height": height,
            "format": image_format,
            "final_url": final_url,
        }
    except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
        raise SourceFetchError(f"{asset_id}: download failed: {exc}") from exc
    finally:
        if temp_name:
            Path(temp_name).unlink(missing_ok=True)


def fetch_manifest_sources(
    manifest_path: Path,
    only: set[str] | None = None,
    max_bytes: int = DEFAULT_MAX_BYTES,
    timeout: float = 30.0,
) -> dict[str, Any]:
    manifest_path = manifest_path.resolve()
    manifest = load_manifest(manifest_path)
    available_ids = {str(asset["asset_id"]) for asset in manifest["assets"]}
    unknown = (only or set()) - available_ids
    if unknown:
        raise SourceFetchError(
            f"unknown --only asset_id(s): {', '.join(sorted(unknown))}"
        )

    results: list[dict[str, Any]] = []
    for asset in manifest["assets"]:
        asset_id = str(asset["asset_id"])
        if only and asset_id not in only:
            continue
        target = _target_path(manifest_path, asset)
        expected = _expected_sha(asset)
        if target.is_file() and sha256_file(target) == expected:
            width, height, image_format = _verify_decodable_image(target, asset_id)
            results.append(
                {
                    "asset_id": asset_id,
                    "status": "verified_existing",
                    "path": str(target),
                    "sha256": expected,
                    "bytes": target.stat().st_size,
                    "width": width,
                    "height": height,
                    "format": image_format,
                }
            )
            continue
        result = _download(
            _source_url(asset),
            target,
            expected,
            asset_id,
            max_bytes,
            timeout,
        )
        result["asset_id"] = asset_id
        results.append(result)

    return {
        "schema_version": "hairbook.person_v3_source_fetch.v1",
        "manifest": str(manifest_path),
        "manifest_sha256": sha256_file(manifest_path),
        "count": len(results),
        "downloaded": sum(item["status"] == "downloaded" for item in results),
        "verified_existing": sum(
            item["status"] == "verified_existing" for item in results
        ),
        "results": results,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Fetch and SHA-256 verify Person V3 source images."
    )
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument(
        "--only",
        action="append",
        default=[],
        help="Fetch only this asset_id. Repeatable.",
    )
    parser.add_argument(
        "--max-bytes",
        type=int,
        default=DEFAULT_MAX_BYTES,
    )
    parser.add_argument("--timeout", type=float, default=30.0)
    args = parser.parse_args()

    if args.max_bytes <= 0:
        parser.error("--max-bytes must be positive")
    if args.timeout <= 0:
        parser.error("--timeout must be positive")
    try:
        report = fetch_manifest_sources(
            args.manifest,
            set(args.only) or None,
            args.max_bytes,
            args.timeout,
        )
    except (ManifestError, SourceFetchError) as exc:
        parser.exit(2, f"source fetch failed: {exc}\n")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
