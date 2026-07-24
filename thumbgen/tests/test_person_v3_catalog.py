from __future__ import annotations

import sys
import unittest
from pathlib import Path


THUMBGEN = Path(__file__).resolve().parents[1]
if str(THUMBGEN) not in sys.path:
    sys.path.insert(0, str(THUMBGEN))

from build_person_v3_catalog import (  # noqa: E402
    PageInfo,
    _clean_salon_name,
    _headline_copy,
    _landing_key,
    _legacy_style_candidates,
)


def page_info(source_text: str) -> PageInfo:
    return PageInfo(
        landing_url="https://hairbook.jp/salons/1/",
        component="salon/pages/show",
        version="v1",
        salon_id="1",
        stylist_id="",
        salon_name="Example",
        location="表参道駅より徒歩3分",
        region="東京都",
        city="港区",
        nearest_stations=["表参道"],
        source_text=source_text,
        staff_name="",
        candidates=[],
    )


class PersonV3CatalogCopyTest(unittest.TestCase):
    def test_display_name_removes_reading_and_service_suffix(self) -> None:
        self.assertEqual(
            _clean_salon_name(
                "ROCAReTA kyoto 千本丸太町店 ヘッドスパ/髪質改善"
            ),
            "ROCAReTA kyoto 千本丸太町店",
        )
        self.assertEqual(
            _clean_salon_name("LUCK 辻堂【ラック】"),
            "LUCK 辻堂",
        )

    def test_category_copy_does_not_treat_hair_esthetic_as_body_esthetic(self) -> None:
        self.assertEqual(
            _headline_copy(page_info("PIM濃密ヘアエステ 髪質改善"), ""),
            ["髪のお悩みに寄り添う、", "扱いやすい美髪へ。"],
        )
        self.assertEqual(
            _headline_copy(page_info("深爪矯正ネイル"), ""),
            ["指先のお悩みに寄り添う、", "ネイルデザインをご提案。"],
        )
        self.assertEqual(
            _headline_copy(page_info("眉毛・まつ毛パーマ"), ""),
            ["目元の魅力を引き出す、", "似合わせデザイン。"],
        )


class PersonV3CatalogSourceTest(unittest.TestCase):
    def test_supported_hairbook_landing_domains(self) -> None:
        self.assertEqual(
            _landing_key("https://hairbook.jp/salons/61/?utm_source=meta"),
            "https://hairbook.jp/salons/61/",
        )
        self.assertEqual(
            _landing_key(
                "https://salonpage.hairbook.jp/salons/H000178303"
                "?utm_source=meta"
            ),
            "https://salonpage.hairbook.jp/salons/H000178303",
        )
        with self.assertRaises(Exception):
            _landing_key("https://example.com/salons/61/")

    def test_legacy_styles_use_existing_page_image_urls(self) -> None:
        candidates = _legacy_style_candidates(
            [
                {
                    "id": "L1",
                    "imageUrl": "https://imgbp.hotp.jp/style.jpg",
                    "styleUrl": "https://beauty.hotpepper.jp/style/L1.html",
                }
            ]
        )
        self.assertEqual(len(candidates), 1)
        self.assertEqual(
            candidates[0].source_type,
            "hairbook_salonpage_style_photo",
        )
        self.assertEqual(
            candidates[0].image_url,
            "https://imgbp.hotp.jp/style.jpg",
        )


if __name__ == "__main__":
    unittest.main()
