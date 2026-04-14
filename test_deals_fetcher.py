"""deals_fetcher の日付抽出・文脈判定の回帰テスト（ネットワーク不要）。"""

from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone

from deals_fetcher import decide_status, find_end_mmdd

JST = timezone(timedelta(hours=9))


def _dt(year: int, month: int, day: int) -> datetime:
    return datetime(year, month, day, 12, 0, 0, tzinfo=JST)


class TestFindEndMmdd(unittest.TestCase):
    def test_solaseed_sale_line(self) -> None:
        text = """
        期間限定SALE！ソラシドスペシャル
        対象搭乗期間：2026年5月25日（月）～6月30日（火）
        予約・販売期間：2026年4月14日（火）0:00～4月21日（火）23:59
        """
        now = _dt(2026, 4, 14)
        self.assertEqual(find_end_mmdd(text, now), "04/21")

    def test_23_59_without_presale_line(self) -> None:
        text = "セール\n2026年4月14日（火）0:00～4月21日（火）23:59\nお支払い"
        now = _dt(2026, 4, 14)
        self.assertEqual(find_end_mmdd(text, now), "04/21")

    def test_slash_deadline(self) -> None:
        text = "春夏フェア 最大21%OFF 4/20（月）09:59まで"
        now = _dt(2026, 4, 14)
        self.assertEqual(find_end_mmdd(text, now), "04/20")

    def test_boarding_period_not_preferred(self) -> None:
        text = """
        対象搭乗期間：2026年5月25日（月）～6月30日（火）
        予約はお早めに
        """
        now = _dt(2026, 4, 14)
        self.assertEqual(find_end_mmdd(text, now), "")


class TestDecideStatus(unittest.TestCase):
    def test_solaseed_title_active(self) -> None:
        title = "ソラシドスペシャル｜運賃情報｜ソラシドエア"
        body = "期間限定SALE"
        now = _dt(2026, 4, 14)
        self.assertEqual(decide_status(title, "04/21", body, now), "active")

    def test_past_end_none(self) -> None:
        title = "タイムセール"
        now = _dt(2026, 6, 1)
        self.assertEqual(decide_status(title, "04/21", "セール", now), "none")


if __name__ == "__main__":
    unittest.main()
