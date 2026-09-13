import os
from datetime import timedelta

# Database configuration
BIRD_DB_NAME = "birdlife"
BIRDS_COLLECTION_NAME = "birds"
LIFE_LIST_COLLECTION_NAME = "life_list"

# Cache TTL
BIRD_CACHE_TTL = timedelta(hours=1)

# Image hosting & Maps
BIRD_IMAGE_HOST = os.environ.get("BIRD_IMAGE_HOST", "")
CARTO_API_KEY = os.environ.get("CARTO_API_KEY", "")
