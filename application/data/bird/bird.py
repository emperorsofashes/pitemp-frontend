from dataclasses import dataclass
from datetime import datetime


@dataclass
class Bird:
    id: str
    scientific_name: str
    common_name: str
    birdnet_id: str | None
    ebird_id: str | None
    inat_id: str | None
    gbif_id: str | None
    avibase_id: str | None
    birdlife_id: str | None
    ncbi_id: str | None
    group: str | None
    order: str | None
    family: str | None
    genus: str | None
    updated_at: datetime


@dataclass
class LifeListEntry:
    id: str
    bird_id: str
    scientific_name: str
    common_name: str
    date_sighted: datetime
    notes: str | None = None
