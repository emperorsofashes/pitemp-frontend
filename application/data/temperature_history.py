from dataclasses import dataclass
from typing import List


@dataclass
class TemperatureHistory:
    dates: List[str]
    temperatures: List[float]
    current_temp: float
    minimum_temp: float
    maximum_temp: float
    minimum_temp_date: str = None
    maximum_temp_date: str = None
