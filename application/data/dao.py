import datetime
import logging
import operator
import os
import time
from typing import List
from flask import json

import fakeredis
import pymongo
import redis
from pymongo import MongoClient
from pymongo.collection import Collection
from pymongo.database import Database

from application.constants.app_constants import (
    DATE_FORMAT_STRING,
    PRODUCT_DISPLAY_NAME_CACHE_PREFIX,
    ONE_DAY_IN_SECONDS,
    REDIS_VERSION,
    PRODUCT_PRICE_HISTORY_CACHE_PREFIX,
    PRODUCT_SEARCH_CACHE_PREFIX,
    CATEGORIES_CACHE_KEY,
    CATEGORY_PRODUCTS_CACHE_KEY,
    PRODUCT_IDS_SEARCH_CACHE_PREFIX,
    CATEGORY_NAME_CACHE_KEY,
    NUM_PRODUCTS_CACHE_KEY,
    NUM_PRICES_CACHE_KEY,
    ONE_HOUR_IN_SECONDS,
    EXTREMES_PRICE_DATE_CACHE_PREFIX,
    MOST_PRICES_PRODUCT_CACHE_KEY,
)
from application.data.category import Category
from application.data.metrics import Metrics
from application.data.price_history import PriceHistory
from application.data.products_search import Product

DATABASE_NAME = "price_history"

LOG = logging.getLogger(__name__)


