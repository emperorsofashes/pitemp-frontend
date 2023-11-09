import os
from typing import Iterable

from pymongo import MongoClient
from pymongo.collection import Collection
from pymongo.database import Database

from application.constants.app_constants import MAX_METRICS_DOCUMENTS, MAX_METRICS_SIZE

DATABASE_NAME = "price_history_metrics"


class Metrics:
    def __init__(self, database: Database = None):
        # If no database provided, connect to one
        if database is None:
            username = os.environ.get("METRICS_USER")
            password = os.environ.get("METRICS_PASSWORD")
            host = os.environ.get("METRICS_HOST")

            if (username is None) or (password is None) or (host is None):
                print("!!!Metrics environment variables not set. Metrics logging disabled!!!")
                self.disabled = True
                return
            else:
                self.disabled = False

            self.client = MongoClient(
                f"mongodb+srv://{username}:{password}@{host}/{DATABASE_NAME}?retryWrites=true&w=majority"
            )

            database: Database = self.client[DATABASE_NAME]

        # Set up database and collection variables
        self.database = database

        list_of_collections = self.database.list_collection_names()

        self._create_capped_collection_if_not_exists("products_search_time", list_of_collections)
        self._create_capped_collection_if_not_exists("products_price_history_time", list_of_collections)
        self._create_capped_collection_if_not_exists("category_products_time", list_of_collections)

        self.products_search_time_collection: Collection = self.database["products_search_time"]
        self.products_price_history_time: Collection = self.database["products_price_history_time"]
        self.category_products_time: Collection = self.database["category_products_time"]

    def log_products_search_time(self, search_time_ms: int, query: str):
        if self.disabled:
            return

        self.products_search_time_collection.insert_one({"search_time_ms": search_time_ms, "query": query})

    def log_products_price_history_time(self, time_ms: int, product_id: int):
        if self.disabled:
            return

        self.products_price_history_time.insert_one({"time_ms": time_ms, "product_id": product_id})

    def log_category_products_time(self, time_ms: int, category_id: int):
        if self.disabled:
            return

        self.category_products_time.insert_one({"time_ms": time_ms, "category_id": category_id})

    def _create_capped_collection_if_not_exists(self, collection_name: str, collection_names: Iterable[str]):
        if collection_name not in collection_names:
            self.database.create_collection(
                collection_name,
                check_exists=True,
                capped=True,
                size=MAX_METRICS_SIZE,
                max=MAX_METRICS_DOCUMENTS,
            )
