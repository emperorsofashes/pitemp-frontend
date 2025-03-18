from dataclasses import dataclass
from typing import List


@dataclass
class Temperatures:
    dates: List[str]
    temperatures: List[float]
