"""industry_fetcher のトラック割当ロジックの回帰テスト（ネットワーク不要）。"""

from __future__ import annotations

import unittest

from industry_fetcher import assign_track


class TestAssignTrack(unittest.TestCase):
    def setUp(self) -> None:
        self.order = ["aam", "intl_oem", "jp_oem"]
        self.tracks = {
            "jp_oem": {"include": ["三菱重工", "IHI"]},
            "intl_oem": {"include": ["Boeing", "エアバス"]},
            "aam": {"include": ["Joby", "SkyDrive", "eVTOL"]},
        }

    def test_aam_wins_over_boeing(self) -> None:
        text = "Joby と Boeing の提携\n概要"
        self.assertEqual(assign_track(text, self.order, self.tracks), "aam")

    def test_intl_when_no_aam(self) -> None:
        text = "エアバスが新機材を発表"
        self.assertEqual(assign_track(text, self.order, self.tracks), "intl_oem")

    def test_jp_oem_last(self) -> None:
        text = "三菱重工の航空部門"
        self.assertEqual(assign_track(text, self.order, self.tracks), "jp_oem")

    def test_no_match(self) -> None:
        text = "空港ラウンジの話題のみ"
        self.assertIsNone(assign_track(text, self.order, self.tracks))


if __name__ == "__main__":
    unittest.main()
