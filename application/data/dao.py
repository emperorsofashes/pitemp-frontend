import datetime
import logging
import os
import time
from typing import List

import fakeredis
import pytz
import redis
from pymongo import MongoClient
from pymongo.collection import Collection
from pymongo.database import Database

from application.constants.app_constants import (
    DATE_FORMAT_STRING,
    REDIS_VERSION,
)
from application.data.temperature_history import TemperatureHistory

DATABASE_NAME = "sensors"

LOG = logging.getLogger(__name__)


class ApplicationDao:
    def __init__(self, database: Database = None, cache: redis.Redis = None):
        # If no cache is given, spin up a fake one
        if cache is None:
            self.cache = fakeredis.FakeStrictRedis(version=REDIS_VERSION)
        else:
            self.cache = cache

        # If no database provided, connect to one
        if database is None:
            username = os.environ.get("MONGO_USER")
            password = os.environ.get("MONGO_PASSWORD")
            host = os.environ.get("MONGO_HOST")
            self.client = MongoClient(
                f"mongodb+srv://{username}:{password}@{host}/{DATABASE_NAME}?retryWrites=true&w=majority"
            )

            database: Database = self.client[DATABASE_NAME]

        # Set up database and collection variables
        self.database = database
        self.pitemp_collection: Collection = self.database["pitemp"]

        LOG.info(f"Database collections: {self.database.list_collection_names()}")

    def get_temperature_history(self, days_back: int) -> TemperatureHistory:
        # TODO implement min-max decimation to help with performance

        start = time.perf_counter_ns()

        dates: List[datetime] = []
        temperatures: List[float] = []

        documents = self.pitemp_collection.find(
            filter={"timestamp": {"$gte": datetime.datetime.now() - datetime.timedelta(days=days_back)}}
        )
        # We need the dates in order for them to render correctly
        documents.sort({"timestamp": 1})

        minimum_temp = None
        maximum_temp = None
        minimum_temp_date = None
        maximum_temp_date = None

        for document in documents:
            timestamp = (
                document["timestamp"].replace(tzinfo=datetime.timezone.utc).astimezone(tz=pytz.timezone("US/Central"))
            )
            dates.append(timestamp)
            temp = document["temp_f"]
            temperature = temp
            temperatures.append(temperature)

            if (minimum_temp is None) or (minimum_temp >= temp):
                minimum_temp = temp
                minimum_temp_date = timestamp
            if (maximum_temp is None) or (maximum_temp <= temp):
                maximum_temp = temp
                maximum_temp_date = timestamp

        temp_history = TemperatureHistory(
            dates=[x.strftime(DATE_FORMAT_STRING) for x in dates],
            temperatures=temperatures,
            current_temp=temperatures[-1],
            minimum_temp=minimum_temp,
            maximum_temp=maximum_temp,
            minimum_temp_date=minimum_temp_date.strftime(DATE_FORMAT_STRING),
            maximum_temp_date=maximum_temp_date.strftime(DATE_FORMAT_STRING),
        )

        duration_ms = (time.perf_counter_ns() - start) // 1000000
        print(f"Temperature history for {days_back} days back took {duration_ms} ms")

        return temp_history
