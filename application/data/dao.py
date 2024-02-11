import datetime
import json
import logging
import os
import pickle
import time
from typing import List

import fakeredis
import pytz
import redis
from pymongo import MongoClient
from pymongo.collection import Collection
from pymongo.database import Database

from application import CustomJsonEncoder
from application.constants.app_constants import (
    DATETIME_FORMAT_STRING,
    REDIS_VERSION, DATE_FORMAT_STRING, ONE_DAY_IN_SECONDS,
)
from application.data.custom_json_decoder import decode_json
from application.data.temperature_history import TemperatureHistory
from application.data.temperatures import Temperatures

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
        start = time.perf_counter_ns()

        temp_history = self._get_decimated_data(days_back)

        duration_ms = (time.perf_counter_ns() - start) // 1000000
        print(f"Temperature history for {days_back} days back took {duration_ms} ms")

        return temp_history

    @staticmethod
    def _get_data_to_add(min_temp: float, min_date: datetime.datetime, max_temp: float, max_date: datetime.datetime) -> (List[datetime.datetime], List[float]):
        if min_temp == max_temp:
            return [min_date], [min_temp]
        elif min_date <= max_date:
            return [min_date, max_date], [min_temp, max_temp]
        else:
            return [max_date, min_date], [max_temp, min_temp]

    def _calculate_day_temperatures(self, date: datetime.datetime, periods_per_day: int) -> Temperatures:
        # The first instant and last instant of the calendar date
        min_date = datetime.datetime.combine(date, datetime.time.min)
        max_date = datetime.datetime.combine(date, datetime.time.max)
        LOG.info(f"Calculating decimated values for date {min_date}")

        documents = self.pitemp_collection.find(
            filter={"timestamp": {"$gte": min_date, "$lte": max_date}}
        )
        # We need the dates in order for the algorithm to work
        documents.sort({"timestamp": 1})

        dates: List[datetime] = []
        temperatures: List[float] = []

        period_in_seconds = int(ONE_DAY_IN_SECONDS / periods_per_day)
        next_boundary = min_date + datetime.timedelta(seconds=period_in_seconds)
        period_min_temp = None
        period_min_datetime = None
        period_max_temp = None
        period_max_datetime = None

        for document in documents:
            timestamp = document["timestamp"]
            temperature = document["temp_f"]

            # If we are past the boundary of the period, it's time to start a new period by adding the min and max
            # values then resetting them to give this new period a clean start.
            if timestamp > next_boundary:
                dates_to_add, temps_to_add = self._get_data_to_add(min_temp=period_min_temp, min_date=period_min_datetime, max_temp=period_max_temp, max_date=period_max_datetime)
                dates.extend([x.strftime(DATETIME_FORMAT_STRING) for x in dates_to_add])
                temperatures.extend(temps_to_add)

                # Reset values for the next period
                next_boundary = next_boundary + datetime.timedelta(seconds=period_in_seconds)
                period_min_temp = None
                period_min_datetime = None
                period_max_temp = None
                period_max_datetime = None

            if (period_min_temp is None) or (temperature < period_min_temp):
                period_min_temp = temperature
                period_min_datetime = timestamp

            if (period_max_temp is None) or (temperature > period_max_temp):
                period_max_temp = temperature
                period_max_datetime = timestamp

        return Temperatures(dates=dates, temperatures=temperatures)

    def _get_decimated_data(self, days_back: int) -> TemperatureHistory:
        now_datetime = datetime.datetime.now()

        dates: List[str] = []
        temperatures: List[float] = []

        current_date = datetime.datetime.now() - datetime.timedelta(days=days_back)
        periods_per_day = self._get_periods_per_day(days_back)
        for i in range(days_back + 1):
            hours_diff = abs((current_date - now_datetime).total_seconds() // 60)

            if hours_diff > 23:
                # Check the cache first to save computation cost
                day_cache_key = self._get_day_cache_key(current_date, periods_per_day)
                cached_day_value = self.cache.get(day_cache_key)

                if cached_day_value:
                    LOG.info(f"Getting day value from cache: {cached_day_value}")
                    day_temperatures = Temperatures(**json.loads(cached_day_value.decode()))
                else:
                    # If the day is not already cached, do so since the data should be immutable
                    day_temperatures = self._calculate_day_temperatures(current_date, periods_per_day)
                    self.cache.set(day_cache_key, json.dumps(day_temperatures, cls=CustomJsonEncoder))
            else:
                # We don't want to set the cache for the current day because it is not complete yet
                day_temperatures = self._calculate_day_temperatures(current_date, periods_per_day)

            dates.extend(day_temperatures.dates)
            temperatures.extend(day_temperatures.temperatures)

            current_date = current_date + datetime.timedelta(days=1)

        return TemperatureHistory(
            dates=dates,
            temperatures=temperatures,
            current_temp=temperatures[-1],
            minimum_temp=min(temperatures),
            maximum_temp=max(temperatures),
        )

    @staticmethod
    def _get_day_cache_key(date: datetime.datetime, periods_per_day: int) -> str:
        return f"{date.strftime(DATE_FORMAT_STRING)}_{periods_per_day}"

    @staticmethod
    def _get_periods_per_day(num_days: int) -> int:
        if num_days < 4:
            return 96
        if num_days < 7:
            return 48
        if num_days < 31:
            return 24
        if num_days < 91:
            return 12
        if num_days < 365:
            return 6
        return 1
