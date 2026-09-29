import logging
import os

import valkey
from flask import Flask, session, request, jsonify, redirect
from flask_compress import Compress
from flask_wtf.csrf import CSRFProtect
from pymongo import MongoClient

from application.constants.app_constants import (
    DATABASE_CONFIG_KEY,
    BEERS_DATABASE_CONFIG_KEY,
    DISKS_DATABASE_CONFIG_KEY,
    BIRDS_DATABASE_CONFIG_KEY,
)
from application.data.beer.dao import BeerDao
from application.data.bird.dao import BirdDao
from application.data.custom_json_encoder import CustomJsonEncoder
from application.data.disks.dao import DisksDao
from application.data.temperature.dao import ApplicationDao
from application.routes.html_routes import HTML_BLUEPRINT

logging.basicConfig(level=logging.INFO)
logging.getLogger("engineio.server").setLevel(logging.WARNING)
logging.getLogger("socketio.server").setLevel(logging.WARNING)

LOG = logging.getLogger(__name__)

COMPRESS = Compress()
CSRF = CSRFProtect()


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

    cache_url = os.environ.get("REDIS_DATA_URL")
    if cache_url:
        cache = valkey.Valkey.from_url(cache_url)
        cache.ping()
        LOG.info("Using persistent cache for data")
    else:
        cache = None

    username = os.environ.get("MONGO_USER")
    password = os.environ.get("MONGO_PASSWORD")
    host = os.environ.get("MONGO_HOST")
    client = MongoClient(f"mongodb+srv://{username}:{password}@{host}/?retryWrites=true&w=majority")

    dao = ApplicationDao(client=client, cache=cache)
    app.config[DATABASE_CONFIG_KEY] = dao

    beer_dao = BeerDao(client=client, cache=cache)
    app.config[BEERS_DATABASE_CONFIG_KEY] = beer_dao

    disks_dao = DisksDao(client=client, cache=cache)
    app.config[DISKS_DATABASE_CONFIG_KEY] = disks_dao

    # Initialize bird DAO with separate credentials
    bird_username = os.environ.get("MONGO_BIRD_USER")
    bird_password = os.environ.get("MONGO_BIRD_PASSWORD")
    if bird_username and bird_password:
        bird_client = MongoClient(f"mongodb+srv://{bird_username}:{bird_password}@{host}/?retryWrites=true&w=majority")
        bird_dao = BirdDao(client=bird_client, cache=cache)
        app.config[BIRDS_DATABASE_CONFIG_KEY] = bird_dao
        LOG.info("Bird DAO initialized with separate credentials")
    else:
        LOG.warning("MONGO_BIRD_USER or MONGO_BIRD_PASSWORD not set, bird functionality will not be available")
        app.config[BIRDS_DATABASE_CONFIG_KEY] = None

    secret_key = os.environ.get("SECRET_KEY")
    admin_password = os.environ.get("ADMIN_PASSWORD")

    if not secret_key:
        raise RuntimeError("SECRET_KEY environment variable is required")

    if not admin_password:
        raise RuntimeError("ADMIN_PASSWORD environment variable is required")

    app.config["SECRET_KEY"] = secret_key
    app.config["ADMIN_PASSWORD"] = admin_password

    # Configure secure session settings for production (HTTPS)
    app.config["SESSION_COOKIE_SECURE"] = os.environ.get("SESSION_COOKIE_SECURE", "true").lower() == "true"
    app.config["SESSION_COOKIE_HTTPONLY"] = True
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"

    # Initialize CSRF protection
    CSRF.init_app(app)

    # Allow the use of the bytes_to_display method in Jinja
    app.jinja_env.filters["bytes_to_display"] = bytes_to_display

    # Register blueprints to add routes to the app
    app.register_blueprint(HTML_BLUEPRINT)

    # Add before_request hook for automatic write protection
    @app.before_request
    def require_auth_for_writes():
        # Public endpoints that don't require auth
        public_endpoints = {'login', 'static'}
        if request.endpoint in public_endpoints:
            return None

        # Allow read-only requests
        if request.method in ('GET', 'HEAD', 'OPTIONS'):
            return None

        # Authenticated users may perform writes
        if session.get('authenticated'):
            return None

        # API/fetch request
        if request.is_json or (
                request.accept_mimetypes
                and request.accept_mimetypes.accept_json
                and not request.accept_mimetypes.accept_html
        ):
            return jsonify({'error': 'Authentication required'}), 401

        # Browser request
        session['next'] = request.full_path.rstrip('?')
        return redirect('/login')

    return app
