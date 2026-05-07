"""External data connectors.

각 connector는 환경변수로 API 키를 받고, 키가 없으면 sample data로 fallback.
"""

from .repository import FinancialsRepository
from .news import NewsConnector
from .commodities import CommodityConnector
from .price import PriceConnector
from .dart import DartConnector
from .live import LiveFinancials
from .naver_fundamentals import NaverFundamentals

__all__ = [
    "FinancialsRepository",
    "NewsConnector",
    "CommodityConnector",
    "PriceConnector",
    "DartConnector",
    "LiveFinancials",
    "NaverFundamentals",
]
