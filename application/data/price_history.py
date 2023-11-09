from dataclasses import dataclass
from typing import List


@dataclass
class PriceHistory:
    dates: List[str]
    prices: List[float]
    current_price: float
    minimum_price: float
    maximum_price: float
    minimum_price_date: str = None
    maximum_price_date: str = None
