from __future__ import annotations

import sys
import unittest
from pathlib import Path


REPO_DIR = Path(__file__).resolve().parents[2]
sys.path.append(str(REPO_DIR / "services" / "one_piece"))

from notify_new_cards import diff_rows, filter_alert_additions
from one_piece_missing import is_don_title, match_knightly, normalize_card_number, searched_card_number
from scrape_collection import normalize_set_code


class HourlyNotificationTests(unittest.TestCase):
    def test_only_new_op_eb_and_don_cards_strictly_under_r100_are_alerted(self) -> None:
        rows = [
            {"card_number": "OP16-001", "price": "99.99"},
            {"card_number": "EB03-001", "price": "50"},
            {"card_number": "ST01-001", "price": "20"},
            {"card_number": "OP16-002", "price": "100"},
            {"card_number": "OP16-003", "price": "unknown"},
            {"card_number": "DON!!", "title": "Monkey D. Luffy DON!! Card", "price": "45"},
            {"card_number": "", "title": "Special DON Card", "price": "25"},
            {"card_number": "", "title": "London promo", "price": "10"},
        ]

        self.assertEqual(
            ["OP16-001", "EB03-001", "DON!!", ""],
            [row["card_number"] for row in filter_alert_additions(rows, 100)],
        )

    def test_price_updates_and_removals_are_not_additions(self) -> None:
        previous = [
            {"card_number": "OP16-001", "store": "Shop", "url": "one", "price": "120"},
            {"card_number": "EB03-001", "store": "Shop", "url": "removed", "price": "20"},
        ]
        today = [
            {"card_number": "OP16-001", "store": "Shop", "url": "one", "price": "90"},
            {"card_number": "OP16-002", "store": "Shop", "url": "two", "price": "80"},
        ]

        additions, _changes = diff_rows(today, previous)
        self.assertEqual(["OP16-002"], [row["card_number"] for row in additions])

    def test_op16_is_a_supported_workbook_card_number(self) -> None:
        self.assertEqual("OP16-001", normalize_card_number("OP16-1"))
        self.assertEqual("OP16-123", normalize_card_number("OP-16-123"))
        self.assertEqual("OP16", normalize_set_code("OP16"))

    def test_don_titles_are_searched_without_being_in_the_workbook(self) -> None:
        self.assertTrue(is_don_title("Nami DON!! Card"))
        self.assertTrue(is_don_title("Special Don Card"))
        self.assertFalse(is_don_title("London promo"))
        self.assertFalse(is_don_title("Don't Worry!! I'm Here!!"))
        self.assertFalse(is_don_title("Don Accino"))
        self.assertEqual("DON!!", searched_card_number(None, "Nami DON!! Card", set()))

    def test_store_matcher_scrapes_don_card_without_workbook_entry(self) -> None:
        products = [{
            "title": "Monkey D. Luffy DON!! Card",
            "body_html": "",
            "handle": "luffy-don-card",
            "variants": [{"available": True, "price": "75", "title": "Near Mint"}],
            "images": [],
        }]

        matches = match_knightly(set(), products)
        self.assertEqual(1, len(matches))
        self.assertEqual("DON!!", matches[0]["card_number"])


if __name__ == "__main__":
    unittest.main()
