from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

THUMBGEN = Path(__file__).resolve().parents[1]
if str(THUMBGEN) not in sys.path:
    sys.path.insert(0, str(THUMBGEN))

import creative_batch


def publish_manifest(previous_override: dict | None = None) -> dict:
    return {
        "schema_version": creative_batch.PUBLISH_SCHEMA,
        "mode": "production",
        "status": "ready_to_publish",
        "account_scope": "HB_02",
        "batch_id": "unit-test-batch",
        "rollout_scope": "pilot",
        "entries": [
            {
                "product_id": "61_01TEST",
                "salon_id": "61",
                "asset_id": "asset-61",
                "design_version": "person_v3_layered_v1",
                "render_mode": "complete_banner",
                "new_image_url": "https://example.com/asset-61.jpg",
                "new_image_sha256": "a" * 64,
                "previous_override": previous_override or {},
            }
        ],
    }


class FakeWorksheet:
    def __init__(self, values: list[list[str]], row_count: int = 50):
        self.values = [list(row) for row in values]
        self.row_count = row_count

    def get_all_values(self):
        while self.values and not any(self.values[-1]):
            self.values.pop()
        return [list(row) for row in self.values]

    def add_rows(self, count: int):
        self.row_count += count

    def _ensure_row(self, row_number: int):
        while len(self.values) < row_number:
            self.values.append([])

    def batch_update(self, updates, value_input_option=None):
        del value_input_option
        for update in updates:
            row_number = int(update["range"].split(":")[0][1:])
            self._ensure_row(row_number)
            self.values[row_number - 1] = list(update["values"][0])

    def update(self, values, range_name, value_input_option=None):
        del value_input_option
        row_number = int(range_name.split(":")[0][1:])
        for offset, row in enumerate(values):
            self._ensure_row(row_number + offset)
            self.values[row_number + offset - 1] = list(row)

    def append_rows(self, rows, value_input_option=None):
        del value_input_option
        self.values.extend([list(row) for row in rows])


class FakeSpreadsheet:
    def __init__(self, override: FakeWorksheet):
        self.worksheets = {creative_batch.OVERRIDE_TAB: override}

    def worksheet(self, title: str):
        if title not in self.worksheets:
            raise RuntimeError("worksheet missing")
        return self.worksheets[title]

    def add_worksheet(self, title: str, rows: int, cols: int):
        del cols
        worksheet = FakeWorksheet([], row_count=rows)
        self.worksheets[title] = worksheet
        return worksheet


class FakeClient:
    def __init__(self, spreadsheet: FakeSpreadsheet):
        self.spreadsheet = spreadsheet

    def open_by_key(self, spreadsheet_id: str):
        self.last_spreadsheet_id = spreadsheet_id
        return self.spreadsheet


class CreativeBatchTest(unittest.TestCase):
    def test_plan_rejects_override_changed_after_preflight(self):
        manifest = publish_manifest()
        snapshot = {
            "schema_version": creative_batch.OVERRIDE_SCHEMA,
            "rows": [
                {
                    "id": "61_01TEST",
                    "image_link": "https://example.com/unexpected.jpg",
                    "hash": "",
                    "title": "",
                    "srow": "",
                    "note": "",
                }
            ],
        }
        with self.assertRaises(creative_batch.BatchError):
            creative_batch.make_execution_plan(manifest, snapshot)

    def test_full_coverage_requires_publish_or_documented_hold(self):
        manifest = publish_manifest()
        inventory = {
            "schema_version": creative_batch.INVENTORY_SCHEMA,
            "rows": [
                {
                    "product_id": "61_01TEST",
                    "eligibility_status": "source_pending",
                },
                {
                    "product_id": "67_01HOLD",
                    "eligibility_status": "person_source_hold",
                },
            ],
        }
        with self.assertRaises(creative_batch.BatchError):
            creative_batch.validate_full_coverage(manifest, inventory)
        manifest["excluded_products"] = [
            {"product_id": "67_01HOLD", "reason": "person_source_hold"}
        ]
        coverage = creative_batch.validate_full_coverage(manifest, inventory)
        self.assertEqual(coverage["active_products"], 2)
        self.assertEqual(coverage["publish_products"], 1)
        self.assertEqual(coverage["held_products"], 1)

    def test_apply_and_later_batch_rollback_restore_previous_override(self):
        previous = {
            "id": "61_01TEST",
            "image_link": "https://example.com/old.jpg",
            "hash": "old-hash",
            "title": "old title",
            "srow": "12",
            "note": "old note",
        }
        manifest = publish_manifest(previous)
        override = FakeWorksheet(
            [creative_batch.OVERRIDE_HEADERS, list(previous.values())]
        )
        spreadsheet = FakeSpreadsheet(override)
        client = FakeClient(spreadsheet)
        confirmation = creative_batch.canonical_sha256(manifest)

        with tempfile.TemporaryDirectory() as raw:
            output = Path(raw)
            result = creative_batch.apply_manifest(
                manifest,
                confirmation,
                "unit-test-publisher",
                output / "apply",
                client=client,
            )
            self.assertEqual(result["status"], "published")
            current = creative_batch.values_to_override_rows(
                override.get_all_values()
            )[0]
            self.assertEqual(
                current["image_link"],
                "https://example.com/asset-61.jpg",
            )
            self.assertTrue(
                (output / "apply" / "thumbnail_override_before.json").exists()
            )

            rolled_back = creative_batch.rollback_batch(
                "unit-test-batch",
                "unit-test-batch",
                "unit-test-publisher",
                "unit test",
                output / "rollback",
                client=client,
            )
            self.assertEqual(rolled_back["status"], "rolled_back")
            restored = creative_batch.values_to_override_rows(
                override.get_all_values()
            )[0]
            self.assertEqual(restored, previous)
            events = spreadsheet.worksheet(
                creative_batch.EVENT_TAB
            ).get_all_values()
            self.assertEqual(events[1][2], "publish")
            self.assertEqual(events[2][2], "rollback")

    def test_wrong_confirmation_never_writes(self):
        manifest = publish_manifest()
        override = FakeWorksheet([creative_batch.OVERRIDE_HEADERS])
        spreadsheet = FakeSpreadsheet(override)
        client = FakeClient(spreadsheet)
        with tempfile.TemporaryDirectory() as raw:
            with self.assertRaises(creative_batch.BatchError):
                creative_batch.apply_manifest(
                    manifest,
                    "0" * 64,
                    "unit-test-publisher",
                    Path(raw),
                    client=client,
                )
        self.assertEqual(override.get_all_values(), [creative_batch.OVERRIDE_HEADERS])


if __name__ == "__main__":
    unittest.main()
