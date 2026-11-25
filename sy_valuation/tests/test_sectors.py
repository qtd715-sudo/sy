"""섹터 판별 테스트.

    python -m unittest sy_valuation.tests.test_sectors
"""
import unittest

from sy_valuation.data_sources.naver_sectors import sector_from_naver, NAVER_INDUSTRY_TO_SECTOR
from sy_valuation.data_sources.repository import FinancialsRepository


class SectorTest(unittest.TestCase):
    def test_naver_industry_mapping(self):
        self.assertEqual(sector_from_naver("287"), "IT서비스")   # 소프트웨어 (엠로)
        self.assertEqual(sector_from_naver(278), "반도체")
        self.assertEqual(sector_from_naver("279"), "")           # 건설 — 맞는 섹터 없음 → 매핑 안 함
        self.assertEqual(sector_from_naver(""), "")
        self.assertEqual(sector_from_naver(None), "")

    def test_every_mapped_sector_has_multiples(self):
        table = FinancialsRepository().sector_table()
        self.assertTrue(set(NAVER_INDUSTRY_TO_SECTOR.values()) <= set(table))

    def test_fine_label_uses_parent_multiples(self):
        repo = FinancialsRepository()
        self.assertEqual(repo.sector_multiples("응용SW"), repo.sector_multiples("IT서비스"))
        self.assertTrue(repo.sector_multiples("IT서비스"))
        self.assertEqual(repo.sector_multiples("기타"), {})
        self.assertEqual(repo.sector_multiples("없는섹터"), {})


if __name__ == "__main__":
    unittest.main()
