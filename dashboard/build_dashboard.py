"""Build the authenticated HB_02 creative rollout dashboard.

The page intentionally embeds no feed rows or private source metadata.  At
runtime it calls the authenticated ``/api/creative-status`` endpoint, which
joins the live catalog feed with persisted asset/review/publish state.
"""
from __future__ import annotations
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def main() -> None:
    html = (ROOT / "creative.rollout.template.html").read_text(
        encoding="utf-8"
    )
    out = ROOT / "creative.html"
    out.write_text(html, encoding="utf-8")
    print(f"wrote {out} ({len(html) / 1024:.0f} KB)")


if __name__ == "__main__":
    main()
