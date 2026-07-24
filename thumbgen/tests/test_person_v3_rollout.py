from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from PIL import Image

THUMBGEN = Path(__file__).resolve().parents[1]
REPO = THUMBGEN.parent
if str(THUMBGEN) not in sys.path:
    sys.path.insert(0, str(THUMBGEN))

import creative_inventory
import creative_rollout
import enrich
import fetch_person_v3_sources
import person_v3


SAMPLE_MANIFEST = (
    REPO / "dashboard" / "source_images" / "person_v3_manifest.sample.json"
)


class PersonV3RendererTest(unittest.TestCase):
    def test_render_and_qa_sample_manifest(self):
        with tempfile.TemporaryDirectory() as raw:
            output = Path(raw)
            index = person_v3.render_manifest(SAMPLE_MANIFEST, output)
            self.assertEqual(len(index["assets"]), 3)
            for record in index["assets"]:
                with Image.open(record["output_path"]) as image:
                    self.assertEqual(image.size, (1080, 1350))
                    self.assertEqual(image.format, "JPEG")
                    self.assertEqual(len(image.getexif()), 0)
                with Image.open(record["preview_path"]) as preview:
                    self.assertEqual(preview.size, (360, 450))

            qa_path = output / "qa.json"
            qa = creative_rollout.run_qa(
                SAMPLE_MANIFEST,
                output / "render_index.json",
                qa_path,
            )
            self.assertEqual(qa["overall_status"], "pass")
            self.assertEqual(qa["summary"]["pass"], 3)

    def test_manifest_rejects_unknown_theme(self):
        manifest = json.loads(SAMPLE_MANIFEST.read_text(encoding="utf-8"))
        manifest["assets"][0]["theme"] = "unknown"
        with tempfile.TemporaryDirectory() as raw:
            path = Path(raw) / "manifest.json"
            path.write_text(
                json.dumps(manifest, ensure_ascii=False),
                encoding="utf-8",
            )
            with self.assertRaises(person_v3.ManifestError):
                person_v3.load_manifest(path)


class PersonV3SourceFetchTest(unittest.TestCase):
    def _manifest_with_local_image(
        self,
        directory: Path,
        source_path: str = "private/source.jpg",
    ) -> Path:
        source = directory / "private" / "source.jpg"
        source.parent.mkdir(parents=True)
        Image.new("RGB", (720, 900), "#887766").save(source, "JPEG")
        manifest = {
            "schema_version": person_v3.SCHEMA_VERSION,
            "design_version": person_v3.DESIGN_VERSION,
            "assets": [
                {
                    "asset_id": "source-fetch-test",
                    "source": {
                        "path": source_path,
                        "image_url": "https://example.com/source.jpg",
                        "sha256": person_v3.sha256_file(source),
                    },
                    "copy": {
                        "area": "大阪・梅田",
                        "salon_name": "テストサロン",
                        "access": ["大阪駅 徒歩5分"],
                        "headline": ["似合わせスタイル"],
                        "cta": "詳しく見る",
                    },
                }
            ],
        }
        path = directory / "manifest.json"
        path.write_text(
            json.dumps(manifest, ensure_ascii=False),
            encoding="utf-8",
        )
        return path

    def test_existing_source_is_hash_and_decode_verified(self):
        with tempfile.TemporaryDirectory() as raw:
            manifest = self._manifest_with_local_image(Path(raw))
            report = fetch_person_v3_sources.fetch_manifest_sources(manifest)
            self.assertEqual(report["count"], 1)
            self.assertEqual(report["verified_existing"], 1)
            self.assertEqual(report["downloaded"], 0)
            self.assertEqual(report["results"][0]["width"], 720)
            self.assertEqual(report["results"][0]["height"], 900)

    def test_source_path_cannot_escape_manifest_directory(self):
        with tempfile.TemporaryDirectory() as raw:
            directory = Path(raw)
            manifest = self._manifest_with_local_image(
                directory,
                "../outside.jpg",
            )
            parsed = person_v3.load_manifest(manifest)
            with self.assertRaises(fetch_person_v3_sources.SourceFetchError):
                fetch_person_v3_sources._target_path(
                    manifest,
                    parsed["assets"][0],
                )


