import logging
import os
from datetime import timedelta
from pathlib import Path
from urllib.parse import urlparse

import valkey
from dotenv import load_dotenv

# Load .env file if it exists (optional, provides defaults)
# Environment variables already set take precedence over .env values
load_dotenv(Path(__file__).parent.parent / "secrets.env", override=False)

from flask import Flask, session, request, jsonify, redirect, flash
from flask_compress import Compress
from flask_wtf.csrf import CSRFProtect
from pymongo import MongoClient

from application.constants.app_constants import (
    DATABASE_CONFIG_KEY,
    BEERS_DATABASE_CONFIG_KEY,
    DISKS_DATABASE_CONFIG_KEY,
    BIRDS_DATABASE_CONFIG_KEY,
    BOOKS_DATABASE_CONFIG_KEY,
    R2_CLIENT_CONFIG_KEY,
    MAX_COVER_IMAGE_SIZE_BYTES,
    SESSION_LIFETIME_DAYS,
)
from application.data.beer.dao import BeerDao
from application.data.bird.dao import BirdDao
from application.data.book.dao import BookDao
from application.data.custom_json_encoder import CustomJsonEncoder
from application.data.disks.dao import DisksDao
from application.data.storage.r2_storage import R2Storage, derive_thumb_key
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

    app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(days=SESSION_LIFETIME_DAYS)

    # Validate required environment variables before initializing databases
    secret_key = os.environ.get("SECRET_KEY")
    admin_password = os.environ.get("ADMIN_PASSWORD")

    if not secret_key:
        raise RuntimeError("SECRET_KEY environment variable is required")

    if not admin_password:
        raise RuntimeError("ADMIN_PASSWORD environment variable is required")

    app.secret_key = secret_key
    app.config["ADMIN_PASSWORD"] = admin_password

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
    client = MongoClient(
        host=f"mongodb+srv://{host}/",
        username=username,
        password=password,
        retryWrites=True,
        w="majority",
    )

    dao = ApplicationDao(client=client, cache=cache)
    app.config[DATABASE_CONFIG_KEY] = dao

    beer_dao = BeerDao(client=client, cache=cache)
    app.config[BEERS_DATABASE_CONFIG_KEY] = beer_dao

    disks_dao = DisksDao(client=client, cache=cache)
    app.config[DISKS_DATABASE_CONFIG_KEY] = disks_dao

    # Initialize bird DAO using the main MongoDB credentials
    bird_dao = BirdDao(client=client, cache=cache)
    app.config[BIRDS_DATABASE_CONFIG_KEY] = bird_dao
    LOG.info("Bird DAO initialized using main MongoDB credentials")

    # Initialize books DAO using the main MongoDB credentials
    books_dao = BookDao(client=client, cache=cache)
    app.config[BOOKS_DATABASE_CONFIG_KEY] = books_dao
    LOG.info("Books DAO initialized using main MongoDB credentials")

    # Initialize Cloudflare R2 storage
    app.config["MAX_CONTENT_LENGTH"] = MAX_COVER_IMAGE_SIZE_BYTES
    r2_account_id = os.environ.get("R2_ACCOUNT_ID")
    r2_access_key_id = os.environ.get("R2_ACCESS_KEY_ID")
    r2_secret_access_key = os.environ.get("R2_SECRET_ACCESS_KEY")
    r2_bucket_name = os.environ.get("R2_BUCKET_NAME")
    r2_public_url = os.environ.get("BOOK_IMAGE_HOST") or os.environ.get("R2_PUBLIC_URL")

    if r2_account_id and r2_access_key_id and r2_secret_access_key and r2_bucket_name:
        r2_storage = R2Storage(
            account_id=r2_account_id,
            access_key_id=r2_access_key_id,
            secret_access_key=r2_secret_access_key,
            bucket_name=r2_bucket_name,
            public_url=r2_public_url,
        )
        app.config[R2_CLIENT_CONFIG_KEY] = r2_storage
        LOG.info("Cloudflare R2 storage initialized successfully")
    else:
        app.config[R2_CLIENT_CONFIG_KEY] = None
        LOG.info("Cloudflare R2 storage credentials not set in environment")

    # Configure secure session settings for production (HTTPS)
    app.config["SESSION_COOKIE_SECURE"] = os.environ.get("SESSION_COOKIE_SECURE", "true").lower() == "true"
    app.config["SESSION_COOKIE_HTTPONLY"] = True
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"

    # Initialize CSRF protection
    CSRF.init_app(app)

    # Allow the use of the bytes_to_display method in Jinja
    app.jinja_env.filters["bytes_to_display"] = bytes_to_display

    # Add Jinja filters for cover and thumbnail URLs
    def cover_url_filter(cover_key: str | None) -> str:
        if not cover_key:
            return ""
        storage: R2Storage | None = app.config.get(R2_CLIENT_CONFIG_KEY)
        if storage and storage.public_url:
            return storage.get_public_url(cover_key)
        r2_url = os.environ.get("BOOK_IMAGE_HOST") or os.environ.get("R2_PUBLIC_URL", "")
        return f"{r2_url.rstrip('/')}/{cover_key.lstrip('/')}" if r2_url else ""

    def thumb_url_filter(cover_key: str | None) -> str:
        if not cover_key:
            return ""
        thumb_key = derive_thumb_key(cover_key)
        return cover_url_filter(thumb_key)

    app.jinja_env.filters["cover_url"] = cover_url_filter
    app.jinja_env.filters["thumb_url"] = thumb_url_filter

    # Handle file upload exceeding MAX_CONTENT_LENGTH
    @app.errorhandler(413)
    def request_entity_too_large(error):
        if request.is_json or (
            request.accept_mimetypes
            and request.accept_mimetypes.accept_json
            and not request.accept_mimetypes.accept_html
        ):
            return jsonify({"error": "Uploaded file exceeds the 10 MB limit."}), 413
        flash("The uploaded file exceeds the 10 MB limit.", "danger")
        if request.referrer:
            ref_url = urlparse(request.referrer)
            if not ref_url.netloc or ref_url.netloc == request.host:
                path = ref_url.path
                if ref_url.query:
                    path += f"?{ref_url.query}"
                return redirect(path)
        return redirect("/books")

    # Register blueprints to add routes to the app
    app.register_blueprint(HTML_BLUEPRINT)

    # Add before_request hook for automatic write protection
    @app.before_request
    def require_auth_for_writes():
        # Login must always be accessible, including its POST request.
        if request.path == "/login":
            return None

        # Allow read-only requests.
        if request.method in ('GET', 'HEAD', 'OPTIONS'):
            return None

        # Authenticated users may perform writes.
        if session.get('authenticated'):
            return None

        # API/fetch request.
        if request.is_json or (
                request.accept_mimetypes
                and request.accept_mimetypes.accept_json
                and not request.accept_mimetypes.accept_html
        ):
            if request.referrer:
                ref_url = urlparse(request.referrer)
                path = ref_url.path
                if ref_url.query:
                    path += f"?{ref_url.query}"

                if path.startswith('/') and not path.startswith('//'):
                    session['next'] = path

            return jsonify({'error': 'Authentication required'}), 401

        # Browser request.
        session['next'] = request.full_path.rstrip('?')
        return redirect('/login')

    return app
