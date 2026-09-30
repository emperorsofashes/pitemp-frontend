from dataclasses import dataclass, field
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


@dataclass(kw_only=True)
class SearchResult:
    """Normalized search result from providers."""
    title: str
    authors: list[str] = field(default_factory=list)
    publisher: str | None = None
    publication_date: datetime | None = None
    publication_year: int | None = None
    page_count: int | None = None
    isbn_10: str | None = None
    isbn_13: str | None = None
    description: str | None = None
    edition: str | None = None
    series: str | None = None
    subjects: list[str] = field(default_factory=list)
    language: str | None = None
    cover_url: str | None = None
    provider: str = ""  # Name of the provider
    provider_record_id: str = ""  # Provider's internal ID for this record
    source_url: str | None = None  # URL to view the record on the provider's site

    def get_isbn(self) -> str | None:
        """Return ISBN-13 if available, otherwise ISBN-10."""
        return self.isbn_13 or self.isbn_10

    def to_book_metadata(self) -> BookMetadata:
        """Convert to BookMetadata for form population."""
        return BookMetadata(
            title=self.title,
            authors=self.authors,
            date_published=self.publication_date,
            isbn=self.get_isbn(),
            page_count=self.page_count,
            publisher=self.publisher,
            description=self.description,
            cover_url=self.cover_url,
            source_providers={self.provider: "primary"}
        )


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

    def search(self, query: str, max_results: int = 10) -> list[SearchResult]:
        """
        Search for books by keyword query.
        
        Args:
            query: Search query string
            max_results: Maximum number of results to return
            
        Returns:
            List of SearchResult objects
        """
        raise NotImplementedError("Subclasses must implement search method")

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
