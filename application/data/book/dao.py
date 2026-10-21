import logging
import os
import pickle
from datetime import datetime, timedelta
from typing import Any

import fakeredis
from bson import ObjectId
from pymongo.collection import Collection
from pymongo.database import Database

from application.constants.book_constants import BOOKS_CACHE_TTL, BOOKS_COLLECTION_NAME, BOOKS_DB_NAME
from application.data.book.book import Book


class DuplicateBookError(Exception):
    """Raised when attempting to add a duplicate book."""
    pass

LOG = logging.getLogger(__name__)
ISBN_LOOKUP_CACHE_TTL = timedelta(days=30)  # Cache ISBN lookups for 30 days
BOOK_SEARCH_CACHE_TTL = timedelta(days=7)  # Cache book searches for 7 days


class BookDao:
    def __init__(self, client, database: Database = None, cache=None):
        self.cache = cache or fakeredis.FakeValkey()
        self.client = client
        self.database: Database = database if database is not None else self.client[BOOKS_DB_NAME]
        self.books_collection: Collection = self.database[BOOKS_COLLECTION_NAME]

        # Support resetting the cache for development testing
        if os.environ.get("RESET_CACHE", "false") == "true":
            LOG.info("Flushing cache")
            self.cache.flushall()

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

    def check_duplicate(self, title: str, isbn: str | None = None, oclc_number: str | None = None, exclude_id: str | None = None) -> tuple[bool, str]:
        """Check if a book with the same title, ISBN, or OCLC already exists.
        
        Args:
            title: The book title to check
            isbn: The ISBN to check (optional)
            oclc_number: The OCLC number to check (optional)
            exclude_id: Book ID to exclude from duplicate check (for updates)
        
        Returns:
            Tuple of (is_duplicate, error_message)
        """
        query = {"$or": []}
        
        # Check title (case-insensitive)
        if title:
            query["$or"].append({"title": {"$regex": f"^{title}$", "$options": "i"}})
        
        # Check ISBN (if provided)
        if isbn:
            query["$or"].append({"isbn": isbn})
        
        # Check OCLC (if provided)
        if oclc_number:
            query["$or"].append({"oclc_number": oclc_number})
        
        # Exclude the current book when updating
        if exclude_id:
            query["_id"] = {"$ne": ObjectId(exclude_id)}
        
        # If no fields to check, return False
        if not query["$or"]:
            return False, ""
        
        existing = self.books_collection.find_one(query)
        if existing:
            existing_book = Book.from_mongo(existing)
            # Determine which field matched
            if isbn and existing_book.isbn == isbn:
                return True, f"A book with ISBN '{isbn}' already exists"
            elif oclc_number and existing_book.oclc_number == oclc_number:
                return True, f"A book with OCLC number '{oclc_number}' already exists"
            elif title.lower() == existing_book.title.lower():
                return True, f"A book with title '{title}' already exists"
        
        return False, ""

    def add_book(
        self,
        title: str,
        authors: list[str],
        date_published: datetime | None = None,
        isbn: str | None = None,
        oclc_number: str | None = None,
        page_count: int | None = None,
        purchase_price: float | None = None,
        notes: str | None = None,
    ) -> str:
        """Add a book to the collection."""
        # Check for duplicates before adding
        is_duplicate, error_message = self.check_duplicate(title, isbn, oclc_number)
        if is_duplicate:
            raise DuplicateBookError(error_message)
        
        document = {
            "title": title,
            "authors": authors,
            "date_published": date_published,
            "isbn": isbn,
            "oclc_number": oclc_number,
            "page_count": page_count,
            "date_added": datetime.now(),
            "purchase_price": purchase_price,
            "notes": notes,
        }
        result = self.books_collection.insert_one(document)
        self._retry_cache_delete_async("all_books_title_-1")
        self._retry_cache_delete_async("all_books_date_published_-1")
        self._retry_cache_delete_async("all_books_date_added_-1")
        self._retry_cache_delete_async("all_books_page_count_-1")
        return str(result.inserted_id)

    def update_book(
        self,
        book_id: str,
        title: str,
        authors: list[str],
        date_published: datetime | None = None,
        isbn: str | None = None,
        oclc_number: str | None = None,
        page_count: int | None = None,
        purchase_price: float | None = None,
        notes: str | None = None,
    ) -> bool:
        """Update a book in the collection."""
        try:
            # Check for duplicates before updating (exclude current book)
            is_duplicate, error_message = self.check_duplicate(title, isbn, oclc_number, exclude_id=book_id)
            if is_duplicate:
                raise DuplicateBookError(error_message)
            
            document = {
                "title": title,
                "authors": authors,
                "date_published": date_published,
                "isbn": isbn,
                "oclc_number": oclc_number,
                "page_count": page_count,
                "purchase_price": purchase_price,
                "notes": notes,
            }
            result = self.books_collection.update_one({"_id": ObjectId(book_id)}, {"$set": document})
            self._retry_cache_delete_async("all_books_title_-1")
            self._retry_cache_delete_async("all_books_date_published_-1")
            self._retry_cache_delete_async("all_books_date_added_-1")
            self._retry_cache_delete_async("all_books_page_count_-1")
            self._retry_cache_delete_async(f"book_{book_id}")
            return result.modified_count > 0
        except DuplicateBookError:
            raise
        except Exception:
            return False

    def delete_book(self, book_id: str) -> bool:
        """Delete a book from the collection."""
        try:
            result = self.books_collection.delete_one({"_id": ObjectId(book_id)})
            self._retry_cache_delete_async("all_books_title_-1")
            self._retry_cache_delete_async("all_books_date_published_-1")
            self._retry_cache_delete_async("all_books_date_added_-1")
            self._retry_cache_delete_async("all_books_page_count_-1")
            self._retry_cache_delete_async(f"book_{book_id}")
            return result.deleted_count > 0
        except Exception:
            return False


    def get_num_total_books(self) -> int:
        """Get total count of books."""
        return self.books_collection.count_documents({})

    def cache_isbn_lookup(self, isbn: str, metadata: dict) -> None:
        """Cache ISBN lookup result."""
        cache_key = f"isbn_lookup_{isbn}"
        try:
            self.cache.set(cache_key, pickle.dumps(metadata), ex=ISBN_LOOKUP_CACHE_TTL)
        except Exception as e:
            LOG.warning(f"Failed to cache ISBN lookup for {isbn}: {e}")

    def get_cached_isbn_lookup(self, isbn: str) -> dict | None:
        """Get cached ISBN lookup result."""
        cache_key = f"isbn_lookup_{isbn}"
        try:
            cached = self.cache.get(cache_key)
            return pickle.loads(cached) if cached else None
        except Exception as e:
            LOG.warning(f"Failed to retrieve cached ISBN lookup for {isbn}: {e}")
            return None

    def cache_book_search(self, query: str, results: list, provider_status: dict) -> None:
        """Cache book search result."""
        cache_key = f"book_search_{query.lower().strip()}"
        try:
            cache_data = {
                "results": results,
                "provider_status": provider_status
            }
            self.cache.set(cache_key, pickle.dumps(cache_data), ex=BOOK_SEARCH_CACHE_TTL)
        except Exception as e:
            LOG.warning(f"Failed to cache book search for '{query}': {e}")

    def get_cached_book_search(self, query: str) -> tuple[list, dict] | None:
        """Get cached book search result."""
        cache_key = f"book_search_{query.lower().strip()}"
        try:
            cached = self.cache.get(cache_key)
            if cached:
                cache_data = pickle.loads(cached)
                return cache_data.get("results", []), cache_data.get("provider_status", {})
            return None
        except Exception as e:
            LOG.warning(f"Failed to retrieve cached book search for '{query}': {e}")
            return None
