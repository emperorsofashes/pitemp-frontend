from dataclasses import dataclass
from datetime import datetime


@dataclass
class Brewery:
    id: str
    name: str
    type: str
    full_location: str
    country: str
    num_checkins: int
    num_checkins_with_ratings: int
    avg_rating: float
    first_checkin: datetime
