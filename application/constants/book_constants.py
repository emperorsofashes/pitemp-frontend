import os
from datetime import timedelta

# Database configuration
BOOKS_DB_NAME = "books"
BOOKS_COLLECTION_NAME = "books"

# Cache TTL
BOOKS_CACHE_TTL = timedelta(hours=1)

# Image hosting
BOOK_IMAGE_HOST = os.environ.get("BOOK_IMAGE_HOST", "")
