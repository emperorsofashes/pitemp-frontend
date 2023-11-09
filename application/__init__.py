import logging
import os

import redis
from flask import Flask
from flask_compress import Compress

from application.constants.app_constants import DATABASE_CONFIG_KEY, METRICS_CONFIG_KEY, USERS_CONFIG_KEY
from application.data.custom_json_encoder import CustomJsonEncoder
from application.data.dao import ApplicationDao
from application.data.metrics import Metrics
from application.data.users import Users
from application.routes.api_routes import API_BLUEPRINT
from application.routes.html_routes import HTML_BLUEPRINT

logging.basicConfig(level=logging.INFO)
logging.getLogger("engineio.server").setLevel(logging.WARNING)
logging.getLogger("socketio.server").setLevel(logging.WARNING)

LOG = logging.getLogger(__name__)

COMPRESS = Compress()


def create_flask_app() -> Flask:
    # Create the flask app
    app = Flask(__name__)

    # Enable gzip compression for requests
    COMPRESS.init_app(app)

    # Set custom JSON encoder to handle MongoDB ObjectID
    app.json_encoder = CustomJsonEncoder

    # Create a DAO and add it to the flask app config for access by the blueprints
    metrics = Metrics()
    app.config[METRICS_CONFIG_KEY] = metrics

    redis_url = os.environ.get("REDIS_DATA_URL")
    if redis_url:
        cache = redis.Redis.from_url(redis_url)
        cache.ping()
        LOG.info("Using Redis cache for data")
    else:
        cache = None

    dao = ApplicationDao(metrics=metrics, cache=cache)
    app.config[DATABASE_CONFIG_KEY] = dao

    users = Users(dao=dao)
    app.config[USERS_CONFIG_KEY] = users

    # This must be set in the environment as a secret
    app.secret_key = os.environ["SECRET_KEY"]

    # Register blueprints to add routes to the app
    app.register_blueprint(HTML_BLUEPRINT)
    app.register_blueprint(API_BLUEPRINT)

    return app
