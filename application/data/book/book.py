import os
from dataclasses import dataclass
from datetime import datetime

from application.constants.book_constants import BOOK_IMAGE_HOST


@dataclass(kw_only=True)
class Book:
    id: str
    title: str
    authors: list[str]
    date_published: datetime | None = None
    isbn: str | None = None
    oclc_number: str | None = None
    page_count: int | None = None
    date_added: datetime | None = None
    cover_key: str | None = None

    @property
    def thumb_key(self) -> str | None:
        """Derive thumbnail key deterministically from cover_key."""
        if not self.cover_key:
            return None
        if self.cover_key.endswith(".avif"):
            return f"{self.cover_key[:-5]}_thumb.avif"
        return f"{self.cover_key}_thumb"

    @property
    def thumb_url(self) -> str | None:
        """Construct full public URL for thumbnail."""
        host = os.environ.get("BOOK_IMAGE_HOST") or os.environ.get("R2_PUBLIC_URL") or BOOK_IMAGE_HOST
        if not self.thumb_key or not host:
            return None
        return f"{host.rstrip('/')}/{self.thumb_key.lstrip('/')}"

    @property
    def cover_url(self) -> str | None:
        """Construct full public URL for full-size cover."""
        host = os.environ.get("BOOK_IMAGE_HOST") or os.environ.get("R2_PUBLIC_URL") or BOOK_IMAGE_HOST
        if not self.cover_key or not host:
            return None
        return f"{host.rstrip('/')}/{self.cover_key.lstrip('/')}"

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
            cover_key=doc.get("cover_key"),
        )
