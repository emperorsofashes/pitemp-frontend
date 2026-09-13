from dataclasses import dataclass
from datetime import datetime
from application.constants.bird_constants import BIRD_IMAGE_HOST


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

    def get_thumb_url(self) -> str | None:
        """Get the thumbnail URL for this bird"""
        if not BIRD_IMAGE_HOST:
            return None
        # Convert common name to lowercase and replace spaces with underscores
        species_name = self.scientific_name.lower().replace(" ", "_")
        return f"{BIRD_IMAGE_HOST}/{species_name}_thumb.avif"

    def get_full_image_url(self) -> str | None:
        """Get the full image URL for this bird"""
        if not BIRD_IMAGE_HOST:
            return None
        # Convert common name to lowercase and replace spaces with underscores
        species_name = self.scientific_name.lower().replace(" ", "_")
        return f"{BIRD_IMAGE_HOST}/{species_name}.avif"


@dataclass
class LifeListEntry:
    id: str
    bird_id: str
    scientific_name: str
    common_name: str
    date_sighted: datetime
    notes: str | None = None
    thumb_url: str | None = None
    full_image_url: str | None = None
