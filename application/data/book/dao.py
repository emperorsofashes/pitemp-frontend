import logging
import pickle
from datetime import datetime
from typing import Any

import fakeredis
from bson import ObjectId
from pymongo.collection import Collection
from pymongo.database import Database

from application.constants.book_constants import BOOKS_CACHE_TTL, BOOKS_COLLECTION_NAME, BOOKS_DB_NAME
from application.data.book.book import Book

LOG = logging.getLogger(__name__)


class BookDao:
    def __init__(self, client, database: Database = None, cache=None):
        self.cache = cache or fakeredis.FakeValkey()
        self.client = client
        self.database: Database = database if database is not None else self.client[BOOKS_DB_NAME]
        self.books_collection: Collection = self.database[BOOKS_COLLECTION_NAME]

        LOG.info(f"Connected to database: {BOOKS_DB_NAME}")

    def _get_cached(self, key: str) -> Any | None:
        try:
            cached = self.cache.get(key)
            return pickle.loads(cached) if cached else None
        except Exception as e:
            LOG.warning(f"Cache get failed for key {key}: {e}")
            return None

    def _set_cached(self, key: str, value: Any) -> None:
        try:
            self.cache.set(key, pickle.dumps(value), ex=BOOKS_CACHE_TTL)
        except Exception as e:
            LOG.warning(f"Cache set failed for key {key}: {e}")

    def _retry_cache_delete_async(self, key: str, max_retries: int = 3, initial_delay: float = 1.0) -> None:
        """Retry cache delete operation: first sync (3 attempts), then async with exponential backoff."""
        for attempt in range(max_retries):
            try:
                self.cache.delete(key)
                LOG.info(f"Cache delete succeeded for key {key} on sync attempt {attempt + 1}")
                return
            except Exception as e:
                if attempt < max_retries - 1:
                    LOG.warning(f"Cache delete failed for key {key} on sync attempt {attempt + 1}: {e}")
                else:
                    LOG.warning(f"Cache delete failed for key {key} after {max_retries} sync attempts, switching to async retry")
        
        def _async_retry():
            for attempt in range(max_retries):
                try:
                    self.cache.delete(key)
                    LOG.info(f"Cache delete succeeded for key {key} on async attempt {attempt + 1}")
                    return
                except Exception as e:
                    if attempt < max_retries - 1:
                        delay = initial_delay * (2 ** attempt)
                        LOG.warning(f"Cache delete failed for key {key} on async attempt {attempt + 1}, retrying in {delay}s: {e}")
                    else:
                        LOG.error(f"Cache delete failed for key {key} after {max_retries} async attempts: {e}")
        
        import threading
        import time
        thread = threading.Thread(target=_async_retry, daemon=True)
        thread.start()

    def get_all_books(self, sort_by: str = "date_added", sort_order: int = -1) -> list[Book]:
        """Get all books with optional sorting."""
        cache_key = f"all_books_{sort_by}_{sort_order}"
        cached = self._get_cached(cache_key)
        if cached is not None:
            return cached

        # Determine sort field
        sort_field = "date_added"
        if sort_by == "title":
            sort_field = "title"
        elif sort_by == "date_published":
            sort_field = "date_published"
        elif sort_by == "page_count":
            sort_field = "page_count"

        query = self.books_collection.find().sort(sort_field, sort_order)
        books = [Book.from_mongo(doc) for doc in query]
        self._set_cached(cache_key, books)
        return books

    def get_book(self, book_id: str) -> Book | None:
        """Get a book by its MongoDB _id."""
        cache_key = f"book_{book_id}"
        cached = self._get_cached(cache_key)
        if cached is not None:
            return cached

        try:
            doc = self.books_collection.find_one({"_id": ObjectId(book_id)})
            book = Book.from_mongo(doc) if doc else None
            if book:
                self._set_cached(cache_key, book)
            return book
        except Exception:
            return None

    def add_book(
        self,
        title: str,
        authors: list[str],
        date_published: datetime | None = None,
        isbn: str | None = None,
        oclc_number: str | None = None,
        page_count: int | None = None,
    ) -> str:
        """Add a book to the collection."""
        document = {
            "title": title,
            "authors": authors,
            "date_published": date_published,
            "isbn": isbn,
            "oclc_number": oclc_number,
            "page_count": page_count,
            "date_added": datetime.now(),
        }
        result = self.books_collection.insert_one(document)
        self._retry_cache_delete_async("all_books_title_-1")
        self._retry_cache_delete_async("all_books_date_published_-1")
        self._retry_cache_delete_async("all_books_date_added_-1")
        self._retry_cache_delete_async("all_books_page_count_-1")
        return str(result.inserted_id)

    def delete_book(self, book_id: str) -> bool:
        """Delete a book from the collection."""
        try:
            result = self.books_collection.delete_one({"_id": ObjectId(book_id)})
            self._retry_cache_delete_async("all_books_title_-1")
            self._retry_cache_delete_async("all_books_date_published_-1")
            self._retry_cache_delete_async("all_books_date_added_-1")
            self._retry_cache_delete_async("all_books_page_count_-1")
            return result.deleted_count > 0
        except Exception:
            return False

    def get_num_total_books(self) -> int:
        """Get total count of books."""
        return self.books_collection.count_documents({})
