from __future__ import annotations

import sys

from one_piece_missing import (
    run_all,
    run_big_bang,
    run_knightly,
    run_marvellous,
    run_tanuki,
)


RUNNERS = {
    "all": run_all,
    "bigbang": run_big_bang,
    "bigbangshop": run_big_bang,
    "knightly": run_knightly,
    "knightlygaming": run_knightly,
    "marvellous": run_marvellous,
    "marvelloushobbies": run_marvellous,
    "tanuki": run_tanuki,
    "tanukitrader": run_tanuki,
}


def main() -> int:
    store = sys.argv[1].lower().replace("-", "").replace("_", "") if len(sys.argv) > 1 else "all"
    runner = RUNNERS.get(store)
    if runner is None:
        choices = "all, bigbang, knightly, marvellous, tanuki"
        print(f"Unknown store {sys.argv[1]!r}. Use one of: {choices}", file=sys.stderr)
        return 2

    runner()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
