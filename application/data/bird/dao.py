import logging
import pickle
from datetime import datetime
from typing import Any

import fakeredis
from bson import ObjectId
from pymongo.collection import Collection
from pymongo.database import Database

from application.constants.bird_constants import (
    BIRD_CACHE_TTL,
    BIRD_DB_NAME,
    BIRDS_COLLECTION_NAME,
    LIFE_LIST_COLLECTION_NAME,
)
from application.data.bird.bird import Bird, LifeListEntry

LOG = logging.getLogger(__name__)


class BirdDao:
    def __init__(self, client, database: Database = None, cache=None):
        self.cache = cache or fakeredis.FakeValkey()
        self.client = client
        self.database: Database = database if database is not None else self.client[BIRD_DB_NAME]
        self.birds_collection: Collection = self.database[BIRDS_COLLECTION_NAME]
        self.life_list_collection: Collection = self.database[LIFE_LIST_COLLECTION_NAME]

        # Create unique index on scientific_name to ensure one document per species
        self.life_list_collection.create_index([("scientific_name", 1)], unique=True)

        LOG.info(f"Connected to database: {BIRD_DB_NAME}")

    def _get_cached(self, key: str) -> Any | None:
        try:
            cached = self.cache.get(key)
            return pickle.loads(cached) if cached else None
        except Exception as e:
            LOG.warning(f"Cache get failed for key {key}: {e}")
            return None

    def _set_cached(self, key: str, value: Any) -> None:
        try:
            self.cache.set(key, pickle.dumps(value), ex=BIRD_CACHE_TTL)
        except Exception as e:
            LOG.warning(f"Cache set failed for key {key}: {e}")

    def get_all_birds(self) -> list[Bird]:
        """Get all bird species from the birds collection."""
        cache_key = "all_birds"
        cached = self._get_cached(cache_key)
        if cached is not None:
            return cached

        birds = [Bird.from_mongo(doc) for doc in self.birds_collection.find()]
        self._set_cached(cache_key, birds)
        return birds

    def get_bird(self, bird_id: str) -> Bird | None:
        """Get a bird species by its MongoDB _id."""
        cache_key = f"bird_{bird_id}"
        cached = self._get_cached(cache_key)
        if cached is not None:
            return cached

        try:
            doc = self.birds_collection.find_one({"_id": ObjectId(bird_id)})
            bird = Bird.from_mongo(doc) if doc else None
            if bird:
                self._set_cached(cache_key, bird)
            return bird
        except Exception:
            return None

    def search_birds(self, query: str) -> list[Bird]:
        """Search birds by common name or scientific name with forgiving matching."""
        # Trim and normalize query
        query = query.strip()
        if not query:
            return []

        # Create space-removed version for space-insensitive matching (e.g., "Fairy Wren" -> "Fairywren")
        query_no_spaces = query.replace(" ", "")

        cache_key = f"bird_search_{query}"
        cached = self._get_cached(cache_key)
        if cached is not None:
            return cached

        # Use MongoDB regex for efficient substring matching
        # Match original query as substring (case-insensitive)
        docs = self.birds_collection.find({
            "$or": [
                {"common_name": {"$regex": query, "$options": "i"}},
                {"scientific_name": {"$regex": query, "$options": "i"}},
                {"common_name": {"$regex": query_no_spaces, "$options": "i"}},
                {"scientific_name": {"$regex": query_no_spaces, "$options": "i"}},
            ]
        })

        birds = [Bird.from_mongo(doc) for doc in docs]
        self._set_cached(cache_key, birds)
        return birds

    def find_birds_by_inat_ids_or_names(self, inat_ids: list[int], scientific_names: list[str]) -> list[Bird]:
        """Find matching birds in the database by iNat IDs or scientific names."""
        clauses = []
        if inat_ids:
            clauses.append({"inat_id": {"$in": inat_ids}})
        if scientific_names:
            clauses.append({"scientific_name": {"$in": scientific_names}})

        if not clauses:
            return []

        docs = self.birds_collection.find({"$or": clauses})
        return [Bird.from_mongo(doc) for doc in docs]

    def get_life_list(self) -> list[LifeListEntry]:
        """Get all entries from the life list. Sorting is handled client-side."""
        cache_key = "life_list"
        cached = self._get_cached(cache_key)
        if cached is not None:
            return cached

        entries = [LifeListEntry.from_mongo(doc) for doc in self.life_list_collection.find()]
        self._set_cached(cache_key, entries)
        return entries

    def get_life_list_entry(self, entry_id: str) -> LifeListEntry | None:
        """Get a single life list entry by its MongoDB _id."""
        try:
            doc = self.life_list_collection.find_one({"_id": ObjectId(entry_id)})
            return LifeListEntry.from_mongo(doc) if doc else None
        except Exception:
            return None

    def get_life_list_entry_by_bird_id(self, bird_id: str) -> LifeListEntry | None:
        """Get a life list entry by bird_id."""
        doc = self.life_list_collection.find_one({"bird_id": bird_id})
        return LifeListEntry.from_mongo(doc) if doc else None

    def add_to_life_list(
        self,
        bird_id: str,
        scientific_name: str,
        common_name: str,
        date_sighted: datetime,
        notes: str | None = None,
    ) -> str:
        """Add a bird to the life list."""
        document = {
            "bird_id": bird_id,
            "scientific_name": scientific_name,
            "common_name": common_name,
            "date_sighted": date_sighted,
            "notes": notes,
        }
        result = self.life_list_collection.insert_one(document)
        try:
            self.cache.delete("life_list")
        except Exception as e:
            LOG.warning(f"Cache delete failed after adding to life list: {e}")
        return str(result.inserted_id)

    def update_life_list_entry(self, entry_id: str, date_sighted: datetime, notes: str | None = None) -> bool:
        """Update an existing life list entry."""
        update_doc = {"date_sighted": date_sighted}
        if notes is not None:
            update_doc["notes"] = notes

        result = self.life_list_collection.update_one(
            {"_id": ObjectId(entry_id)},
            {"$set": update_doc},
        )
        try:
            self.cache.delete("life_list")
        except Exception as e:
            LOG.warning(f"Cache delete failed after updating life list entry: {e}")
        return result.modified_count > 0

    def delete_from_life_list(self, entry_id: str) -> bool:
        """Delete an entry from the life list."""
        result = self.life_list_collection.delete_one({"_id": ObjectId(entry_id)})
        try:
            self.cache.delete("life_list")
        except Exception as e:
            LOG.warning(f"Cache delete failed after deleting from life list: {e}")
        return result.deleted_count > 0
