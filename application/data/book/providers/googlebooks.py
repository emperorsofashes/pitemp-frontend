import logging
import os
import re
from datetime import datetime

import requests

from application.data.book.providers.base import BookMetadata, BookMetadataProvider

LOG = logging.getLogger(__name__)


class GoogleBooksProvider(BookMetadataProvider):
    """Provider for Google Books API."""

    def __init__(self, timeout: int = 10, api_key: str | None = None):
        super().__init__(timeout)
        self.name = "Google Books"
        # Read API key from environment variable if not provided
        self.api_key = api_key or os.environ.get("GOOGLE_BOOKS_API_KEY")

    def lookup(self, isbn: str) -> BookMetadata | None:
        """Look up book metadata by ISBN using Google Books API."""
        isbn_clean = self._normalize_isbn(isbn)

        try:
            # Build URL
            url = f"https://www.googleapis.com/books/v1/volumes?q=isbn:{isbn_clean}"
            
            # Build headers with API key if available
            headers = {"User-Agent": "BookCatalog/1.0"}
            if self.api_key:
                headers["X-Goog-Api-Key"] = self.api_key
            
            resp = requests.get(url, timeout=self.timeout, headers=headers)

            if resp.status_code != 200:
                LOG.warning(f"Google Books API returned status {resp.status_code}")
                return None

            data = resp.json()

            if "items" not in data or not data["items"]:
                return None

            # Use the first result (should be the best match for ISBN)
            book_data = data["items"][0].get("volumeInfo", {})
            metadata = BookMetadata()

            # Extract title
            if "title" in book_data:
                metadata.title = book_data["title"]

            # Extract authors
            if "authors" in book_data:
                metadata.authors = book_data["authors"]

            # Extract publish date
            if "publishedDate" in book_data:
                publish_date = book_data["publishedDate"]
                if isinstance(publish_date, str):
                    # Try various date formats
                    for fmt in ["%Y-%m-%d", "%Y", "%B %Y", "%b %Y"]:
                        try:
                            if fmt == "%Y":
                                metadata.date_published = datetime.strptime(publish_date[:4], fmt)
                            else:
                                metadata.date_published = datetime.strptime(publish_date, fmt)
                            break
                        except ValueError:
                            continue

            # Extract page count
            if "pageCount" in book_data:
                try:
                    metadata.page_count = int(book_data["pageCount"])
                except (ValueError, TypeError):
                    pass

            # Extract publisher
            if "publisher" in book_data:
                metadata.publisher = book_data["publisher"]

            # Extract description
            if "description" in book_data:
                metadata.description = book_data["description"]

            # Extract cover image
            if "imageLinks" in book_data:
                image_links = book_data["imageLinks"]
                # Prefer larger images
                metadata.cover_url = (
                    image_links.get("extraLarge") or
                    image_links.get("large") or
                    image_links.get("medium") or
                    image_links.get("thumbnail") or
                    image_links.get("smallThumbnail")
                )

            # Extract ISBN from identifiers
            if "industryIdentifiers" in book_data:
                for identifier in book_data["industryIdentifiers"]:
                    if identifier.get("type") in ["ISBN_10", "ISBN_13"]:
                        metadata.isbn = identifier.get("identifier")
                        break

            # Fallback to input ISBN if not found
            if not metadata.isbn:
                metadata.isbn = isbn_clean

            # Track source
            if self._has_data(metadata):
                metadata.source_providers = {self.name: "primary"}

            return metadata

        except requests.Timeout:
            LOG.warning("Google Books API request timed out")
            return None
        except Exception as e:
            LOG.error(f"Error during Google Books lookup: {e}")
            return None