class ApplicationDao:
    def __init__(self, database: Database = None, metrics: Metrics = None, cache: redis.Redis = None):
        self.metrics = metrics

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

            database: Database = self.client["price_history"]

        # Set up database and collection variables
        self.database = database
        self.products_collection: Collection = self.database["products"]
        self.categories_collection: Collection = self.database["categories"]
        self.prices_collection: Collection = self.database["prices"]

        LOG.info(f"Database collections: {self.database.list_collection_names()}")

    def get_product_price_history(self, product_id: int) -> PriceHistory:
        start = time.perf_counter_ns()

        cache_key = f"{PRODUCT_PRICE_HISTORY_CACHE_PREFIX}_{product_id}"
        result = self.cache.get(cache_key)
        if result:
            price_history = PriceHistory(**json.loads(result.decode()))
        else:
            dates: List[datetime] = []
            prices: List[float] = []

            documents = self.prices_collection.find(
                filter={"product_id": product_id}, sort=[("start_date", pymongo.ASCENDING)]
            )

            for document in documents:
                dates.append(document["start_date"])
                prices.append(float(document["price_cents"]) / 100.0)

            # Ensure we add a data point for today based on the most recent data point
            current_price = None
            todays_date = datetime.datetime.today()
            if dates:
                dates.append(todays_date)
                prices.append(prices[-1])
                current_price = prices[-1]

            minimum_price = None
            maximum_price = None
            minimum_price_date = None
            maximum_price_date = None
            for i in range(len(prices)):
                price = prices[i]
                if (minimum_price is None) or (minimum_price >= price):
                    minimum_price = price
                    if i < len(dates) - 1:
                        minimum_price_date = dates[i + 1] - datetime.timedelta(days=1)
                    else:
                        minimum_price_date = todays_date
                if (maximum_price is None) or (maximum_price <= price):
                    maximum_price = price
                    if i < len(dates) - 1:
                        maximum_price_date = dates[i + 1] - datetime.timedelta(days=1)
                    else:
                        maximum_price_date = todays_date

            price_history = PriceHistory(
                dates=[x.strftime(DATE_FORMAT_STRING) for x in dates],
                prices=prices,
                current_price=current_price,
                minimum_price=minimum_price,
                maximum_price=maximum_price,
                minimum_price_date=minimum_price_date.strftime(DATE_FORMAT_STRING),
                maximum_price_date=maximum_price_date.strftime(DATE_FORMAT_STRING),
            )
            self.cache.set(cache_key, json.dumps(price_history), ex=ONE_DAY_IN_SECONDS)

        duration_ms = (time.perf_counter_ns() - start) // 1000000
        print(f"Price history for product {product_id!r} took {duration_ms} ms")
        if self.metrics:
            self.metrics.log_products_price_history_time(time_ms=duration_ms, product_id=product_id)

        return price_history

    def get_product_display_name(self, product_id: int) -> str:
        cache_key = f"{PRODUCT_DISPLAY_NAME_CACHE_PREFIX}_{product_id}"
        result = self.cache.get(cache_key)
        if result:
            return result.decode()

        document = self.products_collection.find_one(filter={"id": product_id})

        if document:
            display_name = document["display_name"]
            self.cache.set(cache_key, display_name, ex=ONE_DAY_IN_SECONDS)
            return display_name
        else:
            return "UNKNOWN"

    def get_products(self, search_query: str) -> List[Product]:
        start = time.perf_counter_ns()

        cache_key = f"{PRODUCT_SEARCH_CACHE_PREFIX}_{search_query}"
        result = self.cache.get(cache_key)
        if result:
            json_data = json.loads(result.decode())
            products = [Product(**x) for x in json_data]
        else:
            products = []

            # We want to make sure each word appears in the product name, so use a compound search
            word_searches = []
            for word in search_query.split():
                word_searches.append({"autocomplete": {"query": word, "path": "display_name"}})

            # We can only do searches in an aggregation pipeline
            documents = self.products_collection.aggregate([{"$search": {"compound": {"must": word_searches}}}])
            for document in documents:
                product = Product(id=document["id"], display_name=document["display_name"])
                products.append(product)

            products.sort(key=operator.attrgetter("display_name"))
            self.cache.set(cache_key, json.dumps(products), ex=ONE_DAY_IN_SECONDS)

        duration_ms = (time.perf_counter_ns() - start) // 1000000
        print(f"Products search {search_query!r} took {duration_ms} ms")
        if self.metrics:
            self.metrics.log_products_search_time(search_time_ms=duration_ms, query=search_query)

        return products

    def get_categories(self) -> List[Category]:
        result = self.cache.get(CATEGORIES_CACHE_KEY)
        if result:
            json_data = json.loads(result.decode())
            categories = [Category(**x) for x in json_data]
        else:
            categories = []
            documents = self.categories_collection.find({})
            for document in documents:
                category = Category(id=document["id"], display_name=document["display_name"])
                categories.append(category)

            categories.sort(key=operator.attrgetter("display_name"))
            self.cache.set(CATEGORIES_CACHE_KEY, json.dumps(categories))

        return categories

    def get_category_display_name(self, category_id: int) -> str:
        cache_key = f"{CATEGORY_NAME_CACHE_KEY}_{category_id}"
        result = self.cache.get(cache_key)
        if result:
            return result.decode()

        document = self.categories_collection.find_one(filter={"id": category_id})

        if document:
            category_display_name = document["display_name"]
            self.cache.set(cache_key, category_display_name)
            return category_display_name
        else:
            return "UNKNOWN"

    def get_category_products(self, category_id: int) -> List[Product]:
        start = time.perf_counter_ns()

        cache_key = f"{CATEGORY_PRODUCTS_CACHE_KEY}_{category_id}"
        result = self.cache.get(cache_key)
        if result:
            json_data = json.loads(result.decode())
            products = [Product(**x) for x in json_data]
        else:
            products = []
            documents = self.products_collection.find(filter={"category": category_id})
            for document in documents:
                product = Product(id=document["id"], display_name=document["display_name"])
                products.append(product)

            products.sort(key=operator.attrgetter("display_name"))
            self.cache.set(cache_key, json.dumps(products), ex=ONE_DAY_IN_SECONDS)

        duration_ms = (time.perf_counter_ns() - start) // 1000000
        print(f"Category products {category_id!r} took {duration_ms} ms")
        if self.metrics:
            self.metrics.log_category_products_time(time_ms=duration_ms, category_id=category_id)

        return products

    def get_products_from_ids(self, product_ids: List[int]) -> List[Product]:
        cache_key = f"{PRODUCT_IDS_SEARCH_CACHE_PREFIX}_{json.dumps(product_ids)}"
        result = self.cache.get(cache_key)
        if result:
            json_data = json.loads(result.decode())
            products = [Product(**x) for x in json_data]
        else:
            documents = self.products_collection.find({"id": {"$in": product_ids}})
            products = []
            for document in documents:
                products.append(Product(id=document["id"], display_name=document["display_name"]))

            products.sort(key=operator.attrgetter("display_name"))
            self.cache.set(cache_key, json.dumps(products), ex=ONE_DAY_IN_SECONDS)

        if len(products) != len(product_ids):
            LOG.warning(f"Could not find all products from ID list {product_ids}. Could only find {products}.")

        return products

    def get_num_products(self) -> int:
        result = self.cache.get(NUM_PRODUCTS_CACHE_KEY)
        if result:
            return int(result)

        num_documents = self.products_collection.count_documents(filter={})
        self.cache.set(NUM_PRODUCTS_CACHE_KEY, num_documents, ex=ONE_DAY_IN_SECONDS)
        return num_documents

    def get_num_prices(self) -> int:
        result = self.cache.get(NUM_PRICES_CACHE_KEY)
        if result:
            return int(result)

        num_documents = self.prices_collection.count_documents(filter={})
        self.cache.set(NUM_PRICES_CACHE_KEY, num_documents, ex=ONE_DAY_IN_SECONDS)
        return num_documents

    def get_oldest_price_document_date(self) -> str:
        return self._get_extreme_price_document_date(pymongo.ASCENDING)

    def get_newest_price_document_date(self) -> str:
        return self._get_extreme_price_document_date(pymongo.DESCENDING)

    def _get_extreme_price_document_date(self, sort_order: int) -> str:
        cache_key = f"{EXTREMES_PRICE_DATE_CACHE_PREFIX}_{sort_order}"
        result = self.cache.get(cache_key)
        if result:
            return result.decode()

        document = self.prices_collection.find_one(sort=[("start_date", sort_order)])
        date: datetime.datetime = document["start_date"]
        date_string = date.date().isoformat()
        self.cache.set(cache_key, date_string, ex=ONE_HOUR_IN_SECONDS)
        return date_string

    def get_product_with_most_price_documents(self) -> int:
        result = self.cache.get(MOST_PRICES_PRODUCT_CACHE_KEY)
        if result:
            return int(result)

        result = self.prices_collection.aggregate([{"$sortByCount": "$product_id"}, {"$limit": 1}])
        document = result.next()
        product_id = document["_id"]
        self.cache.set(MOST_PRICES_PRODUCT_CACHE_KEY, product_id, ex=ONE_DAY_IN_SECONDS)
        return product_id
