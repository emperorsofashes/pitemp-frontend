import logging
import os
from datetime import datetime
from typing import Optional

from pymongo.collection import Collection
from pymongo.database import Database

from application.constants.bird_constants import (
    BIRD_DB_NAME,
    BIRDS_COLLECTION_NAME,
    LIFE_LIST_COLLECTION_NAME,
    BIRD_CACHE_TTL,
)
from application.data.bird.bird import Bird, LifeListEntry

LOG = logging.getLogger(__name__)


class BirdDao:
    def __init__(self, client, database: Database = None, cache=None):
        self.cache = cache
        self.client = client
        
        # If no database provided, connect to one
        if database is None:
            database: Database = self.client[BIRD_DB_NAME]

        # Set up database and collection variables
        self.database = database
        self.birds_collection: Collection = self.database[BIRDS_COLLECTION_NAME]
        self.life_list_collection: Collection = self.database[LIFE_LIST_COLLECTION_NAME]

        LOG.info(f"Connected to database: {BIRD_DB_NAME}")

    def get_all_birds(self) -> list[Bird]:
        """Get all bird species from the birds collection"""
        cache_key = "all_birds"
        
        if self.cache:
            serialized_birds = self.cache.get(cache_key)
            if serialized_birds:
                import pickle
                return pickle.loads(serialized_birds)

        documents = self.birds_collection.find()
        birds = []
        
        for document in documents:
            bird = Bird(
                id=str(document["_id"]),
                scientific_name=document.get("scientific_name", ""),
                common_name=document.get("common_name", ""),
                birdnet_id=document.get("identifiers", {}).get("birdnet"),
                ebird_id=document.get("identifiers", {}).get("ebird"),
                inat_id=document.get("identifiers", {}).get("inat"),
                gbif_id=document.get("identifiers", {}).get("gbif"),
                avibase_id=document.get("identifiers", {}).get("avibase"),
                birdlife_id=document.get("identifiers", {}).get("birdlife"),
                ncbi_id=document.get("identifiers", {}).get("ncbi"),
                group=document.get("taxonomy", {}).get("group"),
                order=document.get("taxonomy", {}).get("order"),
                family=document.get("taxonomy", {}).get("family"),
                genus=document.get("taxonomy", {}).get("genus"),
                updated_at=document.get("updated_at", datetime.now()),
            )
            birds.append(bird)

        if self.cache:
            import pickle
            serialized_data = pickle.dumps(birds)
            self.cache.set(cache_key, serialized_data, ex=BIRD_CACHE_TTL)

        return birds

    def get_life_list(self) -> list[LifeListEntry]:
        """Get all entries from the life list"""
        cache_key = "life_list"
        
        if self.cache:
            serialized_entries = self.cache.get(cache_key)
            if serialized_entries:
                import pickle
                return pickle.loads(serialized_entries)

        documents = self.life_list_collection.find()
        entries = []
        
        for document in documents:
            entry = LifeListEntry(
                id=str(document["_id"]),
                bird_id=document.get("bird_id", ""),
                scientific_name=document.get("scientific_name", ""),
                common_name=document.get("common_name", ""),
                date_sighted=document.get("date_sighted", datetime.now()),
                notes=document.get("notes"),
            )
            entries.append(entry)

        if self.cache:
            import pickle
            serialized_data = pickle.dumps(entries)
            self.cache.set(cache_key, serialized_data, ex=BIRD_CACHE_TTL)

        return entries

    def add_to_life_list(self, bird_id: str, scientific_name: str, common_name: str, 
                        date_sighted: datetime, notes: Optional[str] = None) -> str:
        """Add a bird to the life list"""
        document = {
            "bird_id": bird_id,
            "scientific_name": scientific_name,
            "common_name": common_name,
            "date_sighted": date_sighted,
            "notes": notes,
        }
        
        result = self.life_list_collection.insert_one(document)
        
        # Invalidate cache
        if self.cache:
            self.cache.delete("life_list")
        
        return str(result.inserted_id)

    def delete_from_life_list(self, entry_id: str) -> bool:
        """Delete an entry from the life list"""
        from bson import ObjectId
        result = self.life_list_collection.delete_one({"_id": ObjectId(entry_id)})
        
        # Invalidate cache
        if self.cache:
            self.cache.delete("life_list")
        
        return result.deleted_count > 0

    def search_birds(self, query: str) -> list[Bird]:
        """Search birds by common name or scientific name"""
        cache_key = f"bird_search_{query}"
        
        if self.cache:
            serialized_birds = self.cache.get(cache_key)
            if serialized_birds:
                import pickle
                return pickle.loads(serialized_birds)

        # Case-insensitive search on common_name and scientific_name
        documents = self.birds_collection.find({
            "$or": [
                {"common_name": {"$regex": query, "$options": "i"}},
                {"scientific_name": {"$regex": query, "$options": "i"}},
            ]
        })
        
        birds = []
        for document in documents:
            bird = Bird(
                id=str(document["_id"]),
                scientific_name=document.get("scientific_name", ""),
                common_name=document.get("common_name", ""),
                birdnet_id=document.get("identifiers", {}).get("birdnet"),
                ebird_id=document.get("identifiers", {}).get("ebird"),
                inat_id=document.get("identifiers", {}).get("inat"),
                gbif_id=document.get("identifiers", {}).get("gbif"),
                avibase_id=document.get("identifiers", {}).get("avibase"),
                birdlife_id=document.get("identifiers", {}).get("birdlife"),
                ncbi_id=document.get("identifiers", {}).get("ncbi"),
                group=document.get("taxonomy", {}).get("group"),
                order=document.get("taxonomy", {}).get("order"),
                family=document.get("taxonomy", {}).get("family"),
                genus=document.get("taxonomy", {}).get("genus"),
                updated_at=document.get("updated_at", datetime.now()),
            )
            birds.append(bird)

        if self.cache:
            import pickle
            serialized_data = pickle.dumps(birds)
            self.cache.set(cache_key, serialized_data, ex=BIRD_CACHE_TTL)

        return birds