class CreativeRolloutTest(unittest.TestCase):
    def test_dry_run_preflight_builds_publish_and_rollback_manifests(self):
        with tempfile.TemporaryDirectory() as raw:
            output = Path(raw)
            person_v3.render_manifest(SAMPLE_MANIFEST, output)
            qa_path = output / "qa.json"
            creative_rollout.run_qa(
                SAMPLE_MANIFEST,
                output / "render_index.json",
                qa_path,
            )
            review_path = output / "review.json"
            review = creative_rollout.init_review(
                SAMPLE_MANIFEST,
                output / "render_index.json",
                qa_path,
                review_path,
            )
            for asset in review["assets"]:
                asset["decision"] = "approved_for_dry_run"
                asset["reviewer"] = "unit-test-reviewer"
                asset["reviewed_at"] = "2026-07-24T00:00:00+00:00"
                asset["checklist"] = {
                    key: True for key, _ in creative_rollout.MANUAL_CHECKS
                }
            creative_rollout._write_json(review_path, review)

            snapshot_path = output / "override.json"
            creative_rollout._write_json(
                snapshot_path,
                {
                    "schema_version": creative_rollout.OVERRIDE_SNAPSHOT_SCHEMA,
                    "snapshot_at": "2026-07-24T00:00:00+00:00",
                    "source": "unit-test",
                    "rows": [],
                },
            )
            report = creative_rollout.run_preflight(
                SAMPLE_MANIFEST,
                output / "render_index.json",
                qa_path,
                review_path,
                snapshot_path,
                output / "preflight",
                dry_run=True,
                check_urls=False,
            )
            self.assertEqual(report["status"], "dry_run_ready")
            self.assertTrue((output / "preflight" / "publish_manifest.json").exists())
            self.assertTrue((output / "preflight" / "rollback_manifest.json").exists())

    def test_pending_human_review_blocks_preflight(self):
        with tempfile.TemporaryDirectory() as raw:
            output = Path(raw)
            person_v3.render_manifest(SAMPLE_MANIFEST, output)
            qa_path = output / "qa.json"
            creative_rollout.run_qa(
                SAMPLE_MANIFEST,
                output / "render_index.json",
                qa_path,
            )
            review_path = output / "review.json"
            creative_rollout.init_review(
                SAMPLE_MANIFEST,
                output / "render_index.json",
                qa_path,
                review_path,
            )
            snapshot_path = output / "override.json"
            creative_rollout._write_json(
                snapshot_path,
                {
                    "schema_version": creative_rollout.OVERRIDE_SNAPSHOT_SCHEMA,
                    "snapshot_at": "2026-07-24T00:00:00+00:00",
                    "source": "unit-test",
                    "rows": [],
                },
            )
            report = creative_rollout.run_preflight(
                SAMPLE_MANIFEST,
                output / "render_index.json",
                qa_path,
                review_path,
                snapshot_path,
                output / "preflight",
                dry_run=True,
                check_urls=False,
            )
            self.assertEqual(report["status"], "fail")


class CreativeInventoryTest(unittest.TestCase):
    def test_inventory_classifies_active_and_out_of_stock(self):
        feed = [
            {
                "id": "61_01KT8YQ8NH1XW5AQA7X2N7NJ3Z",
                "title": "reference only",
                "availability": "in stock",
                "link": "https://hairbook.jp/salons/61/",
                "image_link": "https://hairbook.jp/thumbnail/Post/01KT8YQ8NH1XW5AQA7X2N7NJ3Z",
                "address.city": "大阪市北区",
                "address.region": "大阪府",
            },
            {
                "id": "67_1234_01KPGEDY7PBGSHYWATKYJNWAC6",
                "title": "reference only",
                "availability": "out of stock",
                "link": "https://hairbook.jp/staffs/1234/",
                "image_link": "https://hairbook.jp/thumbnail/Post/01KPGEDY7PBGSHYWATKYJNWAC6",
                "address.city": "豊島区",
                "address.region": "東京都",
            },
        ]
        inventory, snapshot, summary = creative_inventory.build_snapshot(
            feed,
            [],
            "2026-07-24T00:00:00+00:00",
            "unit-test",
        )
        self.assertEqual(summary["active_products"], 1)
        self.assertEqual(summary["active_unique_salons"], 1)
        self.assertEqual(
            inventory["rows"][0]["eligibility_status"],
            "source_pending",
        )
        self.assertEqual(
            inventory["rows"][1]["eligibility_status"],
            "excluded_out_of_stock",
        )
        self.assertEqual(snapshot["rows"], [])


class EnrichCompleteBannerTest(unittest.TestCase):
    def test_complete_banner_skips_overlay_after_hash_and_approval_check(self):
        with tempfile.TemporaryDirectory() as raw:
            temp = Path(raw)
            render_dir = temp / "render"
            index = person_v3.render_manifest(
                SAMPLE_MANIFEST,
                render_dir,
                only={"fier-osaka-umeda-person-v3"},
            )
            record = index["assets"][0]
            config_path = temp / "creative_config.json"
            config_path.write_text(
                json.dumps(
                    {
                        "test-product": {
                            "source": "edited_banner",
                            "source_url": record["output_path"],
                            "source_params": {
                                "asset_id": record["asset_id"],
                                "asset_version": 1,
                                "render_mode": "complete_banner",
                                "approval_status": "approved_for_dry_run",
                                "asset_sha256": record["output_sha256"],
                            },
                        }
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            with mock.patch.object(
                enrich,
                "worklist_dry",
                return_value=[
                    {
                        "id": "test-product",
                        "salon": "ignored",
                        "area": "ignored",
                        "image_link": record["output_path"],
                    }
                ],
            ), mock.patch.object(enrich, "ENRICHED", temp / "enriched"):
                result = enrich.run(
                    dry_run=True,
                    limit=0,
                    rollout=1.0,
                    design="bottom_scrim",
                    config_path=config_path,
                )
            self.assertEqual(result["meta"]["counts"]["complete_banner"], 1)
            self.assertEqual(result["results"][0]["action"], "complete_banner")
            self.assertEqual(result["results"][0]["render_mode"], "complete_banner")


if __name__ == "__main__":
    unittest.main()
