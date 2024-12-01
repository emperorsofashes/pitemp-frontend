from dataclasses import dataclass
from datetime import datetime


@dataclass
class Beer:
    name: str
    id: int
    brewery: str
    brewery_id: str
    rating: float
    style: str
    abv: float
    first_checkin: datetime
    country: str
