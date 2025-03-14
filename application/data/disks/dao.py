import logging
import os
import pickle
from collections import defaultdict
from datetime import timedelta

import fakeredis
import redis
from pymongo.synchronous.collection import Collection
from pymongo.synchronous.database import Database

from application.constants.app_constants import REDIS_VERSION
from application.data.disks.drive import Drive

LOG = logging.getLogger(__name__)

DB_NAME = "disks"
COLLECTION_NAME = "space"
REDIS_CACHE_TTL = timedelta(days=1)
DRIVES_LIST_CACHE_KEY = "drives_list"


class DisksDao:
    def __init__(self, client, database: Database = None, cache: redis.Redis = None):
        # If no cache is given, spin up a fake one
        if cache is None:
            self.cache = fakeredis.FakeStrictRedis(version=REDIS_VERSION)
        else:
            self.cache = cache

        # Support resetting the cache for development testing
        if os.environ.get("RESET_CACHE", "false") == "true":
            LOG.info("Flushing cache")
            self.cache.flushall()

        self.client = client
        # If no database provided, connect to one
        if database is None:
            database: Database = self.client[DB_NAME]

        # Set up database and collection variables
        self.database = database
        self.collection: Collection = self.database[COLLECTION_NAME]

        LOG.info(f"Database collections: {self.database.list_collection_names()}")

    def get_drive_letter_to_data(self) -> dict[str, list[Drive]]:
        serialized_drives_list = self.cache.get(DRIVES_LIST_CACHE_KEY)
        if serialized_drives_list:
            # noinspection PyTypeChecker
            return pickle.loads(serialized_drives_list)

        # Get documents from oldest to newest
        documents = self.collection.find().sort("timestamp", 1)

        drive_letter_to_data = defaultdict(list)
        for document in documents:
            free_bytes = document["free_bytes"]
            capacity_bytes = document["capacity_bytes"]
            drive = Drive(
                timestamp=document["timestamp"],
                drive_letter=document["drive_letter"],
                free_bytes=free_bytes,
                capacity_bytes=capacity_bytes,
                used_bytes=capacity_bytes - free_bytes,
            )
            drive_letter_to_data[drive.drive_letter].append(drive)

        serialized_data = pickle.dumps(drive_letter_to_data)
        self.cache.set(DRIVES_LIST_CACHE_KEY, serialized_data, ex=REDIS_CACHE_TTL)

        return drive_letter_to_data
