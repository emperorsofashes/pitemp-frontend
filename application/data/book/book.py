from dataclasses import dataclass
from datetime import datetime


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
        )
