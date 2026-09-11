"""
Put a bid code on every measurable item of an eTakeoff item-tree template.

    python backend/etakeoff_template.py "<Rev Template.itt>"                 # writes beside the template
    python backend/etakeoff_template.py "<Rev Template.itt>" --out-dir DIR

Writes three files named after the template:

    <name> - coded.itt        the template, byte for byte, with only the BidCode values filled
    <name> - bid codes.csv    code, description — paste into Dimension's Standard Bid Code List
    <name> - code review.md   what was kept, added, changed, and what to look at by hand

See docs/specs/etakeoff-bid-codes.md and app/services/etakeoff_template.py.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("path", help="the .itt template")
    ap.add_argument("--out-dir", help="where to write the three files (default: beside the template)")
    args = ap.parse_args()

    from app.services.etakeoff_template import mask_bid_codes, recode

    src = Path(args.path)
    text = src.read_text(encoding="utf-8", newline="")
    result = recode(text)
    assert mask_bid_codes(result.text) == mask_bid_codes(text), "only bid codes may change"

    out_dir = Path(args.out_dir) if args.out_dir else src.parent
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = src.stem
    coded = out_dir / f"{stem} - coded.itt"
    codes = out_dir / f"{stem} - bid codes.csv"
    review = out_dir / f"{stem} - code review.md"
    coded.write_text(result.text, encoding="utf-8", newline="")
    codes.write_text(result.bid_code_csv(), encoding="utf-8", newline="")
    review.write_text(result.review(src.name), encoding="utf-8", newline="\n")

    c = result.counts
    print(f"{src.name}: {len(result.items)} items; coded {len(result.coded())} "
          f"(kept {c.get('kept', 0)}, added {c.get('added', 0)}, changed {c.get('changed', 0)}); "
          f"cleared {c.get('cleared', 0)}; not measurable {c.get('skipped', 0)}")
    defects = result.defects()
    print(f"{len(defects)} items to look at:")
    for it in defects[:40]:
        print(f"  - {it.where}: {'; '.join(it.notes)}")
    if len(defects) > 40:
        print(f"  ... {len(defects) - 40} more in the review")
    print(f"\nwrote:\n  {coded}\n  {codes}\n  {review}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
