"""Read/export the maintained scenario. Business assumptions live in JSON, once."""

import argparse
import copy
import json
from pathlib import Path

from ..resources import PROJECT_ROOT

TEMPLATE = (
    PROJECT_ROOT / "docs/mock-design/examples/scenarios/upgraded-linked-2026.json"
)


class UpgradedScenario:
    def __init__(self, year=2026, category_id=None):
        if year != 2026:
            raise ValueError(
                "Lịch hiện hành dành cho 2026; hãy cấu hình lịch năm mới rõ ràng."
            )
        self.year = year

    def build(self):
        return copy.deepcopy(json.loads(TEMPLATE.read_text()))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if args.output.resolve() == TEMPLATE.resolve():
        parser.error("Không ghi đè nguồn cấu hình chính; chọn file xuất riêng.")
    args.output.write_text(
        json.dumps(UpgradedScenario().build(), ensure_ascii=False, indent=2) + "\n"
    )


if __name__ == "__main__":
    main()
