from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass(kw_only=True)
class BookMetadata:
    """Normalized book metadata from providers."""
    title: str | None = None
    authors: list[str] | None = None
    date_published: datetime | None = None
    isbn: str | None = None
    page_count: int | None = None
    publisher: str | None = None
    description: str | None = None
    cover_url: str | None = None
    source_providers: dict[str, dict[str, Any]] = None  # Track which provider supplied which field

    def __post_init__(self):
        if self.source_providers is None:
            self.source_providers = {}

    def merge(self, other: "BookMetadata", provider_name: str) -> None:
        """Merge another metadata object into this one, tracking sources."""
        if other.title and not self.title:
            self.title = other.title
            self.source_providers["title"] = provider_name

        if other.authors and not self.authors:
            self.authors = other.authors
            self.source_providers["authors"] = provider_name

        if other.date_published and not self.date_published:
            self.date_published = other.date_published
            self.source_providers["date_published"] = provider_name

        if other.isbn and not self.isbn:
            self.isbn = other.isbn
            self.source_providers["isbn"] = provider_name

        if other.page_count and not self.page_count:
            self.page_count = other.page_count
            self.source_providers["page_count"] = provider_name

        if other.publisher and not self.publisher:
            self.publisher = other.publisher
            self.source_providers["publisher"] = provider_name

        if other.description and not self.description:
            self.description = other.description
            self.source_providers["description"] = provider_name

        if other.cover_url and not self.cover_url:
            self.cover_url = other.cover_url
            self.source_providers["cover_url"] = provider_name


class BookMetadataProvider:
    """Base class for book metadata providers."""

    def __init__(self, timeout: int = 10):
        self.timeout = timeout
        self.name = self.__class__.__name__

    def lookup(self, isbn: str) -> BookMetadata | None:
        """
        Look up book metadata by ISBN.
        
        Args:
            isbn: Normalized ISBN (without hyphens or spaces)
            
        Returns:
            BookMetadata object if found, None otherwise
        """
        raise NotImplementedError("Subclasses must implement lookup method")

    def _normalize_isbn(self, isbn: str) -> str:
        """Remove hyphens and spaces from ISBN."""
        return isbn.replace("-", "").replace(" ", "")

    def _has_data(self, metadata: BookMetadata) -> bool:
        """Check if metadata contains any useful information."""
        return bool(
            metadata.title or
            metadata.authors or
            metadata.date_published or
            metadata.page_count or
            metadata.publisher
        )
