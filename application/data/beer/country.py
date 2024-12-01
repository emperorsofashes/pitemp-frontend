from dataclasses import dataclass
from datetime import datetime


@dataclass
class Country:
    name: str
    num_breweries: int
    num_checkins: int
    avg_rating: float
    first_checkin: datetime
