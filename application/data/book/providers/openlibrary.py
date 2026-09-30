import logging
import re
from datetime import datetime

import requests

from application.data.book.providers.base import BookMetadata, BookMetadataProvider

LOG = logging.getLogger(__name__)


class OpenLibraryProvider(BookMetadataProvider):
    """Provider for Open Library Books API."""

    def __init__(self, timeout: int = 10):
        super().__init__(timeout)
        self.name = "Open Library"

    def lookup(self, isbn: str) -> BookMetadata | None:
        """Look up book metadata by ISBN using Open Library API."""
        isbn_clean = self._normalize_isbn(isbn)

        try:
            url = f"https://openlibrary.org/api/books?bibkeys=ISBN:{isbn_clean}&format=json&jscmd=data"
            resp = requests.get(url, timeout=self.timeout, headers={"User-Agent": "BookCatalog/1.0"})

            if resp.status_code != 200:
                LOG.warning(f"Open Library API returned status {resp.status_code}")
                return None

            data = resp.json()
            key = f"ISBN:{isbn_clean}"

            if key not in data or not data[key]:
                return None

            book_data = data[key]
            metadata = BookMetadata()

            # Extract title
            if "title" in book_data:
                metadata.title = book_data["title"]

            # Extract authors
            if "authors" in book_data:
                metadata.authors = [author.get("name", "") for author in book_data["authors"] if author.get("name")]

            # Extract publish date
            if "publish_date" in book_data:
                publish_date = book_data["publish_date"]
                if isinstance(publish_date, str):
                    # Try to parse as full date first
                    try:
                        metadata.date_published = datetime.strptime(publish_date, "%Y-%m-%d")
                    except ValueError:
                        # Try to extract just the year
                        year_match = re.search(r"\d{4}", publish_date)
                        if year_match:
                            metadata.date_published = datetime.strptime(year_match.group() + "-01-01", "%Y-%m-%d")

            # Extract page count
            if "number_of_pages" in book_data:
                try:
                    metadata.page_count = int(book_data["number_of_pages"])
                except (ValueError, TypeError):
                    pass

            # Extract publisher
            if "publishers" in book_data:
                publishers = book_data["publishers"]
                if publishers and isinstance(publishers, list) and len(publishers) > 0:
                    metadata.publisher = publishers[0].get("name", "")

            # Extract cover image
            if "cover" in book_data:
                cover_data = book_data["cover"]
                if isinstance(cover_data, dict):
                    metadata.cover_url = cover_data.get("large") or cover_data.get("medium") or cover_data.get("small")

            # Extract ISBN
            metadata.isbn = isbn_clean

            # Track source
            if self._has_data(metadata):
                metadata.source_providers = {self.name: "primary"}

            return metadata

        except requests.Timeout:
            LOG.warning("Open Library API request timed out")
            return None
        except Exception as e:
            LOG.error(f"Error during Open Library lookup: {e}")
            return None
