import os
from dataclasses import dataclass
from datetime import datetime

from application.constants.book_constants import BOOK_IMAGE_HOST


@dataclass(kw_only=True)
class Book:
    id: str
    title: str
    authors: list[str] | None = None
    date_published: datetime | None = None
    isbn: str | None = None
    oclc_number: str | None = None
    page_count: int | None = None
    date_added: datetime | None = None
    purchase_price: float | None = None
    notes: str | None = None
    cover_uploaded_at: datetime | None = None
    cover_version: int = 0

    @property
    def cover_key(self) -> str:
        """Derive cover key deterministically from book ID."""
        return f"covers/{self.id}.webp"

    @property
    def thumb_key(self) -> str:
        """Derive thumbnail key deterministically from book ID."""
        return f"covers/{self.id}_thumb.webp"

    @property
    def has_cover(self) -> bool:
        """Indicates whether a cover is recorded as present."""
        return self.cover_uploaded_at is not None

    @property
    def thumb_url(self) -> str | None:
        """Construct full public URL for thumbnail with version parameter."""
        if not self.has_cover:
            return None
        host = os.environ.get("BOOK_IMAGE_HOST") or os.environ.get("R2_PUBLIC_URL") or BOOK_IMAGE_HOST
        if not self.thumb_key or not host:
            return None
        base_url = f"{host.rstrip('/')}/{self.thumb_key.lstrip('/')}"
        return f"{base_url}?v={self.cover_version}" if self.cover_version > 0 else base_url

    @property
    def cover_url(self) -> str | None:
        """Construct full public URL for full-size cover with version parameter."""
        if not self.has_cover:
            return None
        host = os.environ.get("BOOK_IMAGE_HOST") or os.environ.get("R2_PUBLIC_URL") or BOOK_IMAGE_HOST
        if not self.cover_key or not host:
            return None
        base_url = f"{host.rstrip('/')}/{self.cover_key.lstrip('/')}"
        return f"{base_url}?v={self.cover_version}" if self.cover_version > 0 else base_url

    @classmethod
    def from_mongo(cls, doc: dict) -> "Book":
        return cls(
            id=str(doc["_id"]),
            title=doc.get("title", ""),
            authors=doc.get("authors", []),
            date_published=doc.get("date_published"),
            isbn=doc.get("isbn"),
            oclc_number=doc.get("oclc_number"),
            page_count=doc.get("page_count"),
            date_added=doc.get("date_added"),
            purchase_price=doc.get("purchase_price"),
            notes=doc.get("notes"),
            cover_uploaded_at=doc.get("cover_uploaded_at"),
            cover_version=doc.get("cover_version", 0),
        )
