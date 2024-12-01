import logging
import os

import redis
from flask import Flask
from flask_compress import Compress
from pymongo import MongoClient
from redis import Redis

from application.constants.app_constants import DATABASE_CONFIG_KEY, BEERS_DATABASE_CONFIG_KEY, \
    DISKS_DATABASE_CONFIG_KEY
from application.data.beer.dao import BeerDao
from application.data.custom_json_encoder import CustomJsonEncoder
from application.data.dao import ApplicationDao
from application.data.disks.dao import DisksDao
from application.routes.html_routes import HTML_BLUEPRINT

logging.basicConfig(level=logging.INFO)
logging.getLogger("engineio.server").setLevel(logging.WARNING)
logging.getLogger("socketio.server").setLevel(logging.WARNING)

LOG = logging.getLogger(__name__)

COMPRESS = Compress()


def bytes_to_display(value: int) -> str:
    unit = 1024 ** 4  # Start with terabytes
    if value < unit:
        unit = 1024 ** 3  # Switch to gigabytes if less than 1 TB
        return f"{value / unit:.2f} GB"
    return f"{value / unit:.2f} TB"


def create_flask_app() -> Flask:
    # Create the flask app
    app = Flask(__name__)

    # Enable gzip compression for requests
    COMPRESS.init_app(app)

    # Set custom JSON encoder to handle MongoDB ObjectID
    app.json_encoder = CustomJsonEncoder

    redis_url = os.environ.get("REDIS_DATA_URL")
    if redis_url:
        cache: Redis = redis.Redis.from_url(redis_url)
        cache.ping()
        LOG.info("Using Redis cache for data")
    else:
        cache = None

    username = os.environ.get("MONGO_USER")
    password = os.environ.get("MONGO_PASSWORD")
    host = os.environ.get("MONGO_HOST")
    client = MongoClient(
        f"mongodb+srv://{username}:{password}@{host}/?retryWrites=true&w=majority"
    )

    dao = ApplicationDao(client=client, cache=cache)
    app.config[DATABASE_CONFIG_KEY] = dao

    beer_dao = BeerDao(client=client, cache=cache)
    app.config[BEERS_DATABASE_CONFIG_KEY] = beer_dao

    disks_dao = DisksDao(client=client, cache=cache)
    app.config[DISKS_DATABASE_CONFIG_KEY] = disks_dao

    # This must be set in the environment as a secret
    app.secret_key = os.environ["SECRET_KEY"]

    # Allow the use of the bytes_to_display method in Jinja
    app.jinja_env.filters['bytes_to_display'] = bytes_to_display

    # Register blueprints to add routes to the app
    app.register_blueprint(HTML_BLUEPRINT)

    return app
