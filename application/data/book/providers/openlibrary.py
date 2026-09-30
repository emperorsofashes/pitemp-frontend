import logging
import re
from datetime import datetime
from urllib.parse import quote

import requests

from application.data.book.providers.base import BookMetadata, BookMetadataProvider, SearchResult

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

    def search(self, query: str, max_results: int = 10) -> list[SearchResult]:
        """Search for books by keyword using Open Library Search API."""
        try:
            # Use Open Library Search API
            url = f"https://openlibrary.org/search.json?q={quote(query)}&limit={max_results}&fields=title,author_name,publisher,first_publish_year,number_of_pages,isbn,cover_i,key"
            resp = requests.get(url, timeout=self.timeout, headers={"User-Agent": "BookCatalog/1.0"})

            if resp.status_code != 200:
                LOG.warning(f"Open Library Search API returned status {resp.status_code}")
                return []

            data = resp.json()
            results = []

            if "docs" not in data:
                return []

            for doc in data["docs"][:max_results]:
                # Extract ISBNs
                isbn_10 = None
                isbn_13 = None
                if "isbn" in doc and doc["isbn"]:
                    for isbn in doc["isbn"]:
                        if len(isbn) == 10:
                            isbn_10 = isbn
                        elif len(isbn) == 13:
                            isbn_13 = isbn

                # Extract publication date
                publication_date = None
                publication_year = None
                if "first_publish_year" in doc:
                    publication_year = doc["first_publish_year"]
                    try:
                        publication_date = datetime(publication_year, 1, 1)
                    except (ValueError, TypeError):
                        pass

                # Build cover URL
                cover_url = None
                if "cover_i" in doc:
                    cover_url = f"https://covers.openlibrary.org/b/id/{doc['cover_i']}-L.jpg"

                # Build source URL
                source_url = None
                if "key" in doc:
                    source_url = f"https://openlibrary.org{doc['key']}"

                result = SearchResult(
                    title=doc.get("title", ""),
                    authors=doc.get("author_name", []),
                    publisher=doc.get("publisher", [None])[0] if doc.get("publisher") else None,
                    publication_date=publication_date,
                    publication_year=publication_year,
                    page_count=doc.get("number_of_pages"),
                    isbn_10=isbn_10,
                    isbn_13=isbn_13,
                    cover_url=cover_url,
                    provider=self.name,
                    provider_record_id=doc.get("key", ""),
                    source_url=source_url
                )
                results.append(result)

            return results

        except requests.Timeout:
            LOG.warning("Open Library Search API request timed out")
            return []
        except Exception as e:
            LOG.error(f"Error during Open Library search: {e}")
            return []
