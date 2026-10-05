import logging
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import quote

import requests

from application.data.book.providers.base import BookMetadata, BookMetadataProvider

LOG = logging.getLogger(__name__)


class MetadataMerger:
    """Merges metadata from multiple providers with conflict resolution."""

    def __init__(self):
        self.providers = []

    def add_provider(self, provider: BookMetadataProvider):
        """Add a provider to the merger."""
        self.providers.append(provider)

    def lookup(self, isbn: str) -> tuple[BookMetadata, dict[str, str]]:
        """
        Lookup ISBN across all providers and merge results.
        
        Returns:
            Tuple of (merged_metadata, provider_status)
            provider_status maps provider name to "success", "no_match", or "error"
        """
        merged_metadata = BookMetadata()
        provider_status = {}

        # Fetch from all providers in parallel to avoid worst-case serial latency.
        with ThreadPoolExecutor(max_workers=len(self.providers)) as executor:
            futures = {provider: executor.submit(provider.lookup, isbn) for provider in self.providers}

            for provider, future in futures.items():
                try:
                    metadata = future.result()

                    if metadata and provider.has_data(metadata):
                        # Merge this provider's data into the merged result
                        self._merge_metadata(merged_metadata, metadata, provider.name)
                        provider_status[provider.name] = 'success'
                    else:
                        provider_status[provider.name] = 'no_match'

                except Exception as e:
                    LOG.error(f'Error in provider {provider.name}: {e}')
                    provider_status[provider.name] = 'error'

        # If no cover was found by the providers during lookup, really try to find one automatically!
        if not merged_metadata.cover_url:
            self._try_find_cover(isbn, merged_metadata)

        return merged_metadata, provider_status

    @staticmethod
    def _merge_metadata(merged: BookMetadata, new: BookMetadata, provider_name: str) -> None:
        """
        Merge new metadata into merged metadata with conflict resolution.
        
        Rules:
        - Prefer exact ISBN matches over approximate
        - Prefer edition-specific info over general work-level
        - Preserve original values when providers disagree
        - Don't invent missing information
        - Track which provider supplied each field
        """
        # Title: Prefer first non-empty title
        if new.title and not merged.title:
            merged.title = new.title
            merged.source_providers["title"] = provider_name
        elif new.title and merged.title and new.title != merged.title:
            # Conflict - log it but keep original
            LOG.warning(
                f"Title conflict: '{merged.title}' vs '{new.title}' from {provider_name}. "
                f"Keeping original from {merged.source_providers.get('title', 'unknown')}"
            )

        # Authors: Merge author lists, avoiding duplicates
        if new.authors:
            if not merged.authors:
                merged.authors = new.authors
                merged.source_providers["authors"] = provider_name
            else:
                # Add new authors that aren't already in the list
                for author in new.authors:
                    if author not in merged.authors:
                        merged.authors.append(author)
                # Update source if we added new authors
                if len(new.authors) > 0:
                    if "authors" not in merged.source_providers:
                        merged.source_providers["authors"] = provider_name
                    else:
                        merged.source_providers["authors"] += f", {provider_name}"

        # Date published: Prefer more specific dates (full date over year only)
        if new.date_published:
            if not merged.date_published:
                merged.date_published = new.date_published
                merged.source_providers["date_published"] = provider_name
            elif new.date_published != merged.date_published:
                # Prefer the more specific date (check if one has time component)
                # For now, keep the first one found
                LOG.warning(
                    f"Date conflict: {merged.date_published} vs {new.date_published} from {provider_name}. "
                    f"Keeping original from {merged.source_providers.get('date_published', 'unknown')}"
                )

        # ISBN: Prefer the ISBN from the provider that matched exactly
        if new.isbn and not merged.isbn:
            merged.isbn = new.isbn
            merged.source_providers["isbn"] = provider_name

        # Page count: Prefer non-zero values
        if new.page_count and new.page_count > 0:
            if not merged.page_count or merged.page_count == 0:
                merged.page_count = new.page_count
                merged.source_providers["page_count"] = provider_name
            elif new.page_count != merged.page_count:
                LOG.warning(
                    f"Page count conflict: {merged.page_count} vs {new.page_count} from {provider_name}. "
                    f"Keeping original from {merged.source_providers.get('page_count', 'unknown')}"
                )

        # Publisher: Prefer first non-empty publisher
        if new.publisher and not merged.publisher:
            merged.publisher = new.publisher
            merged.source_providers["publisher"] = provider_name
        elif new.publisher and merged.publisher and new.publisher != merged.publisher:
            LOG.warning(
                f"Publisher conflict: '{merged.publisher}' vs '{new.publisher}' from {provider_name}. "
                f"Keeping original from {merged.source_providers.get('publisher', 'unknown')}"
            )

        # Description: Prefer first non-empty description
        if new.description and not merged.description:
            merged.description = new.description
            merged.source_providers["description"] = provider_name

        # Cover URL: Prefer larger/higher-resolution images
        if new.cover_url:
            if not merged.cover_url:
                merged.cover_url = new.cover_url
                merged.source_providers["cover_url"] = provider_name
            elif MetadataMerger._is_higher_res_cover(new.cover_url, merged.cover_url):
                merged.cover_url = new.cover_url
                merged.source_providers["cover_url"] = provider_name

    @staticmethod
    def _is_higher_res_cover(new_url: str, current_url: str) -> bool:
        """Heuristic to check if a new cover URL is higher quality than the current one."""
        def score(u: str) -> int:
            if not u:
                return 0
            u_lower = u.lower()
            if "-l." in u_lower or "extralarge" in u_lower:
                return 4
            if "-m." in u_lower or "large" in u_lower:
                return 3
            if "medium" in u_lower:
                return 2
            if "thumbnail" in u_lower:
                return 1
            return 1
        return score(new_url) > score(current_url)

    def _try_find_cover(self, isbn: str, merged: BookMetadata) -> None:
        """
        Exhaustively attempt to find a cover image for the book:
        1. Check Open Library Covers API directly by ISBN.
        2. If not found, and title is available, query Google Books by title/author.
        3. If not found, and title is available, query Open Library Search API by title.
        """
        clean_isbn = BookMetadataProvider.normalize_isbn(isbn) if isbn else ""
        if not clean_isbn and merged.isbn:
            clean_isbn = BookMetadataProvider.normalize_isbn(merged.isbn)

        # Strategy 1: Direct Open Library cover check by ISBN
        if clean_isbn:
            try:
                check_url = f"https://covers.openlibrary.org/b/isbn/{clean_isbn}-L.jpg?default=false"
                resp = requests.head(
                    check_url,
                    timeout=5,
                    allow_redirects=True,
                    headers={"User-Agent": "BookCatalog/1.0"}
                )
                if resp.status_code == 200:
                    merged.cover_url = f"https://covers.openlibrary.org/b/isbn/{clean_isbn}-L.jpg"
                    merged.source_providers["cover_url"] = "Open Library (Covers API)"
                    return
            except Exception as e:
                LOG.debug(f"Direct Open Library cover lookup failed: {e}")

        # Strategy 2: If title is available, search Google Books for a volume with cover
        if merged.title:
            try:
                query = f'intitle:"{merged.title}"'
                if merged.authors:
                    query += f' inauthor:"{merged.authors[0]}"'
                url = f"https://www.googleapis.com/books/v1/volumes?q={quote(query)}&maxResults=5"
                headers = {"User-Agent": "BookCatalog/1.0"}
                for p in self.providers:
                    if getattr(p, "api_key", None):
                        headers["X-Goog-Api-Key"] = p.api_key
                        break
                resp = requests.get(url, timeout=5, headers=headers)
                if resp.status_code == 200:
                    data = resp.json()
                    for item in data.get("items", []):
                        img_links = item.get("volumeInfo", {}).get("imageLinks", {})
                        raw_url = (
                            img_links.get("extraLarge") or
                            img_links.get("large") or
                            img_links.get("medium") or
                            img_links.get("thumbnail") or
                            img_links.get("smallThumbnail")
                        )
                        if raw_url:
                            if raw_url.startswith("http://"):
                                raw_url = "https://" + raw_url[7:]
                            merged.cover_url = raw_url
                            merged.source_providers["cover_url"] = "Google Books (Title Search)"
                            return
            except Exception as e:
                LOG.debug(f"Google Books title search for cover failed: {e}")

        # Strategy 3: Search Open Library by title
        if merged.title:
            try:
                ol_url = f"https://openlibrary.org/search.json?q={quote(merged.title)}&limit=5&fields=title,cover_i,cover_edition_key"
                resp = requests.get(ol_url, timeout=5, headers={"User-Agent": "BookCatalog/1.0"})
                if resp.status_code == 200:
                    data = resp.json()
                    for doc in data.get("docs", []):
                        if doc.get("cover_i"):
                            merged.cover_url = f"https://covers.openlibrary.org/b/id/{doc['cover_i']}-L.jpg"
                            merged.source_providers["cover_url"] = "Open Library (Title Search)"
                            return
                        if doc.get("cover_edition_key"):
                            merged.cover_url = f"https://covers.openlibrary.org/b/olid/{doc['cover_edition_key']}-L.jpg"
                            merged.source_providers["cover_url"] = "Open Library (Title Search)"
                            return
            except Exception as e:
                LOG.debug(f"Open Library title search for cover failed: {e}")

