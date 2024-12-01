import datetime
import json
import logging
import time
from asyncio import Future
from concurrent.futures import ThreadPoolExecutor
from typing import List, Optional

import fakeredis
import pytz
import redis
from pymongo.collection import Collection
from pymongo.database import Database

from application import CustomJsonEncoder
from application.constants.app_constants import (
    DATETIME_FORMAT_STRING,
    REDIS_VERSION,
    DATE_FORMAT_STRING,
    ONE_DAY_IN_SECONDS, DEFAULT_TIMEZONE,
)
from application.data.temperature_data_set import TemperatureDataSet
from application.data.temperatures import Temperatures

DATABASE_NAME = "sensors"

LOG = logging.getLogger(__name__)


class ApplicationDao:
    def __init__(self, client, database: Database = None, cache: redis.Redis = None):
        # If no cache is given, spin up a fake one
        if cache is None:
            self.cache = fakeredis.FakeStrictRedis(version=REDIS_VERSION)
        else:
            self.cache = cache

        self.client =  client
        # If no database provided, connect to one
        if database is None:
            database: Database = self.client[DATABASE_NAME]

        # Set up database and collection variables
        self.database = database
        self.pitemp_collection: Collection = self.database["pitemp"]

        LOG.info(f"Database collections: {self.database.list_collection_names()}")

    @staticmethod
    def _fix_timestamps(temperature_data_set: TemperatureDataSet):
        for entry in temperature_data_set.data:
            timestamp = entry["x"]
            date_time = datetime.datetime.strptime(timestamp, DATETIME_FORMAT_STRING)
            date_time = date_time.replace(tzinfo=pytz.UTC)
            local_datetime = date_time.astimezone(pytz.timezone(DEFAULT_TIMEZONE))
            entry["x"] = datetime.datetime.strftime(local_datetime, DATETIME_FORMAT_STRING)

    def get_temperature_history(self, sensor_id: str, days_back: int) -> TemperatureDataSet:
        start = time.perf_counter_ns()

        temp_history = self._get_decimated_data(sensor_id, days_back)
        self._fix_timestamps(temp_history)

        duration_ms = (time.perf_counter_ns() - start) // 1000000
        print(f"Temperature history for {days_back} days back took {duration_ms} ms")

        return temp_history

    @staticmethod
    def _get_data_to_add(
        min_temp: float, min_date: datetime.datetime, max_temp: float, max_date: datetime.datetime
    ) -> (List[datetime.datetime], List[float]):
        if min_temp == max_temp:
            return [min_date], [min_temp]
        elif min_date <= max_date:
            return [min_date, max_date], [min_temp, max_temp]
        else:
            return [max_date, min_date], [max_temp, min_temp]

    def _calculate_day_temperatures(
        self, sensor_id: str, date: datetime.datetime, periods_per_day: int
    ) -> Optional[Temperatures]:
        # The first instant and last instant of the calendar date
        min_date = datetime.datetime.combine(date, datetime.time.min).replace(tzinfo=pytz.timezone(DEFAULT_TIMEZONE))
        max_date = datetime.datetime.combine(date, datetime.time.max).replace(tzinfo=pytz.timezone(DEFAULT_TIMEZONE))
        LOG.info(f"Calculating decimated values for date {min_date} from sensor {sensor_id}")

        documents = self.pitemp_collection.find(
            filter={"timestamp": {"$gte": min_date, "$lte": max_date}, "sensorId": sensor_id}
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
            # Timestamps in the database are in UTC
            timestamp = document["timestamp"].replace(tzinfo=pytz.UTC)
            temperature = document["temp_f"]

            if timestamp is None or temperature is None:
                LOG.warning(f"Invalid document {document}. Skipping.")
                continue

            # If we are past the boundary of the period, it's time to start a new period by adding the min and max
            # values then resetting them to give this new period a clean start.
            if timestamp > next_boundary:
                # We may not have enough data for the period granularity.
                # In this case, skip the periods before the current timestamp.
                if period_min_temp is None or period_max_temp is None:
                    next_boundary = timestamp
                    period_min_temp = temperature
                    period_min_datetime = timestamp
                    period_max_temp = temperature
                    period_max_datetime = timestamp

                dates_to_add, temps_to_add = self._get_data_to_add(
                    min_temp=period_min_temp,
                    min_date=period_min_datetime,
                    max_temp=period_max_temp,
                    max_date=period_max_datetime,
                )
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

    def _get_temperatures(
        self, sensor_id: str, date: datetime.datetime, now_datetime: datetime.datetime, periods_per_day: int
    ) -> Optional[Temperatures]:
        hours_diff = abs((date - now_datetime).total_seconds() // 60 // 60)

        if hours_diff >= 24:
            # Check the cache first to save computation cost
            day_cache_key = self._get_day_cache_key(sensor_id, date, periods_per_day)
            cached_day_value: bytes = self.cache.get(day_cache_key)

            if cached_day_value:
                LOG.info(f"Getting day value from cache for key {day_cache_key}: {cached_day_value}")
                day_temperatures = Temperatures(**json.loads(cached_day_value.decode()))
            else:
                # If the day is not already cached, do so since the data should be immutable
                day_temperatures = self._calculate_day_temperatures(sensor_id, date, periods_per_day)
                if day_temperatures:
                    self.cache.set(day_cache_key, json.dumps(day_temperatures, cls=CustomJsonEncoder))
        else:
            # We don't want to set the cache for the current day because it is not complete yet
            day_temperatures = self._calculate_day_temperatures(sensor_id, date, periods_per_day)

        return day_temperatures

    def _get_decimated_data(self, sensor_id: str, days_back: int) -> TemperatureDataSet:
        now_datetime = datetime.datetime.now(pytz.timezone(DEFAULT_TIMEZONE))

        dates: List[str] = []
        temperatures: List[float] = []

        current_date = now_datetime - datetime.timedelta(days=days_back)
        futures: List[Optional[Future]] = [None] * (days_back + 1)
        periods_per_day = self._get_periods_per_day(days_back)

        with ThreadPoolExecutor(max_workers=10) as executor:
            for i in range(days_back + 1):
                futures[i] = executor.submit(
                    self._get_temperatures, sensor_id, current_date, now_datetime, periods_per_day
                )
                current_date = current_date + datetime.timedelta(days=1)

            for i in range(len(futures)):
                result = futures[i].result()
                if result:
                    dates.extend(result.dates)
                    temperatures.extend(result.temperatures)

        data = []
        for i in range(len(dates)):
            data.append({"x": dates[i], "y": temperatures[i]})

        current_temp = temperatures[-1] if temperatures else -1
        min_temp = min(temperatures) if temperatures else -1
        max_temp = max(temperatures) if temperatures else -1

        return TemperatureDataSet(
            label=f"{sensor_id} - Temperature (°F)",
            data=data,
            current_temp=current_temp,
            minimum_temp=min_temp,
            maximum_temp=max_temp,
        )

    @staticmethod
    def _get_day_cache_key(sensor_id: str, date: datetime.datetime, periods_per_day: int) -> str:
        return f"{sensor_id}_{date.strftime(DATE_FORMAT_STRING)}_{periods_per_day}"

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
