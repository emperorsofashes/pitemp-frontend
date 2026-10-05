import logging
from datetime import datetime

import requests

from application.data.book.providers.base import BookMetadata, BookMetadataProvider, SearchResult

LOG = logging.getLogger(__name__)


class OpenBDProvider(BookMetadataProvider):
    """Provider for openBD API (Japanese book metadata)."""

    def __init__(self, timeout: int = 10):
        super().__init__(timeout)
        self.name = "openBD"
        self.base_url = "https://api.openbd.jp/v1/get"

    def lookup(self, isbn: str) -> BookMetadata | None:
        """Look up book metadata by ISBN using openBD API."""
        isbn_clean = self.normalize_isbn(isbn)

        try:
            # Build URL
            url = f"{self.base_url}?isbn={isbn_clean}"
            
            resp = requests.get(url, timeout=self.timeout, headers={"User-Agent": "BookCatalog/1.0"})

            if resp.status_code != 200:
                LOG.warning(f"openBD API returned status {resp.status_code}")
                return None

            data = resp.json()

            # openBD returns a list, empty list means no match
            if not data or not isinstance(data, list):
                return None

            # Use the first result
            book_data = data[0]
            
            # Check if the result has the expected structure
            if not book_data or "summary" not in book_data:
                return None

            summary = book_data["summary"]
            metadata = BookMetadata()

            # Extract title
            if "title" in summary:
                metadata.title = summary["title"]

            # Extract subtitle if available
            title = metadata.title or ""
            if "volume" in summary and summary["volume"]:
                title = f"{title} {summary['volume']}".strip()
                metadata.title = title

            # Extract authors (openBD uses "author" field)
            if "author" in summary:
                authors_str = summary["author"]
                if authors_str:
                    # openBD may return authors as a string with various separators
                    # Common formats: "Author1, Author2" or "Author1／Author2"
                    for separator in [",", "／", "/", ";"]:
                        if separator in authors_str:
                            metadata.authors = [a.strip() for a in authors_str.split(separator)]
                            break
                    if not metadata.authors:
                        metadata.authors = [authors_str.strip()]

            # Extract publisher
            if "publisher" in summary:
                metadata.publisher = summary["publisher"]

            # Extract publication date
            if "pubdate" in summary:
                pubdate_str = summary["pubdate"]
                if pubdate_str:
                    # openBD dates are typically in YYYYMMDD format
                    try:
                        if len(pubdate_str) >= 4:
                            year = int(pubdate_str[:4])
                            month = int(pubdate_str[4:6]) if len(pubdate_str) >= 6 else 1
                            day = int(pubdate_str[6:8]) if len(pubdate_str) >= 8 else 1
                            metadata.date_published = datetime(year, month, day)
                    except (ValueError, TypeError):
                        pass

            # Extract page count
            if "extent" in summary:
                extent_str = summary["extent"]
                if extent_str:
                    # Try to extract number from extent (e.g., "300p")
                    import re
                    page_match = re.search(r"\d+", extent_str)
                    if page_match:
                        try:
                            metadata.page_count = int(page_match.group())
                        except (ValueError, TypeError):
                            pass

            # Extract ISBN
            if "isbn" in summary:
                metadata.isbn = summary["isbn"]
            else:
                metadata.isbn = isbn_clean

            # Extract description from "han" field if available
            if "han" in summary and summary["han"]:
                metadata.description = summary["han"]

            # Extract cover image URL from "cover" field
            if "cover" in summary and summary["cover"]:
                cover_url = summary["cover"]
                # Ensure HTTPS
                if cover_url.startswith("http://"):
                    cover_url = "https://" + cover_url[7:]
                metadata.cover_url = cover_url

            # Track source
            if self.has_data(metadata):
                metadata.source_providers = {self.name: "primary"}

            return metadata

        except requests.Timeout:
            LOG.warning("openBD API request timed out")
            return None
        except requests.RequestException as e:
            LOG.error(f"openBD request failed: {e}")
            return None
        except Exception as e:
            LOG.error(f"Error during openBD lookup: {e}")
            return None

    def search(self, query: str, max_results: int = 10) -> list[SearchResult]:
        """
        Search for books by keyword using openBD API.
        
        Note: openBD API is primarily ISBN-based and does not support
        general keyword search. This method returns empty results.
        """
        LOG.warning("openBD does not support keyword search, only ISBN lookup")
        return []
