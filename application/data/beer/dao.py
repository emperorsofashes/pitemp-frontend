import logging
import os
import pickle
from collections import defaultdict
from statistics import median

import fakeredis
import redis
from pymongo import MongoClient
from pymongo.collection import Collection
from pymongo.database import Database

from application.constants.beer_constants import DB_NAME, REDIS_VERSION, BEERS_COLLECTION_NAME, REDIS_CACHE_TTL, \
    BREWERIES_COLLECTION_NAME, COUNTRIES
from application.data.beer.beer import Beer
from application.data.beer.brewery import Brewery
from application.data.beer.country import Country
from application.data.beer.style import Style

LOG = logging.getLogger(__name__)


class BeerDao:
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
        self.beers_collection: Collection = self.database[BEERS_COLLECTION_NAME]
        self.breweries_collection: Collection = self.database[BREWERIES_COLLECTION_NAME]

        LOG.info(f"Database collections: {self.database.list_collection_names()}")

    def get_beers(self) -> list[Beer]:
        serialized_beer_list = self.cache.get("beer_list")
        if serialized_beer_list:
            # noinspection PyTypeChecker
            return pickle.loads(serialized_beer_list)

        brewery_id_to_country = dict()
        breweries_documents = self.breweries_collection.find()
        for brewery_document in breweries_documents:
            brewery_id = brewery_document["id"]
            brewery_id_to_country[brewery_id] = self._get_country(brewery_document["full_location"])

        beer_documents = self.beers_collection.find()
        beers = []
        for beer_document in beer_documents:
            brewery_id = beer_document["brewery_id"]
            beer = Beer(
                name=beer_document["name"],
                id=beer_document["id"],
                brewery=beer_document["brewery"],
                brewery_id=brewery_id,
                rating=beer_document["rating"],
                style=beer_document["style"],
                abv=beer_document["abv"],
                first_checkin=beer_document["first_checkin"],
                country=brewery_id_to_country.get(brewery_id, "")
            )
            beers.append(beer)

        serialized_data = pickle.dumps(beers)
        self.cache.set("beer_list", serialized_data, ex=REDIS_CACHE_TTL)

        return beers

    def get_breweries(self) -> list[Brewery]:
        serialized_breweries_list = self.cache.get("breweries_list")
        if serialized_breweries_list:
            # noinspection PyTypeChecker
            return pickle.loads(serialized_breweries_list)

        documents = self.breweries_collection.find()
        brewery_id_to_beers = self._get_brewery_to_beers()

        breweries = []
        for document in documents:
            full_location = document["full_location"]
            brewery_id = document["id"]

            brewery_beers = brewery_id_to_beers[brewery_id]
            ratings = [b.rating for b in brewery_beers]
            filtered_ratings = [value for value in ratings if value != -1.0]
            avg_rating = sum(filtered_ratings) / len(filtered_ratings) if filtered_ratings else -1
            first_checkin = min([b.first_checkin for b in brewery_beers])

            brewery = Brewery(
                id=brewery_id,
                name=document["name"],
                type=document["type"],
                full_location=full_location,
                num_checkins=len(ratings),
                num_checkins_with_ratings=len(filtered_ratings),
                avg_rating=avg_rating,
                country=self._get_country(full_location),
                first_checkin=first_checkin
            )
            breweries.append(brewery)

        serialized_data = pickle.dumps(breweries)
        self.cache.set("breweries_list", serialized_data, ex=REDIS_CACHE_TTL)

        return breweries

    @staticmethod
    def _get_country(full_location: str) -> str:
        full_location = full_location.strip()
        for country in COUNTRIES:
            if full_location.endswith(country):
                return country

        return "?"

    def get_countries(self) -> list[Country]:
        serialized_countries_list = self.cache.get("countries_list")
        if serialized_countries_list:
            # noinspection PyTypeChecker
            return pickle.loads(serialized_countries_list)

        breweries = self.get_breweries()
        country_to_breweries = defaultdict(list)
        for brewery in breweries:
            country_to_breweries[brewery.country].append(brewery)

        countries = []
        for country in country_to_breweries.keys():
            country_breweries = country_to_breweries[country]
            num_breweries = len(country_breweries)
            num_checkins = sum(brewery.num_checkins for brewery in country_breweries)

            num_rated_checkins = sum(brewery.num_checkins_with_ratings for brewery in country_breweries)
            if num_rated_checkins > 0:
                total_rating = sum(
                    brewery.avg_rating * brewery.num_checkins_with_ratings for brewery in country_breweries)
                avg_rating = total_rating / num_rated_checkins
            else:
                avg_rating = -1

            first_checkin = min(b.first_checkin for b in country_breweries)

            countries.append(Country(name=country, num_breweries=num_breweries, num_checkins=num_checkins,
                                     avg_rating=avg_rating, first_checkin=first_checkin))

        serialized_data = pickle.dumps(countries)
        self.cache.set("countries_list", serialized_data, ex=REDIS_CACHE_TTL)

        return countries

    def _get_brewery_to_beers(self) -> dict[str, list[Beer]]:
        brewery_id_to_beers = defaultdict(list)
        beers = self.get_beers()

        for beer in beers:
            brewery_id = beer.brewery_id
            brewery_id_to_beers[brewery_id].append(beer)

        return brewery_id_to_beers

    def get_styles(self) -> list[Style]:
        serialized_styles_list = self.cache.get("styles_list")
        if serialized_styles_list:
            # noinspection PyTypeChecker
            return pickle.loads(serialized_styles_list)

        beers = self.get_beers()
        style_to_beers = defaultdict(list)
        for beer in beers:
            style_to_beers[beer.style].append(beer)

        styles = []
        for style_name, beers in style_to_beers.items():
            ratings = [b.rating for b in beers]
            filtered_ratings = [value for value in ratings if value != -1.0]

            num_checkins = len(ratings)
            avg_rating = sum(filtered_ratings) / len(filtered_ratings) if filtered_ratings else -1
            median_rating = median(filtered_ratings) if filtered_ratings else -1
            min_rating = min(filtered_ratings) if filtered_ratings else -1
            max_rating = max(filtered_ratings) if filtered_ratings else -1
            first_checkin = min([b.first_checkin for b in beers])
            style = Style(name=style_name, num_checkins=num_checkins, min_rating=min_rating, max_rating=max_rating,
                          avg_rating=avg_rating, median_rating=median_rating, first_checkin=first_checkin)
            styles.append(style)

        serialized_data = pickle.dumps(styles)
        self.cache.set("styles_list", serialized_data, ex=REDIS_CACHE_TTL)

        return styles
