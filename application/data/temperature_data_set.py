from dataclasses import dataclass
from typing import List, Dict


@dataclass
class TemperatureDataSet:
    label: str
    data: List[Dict]
    current_temp: float
    minimum_temp: float
    maximum_temp: float
