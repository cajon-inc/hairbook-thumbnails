"""Read-only inventory snapshot for HB_02 static catalog creatives.

The command can read either an exported CSV or the live Google Sheet using the
existing service-account secret. It never writes to Google Sheets.

Examples:
    python3 creative_inventory.py \
      --input-csv /secure/feed.csv \
      --output-dir ../dashboard/private_snapshots/run-20260724

    GOOGLE_SHEETS_KEY_JSON=... python3 creative_inventory.py \
      --google-sheet \
      --output-dir ../dashboard/private_snapshots/run-20260724
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

FEED_ID = "1nCim5RCsQ9AIksey-AP4PQ6eryR-nGUOg0h8NJHmek4"
FEED_TAB = "入稿用データフィード_ローカル商品"
OVERRIDE_TAB = "thumbnail_override"
INVENTORY_SCHEMA = "hairbook.catalog_static_inventory.v1"
OVERRIDE_SCHEMA = "hairbook.thumbnail_override_snapshot.v1"


class InventoryError(RuntimeError):
    """The feed cannot be safely snapshotted or classified."""


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _canonical_bytes(value: Any) -> bytes:
    return (
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    ).encode("utf-8")


def _write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _normalize_rows(values: list[list[Any]]) -> list[dict[str, str]]:
    if not values:
        raise InventoryError("sheet/CSV is empty")
    headers = [str(value).strip() for value in values[0]]
    if not headers or headers[0] != "id":
        raise InventoryError("first column must be id")
    rows = []
    for raw in values[1:]:
        padded = list(raw) + [""] * max(0, len(headers) - len(raw))
        row = {
            header: str(padded[index] if index < len(padded) else "").strip()
            for index, header in enumerate(headers)
            if header
        }
        if row.get("id"):
            rows.append(row)
    return rows


def _read_csv(path: Path) -> list[dict[str, str]]:
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as fh:
            reader = csv.reader(fh)
            return _normalize_rows([list(row) for row in reader])
    except OSError as exc:
        raise InventoryError(f"cannot read CSV {path}: {exc}") from exc


def _gspread_client():
    raw = os.environ.get("GOOGLE_SHEETS_KEY_JSON")
    if not raw:
        raise InventoryError(
            "GOOGLE_SHEETS_KEY_JSON is required for --google-sheet; no write is performed"
        )
    try:
        info = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise InventoryError("GOOGLE_SHEETS_KEY_JSON is invalid JSON") from exc
    try:
        import gspread
        from google.oauth2.service_account import Credentials
    except ImportError as exc:
        raise InventoryError(
            "gspread and google-auth are required for --google-sheet"
        ) from exc
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets.readonly",
        "https://www.googleapis.com/auth/drive.readonly",
    ]
    credentials = Credentials.from_service_account_info(info, scopes=scopes)
    return gspread.authorize(credentials)


def _read_google_sheet() -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    client = _gspread_client()
    spreadsheet = client.open_by_key(FEED_ID)
    feed_values = spreadsheet.worksheet(FEED_TAB).get_all_values()
    override_values = spreadsheet.worksheet(OVERRIDE_TAB).get_all_values()
    return _normalize_rows(feed_values), _normalize_rows(override_values)


def parse_product_id(product_id: str) -> dict[str, str]:
    parts = product_id.split("_")
    salon_id = parts[0] if parts and parts[0].isdigit() else ""
    stylist_id = ""
    post_id = ""
    creative_subject = ""
    if salon_id and len(parts) >= 2:
        if len(parts) >= 3 and parts[1].isdigit() and parts[2].startswith("01"):
            stylist_id = parts[1]
            post_id = parts[2]
            creative_subject = "stylist"
        elif parts[1].startswith("01"):
            post_id = parts[1]
            creative_subject = "salon"
    return {
        "salon_id": salon_id,
        "stylist_id": stylist_id,
        "post_id": post_id,
        "creative_subject": creative_subject,
    }


def _classify(row: dict[str, str], parsed: dict[str, str]) -> tuple[str, str]:
    availability = row.get("availability", "").lower()
    if availability == "out of stock":
        return "excluded_out_of_stock", "availability=out of stock"
    if availability != "in stock":
        return "data_hold", f"unexpected availability={availability!r}"
    missing = []
    if not parsed["salon_id"] or not parsed["post_id"]:
        missing.append("product_id_mapping")
    if not row.get("link"):
        missing.append("landing_url")
    if not row.get("image_link"):
        missing.append("image_link")
    if not row.get("address.city"):
        missing.append("address.city")
    if not row.get("address.region"):
        missing.append("address.region")
    if missing:
        return "data_hold", "missing:" + ",".join(missing)
    return "source_pending", "person source and canonical copy not selected"


def build_snapshot(
    feed_rows: list[dict[str, str]],
    override_rows: list[dict[str, str]],
    snapshot_at: str,
    source: str,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    override_map = {
        row["id"]: row for row in override_rows if row.get("id")
    }
    inventory_rows = []
    salons: set[str] = set()
    counts: dict[str, int] = {}
    subject_counts: dict[str, int] = {}
    for row in feed_rows:
        product_id = row.get("id", "")
        parsed = parse_product_id(product_id)
        status, reason = _classify(row, parsed)
        counts[status] = counts.get(status, 0) + 1
        if status != "excluded_out_of_stock" and parsed["salon_id"]:
            salons.add(parsed["salon_id"])
        subject = parsed["creative_subject"] or "unknown"
        if status != "excluded_out_of_stock":
            subject_counts[subject] = subject_counts.get(subject, 0) + 1
        inventory_rows.append(
            {
                "snapshot_at": snapshot_at,
                "product_id": product_id,
                "salon_id": parsed["salon_id"],
                "stylist_id": parsed["stylist_id"],
                "post_id": parsed["post_id"],
                "creative_subject": parsed["creative_subject"],
                "availability": row.get("availability", ""),
                "landing_url": row.get("link", ""),
                "current_image_url": row.get("image_link", ""),
                "current_override_url": (
                    override_map.get(product_id, {}).get("image_link", "")
                ),
                # title is retained only as reference. It is not canonical name.
                "feed_title_reference": row.get("title", ""),
                "canonical_salon_name": "",
                "canonical_name_status": "pending_lookup",
                "area_city": row.get("address.city", ""),
                "area_region": row.get("address.region", ""),
                "street_address": row.get("address.street_address", ""),
                "appeal_copy_source": row.get("description", ""),
                "item_group_id": row.get("item_group_id", ""),
                "eligibility_status": status,
                "hold_reason": reason,
                "rollout_batch": "",
            }
        )

    feed_hash = _sha256_bytes(_canonical_bytes(feed_rows))
    inventory = {
        "schema_version": INVENTORY_SCHEMA,
        "snapshot_at": snapshot_at,
        "source": source,
        "feed_sha256": feed_hash,
        "rows": inventory_rows,
    }
    override_snapshot = {
        "schema_version": OVERRIDE_SCHEMA,
        "snapshot_at": snapshot_at,
        "source": source,
        "rows": [
            {
                "id": row.get("id", ""),
                "image_link": row.get("image_link", ""),
                "hash": row.get("hash", ""),
                "title": row.get("title", ""),
                "srow": row.get("srow", ""),
                "note": row.get("note", ""),
            }
            for row in override_rows
            if row.get("id")
        ],
    }
    active_count = sum(
        count
        for status, count in counts.items()
        if status != "excluded_out_of_stock"
    )
    active_override_count = sum(
        bool(row["current_override_url"])
        for row in inventory_rows
        if row["eligibility_status"] != "excluded_out_of_stock"
    )
    summary = {
        "schema_version": "hairbook.catalog_static_inventory_summary.v1",
        "snapshot_at": snapshot_at,
        "source": source,
        "feed_sha256": feed_hash,
        "feed_rows_with_id": len(feed_rows),
        "active_products": active_count,
        "active_unique_salons": len(salons),
        "active_subject_counts": subject_counts,
        "status_counts": counts,
        "override_rows": len(override_snapshot["rows"]),
        "active_products_with_override": active_override_count,
        "active_products_without_override": active_count - active_override_count,
        "canonical_name_note": (
            "feed title is not used as canonical salon name; dedicated lookup remains pending"
        ),
    }
    return inventory, override_snapshot, summary


def _write_inventory_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        raise InventoryError("cannot write an empty inventory")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Create a read-only HB_02 static creative inventory snapshot."
    )
    source_group = parser.add_mutually_exclusive_group(required=True)
    source_group.add_argument("--input-csv", type=Path)
    source_group.add_argument("--google-sheet", action="store_true")
    parser.add_argument("--override-csv", type=Path)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument(
        "--snapshot-at",
        default="",
        help="ISO-8601 timestamp. Defaults to current UTC time.",
    )
    args = parser.parse_args()

    snapshot_at = args.snapshot_at or datetime.now(timezone.utc).isoformat()
    if args.google_sheet:
        feed_rows, override_rows = _read_google_sheet()
        source = f"google-sheet:{FEED_ID}/{FEED_TAB}"
    else:
        feed_rows = _read_csv(args.input_csv)
        override_rows = (
            _read_csv(args.override_csv) if args.override_csv else []
        )
        source = f"csv:{args.input_csv.resolve()}"

    inventory, override_snapshot, summary = build_snapshot(
        feed_rows,
        override_rows,
        snapshot_at,
        source,
    )
    args.output_dir.mkdir(parents=True, exist_ok=True)
    _write_json(args.output_dir / "inventory.json", inventory)
    _write_inventory_csv(args.output_dir / "inventory.csv", inventory["rows"])
    _write_json(
        args.output_dir / "thumbnail_override_snapshot.json",
        override_snapshot,
    )
    _write_json(args.output_dir / "summary.json", summary)
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    main()
