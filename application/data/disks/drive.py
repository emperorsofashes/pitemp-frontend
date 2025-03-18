import datetime
from dataclasses import dataclass


@dataclass
class Drive:
    timestamp: datetime.datetime
    drive_letter: str
    capacity_bytes: int
    free_bytes: int
    used_bytes: int

    @property
    def percent_used(self):
        return (self.used_bytes / self.capacity_bytes) * 100 if self.capacity_bytes > 0 else 0.0
