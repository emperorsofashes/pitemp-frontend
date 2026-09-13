from dataclasses import dataclass
from datetime import datetime


@dataclass(kw_only=True)
class BirdBase:
    id: str
    scientific_name: str
    common_name: str

    @property
    def thumb_url(self) -> str | None:
        if not self.scientific_name:
            return None
        slug = self.scientific_name.strip().lower().replace(" ", "_")
        return f"/birds/image/{slug}_thumb.avif"

    @property
    def full_image_url(self) -> str | None:
        if not self.scientific_name:
            return None
        slug = self.scientific_name.strip().lower().replace(" ", "_")
        return f"/birds/image/{slug}.avif"


@dataclass(kw_only=True)
class Bird(BirdBase):
    birdnet_id: str | None = None
    ebird_id: str | None = None
    inat_id: str | None = None
    gbif_id: str | None = None
    avibase_id: str | None = None
    birdlife_id: str | None = None
    ncbi_id: str | None = None
    group: str | None = None
    order: str | None = None
    family: str | None = None
    genus: str | None = None
    updated_at: datetime | None = None

    @classmethod
    def from_mongo(cls, doc: dict) -> "Bird":
        identifiers = doc.get("identifiers", {})
        taxonomy = doc.get("taxonomy", {})
        return cls(
            id=str(doc["_id"]),
            scientific_name=doc.get("scientific_name", ""),
            common_name=doc.get("common_name", ""),
            birdnet_id=identifiers.get("birdnet"),
            ebird_id=identifiers.get("ebird"),
            inat_id=identifiers.get("inat"),
            gbif_id=identifiers.get("gbif"),
            avibase_id=identifiers.get("avibase"),
            birdlife_id=identifiers.get("birdlife"),
            ncbi_id=identifiers.get("ncbi"),
            group=taxonomy.get("group"),
            order=taxonomy.get("order"),
            family=taxonomy.get("family"),
            genus=taxonomy.get("genus"),
            updated_at=doc.get("updated_at"),
        )


@dataclass(kw_only=True)
class LifeListEntry(BirdBase):
    bird_id: str
    date_sighted: datetime
    notes: str | None = None

    @classmethod
    def from_mongo(cls, doc: dict) -> "LifeListEntry":
        return cls(
            id=str(doc["_id"]),
            bird_id=doc.get("bird_id", ""),
            scientific_name=doc.get("scientific_name", ""),
            common_name=doc.get("common_name", ""),
            date_sighted=doc.get("date_sighted", datetime.now()),
            notes=doc.get("notes"),
        )
