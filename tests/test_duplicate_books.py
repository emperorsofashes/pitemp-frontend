import pytest
from unittest.mock import MagicMock, Mock, patch
from bson import ObjectId
from datetime import datetime

from application.data.book.dao import BookDao, DuplicateBookError
from application.data.book.book import Book


class TestDuplicateBookValidation:
    """Test duplicate book validation logic."""

    def test_check_duplicate_by_title(self):
        """Test that duplicate title detection works (case-insensitive)."""
        mock_client = MagicMock()
        mock_collection = MagicMock()
        mock_collection.find_one.return_value = {
            "_id": ObjectId("507f1f77bcf86cd799439011"),
            "title": "Test Book",
            "authors": ["Author"],
        }
        mock_database = MagicMock()
        mock_database.__getitem__.return_value = mock_collection
        mock_client.__getitem__.return_value = mock_database

        dao = BookDao(mock_client)
        
        is_duplicate, error_message = dao.check_duplicate(title="Test Book")
        assert is_duplicate is True
        assert "title" in error_message.lower()

    def test_check_duplicate_by_isbn(self):
        """Test that duplicate ISBN detection works."""
        mock_client = MagicMock()
        mock_collection = MagicMock()
        mock_collection.find_one.return_value = {
            "_id": ObjectId("507f1f77bcf86cd799439011"),
            "title": "Different Book",
            "isbn": "9780123456789",
        }
        mock_database = MagicMock()
        mock_database.__getitem__.return_value = mock_collection
        mock_client.__getitem__.return_value = mock_database

        dao = BookDao(mock_client)
        
        is_duplicate, error_message = dao.check_duplicate(title="New Book", isbn="9780123456789")
        assert is_duplicate is True
        assert "ISBN" in error_message

    def test_check_duplicate_by_oclc(self):
        """Test that duplicate OCLC detection works."""
        mock_client = MagicMock()
        mock_collection = MagicMock()
        mock_collection.find_one.return_value = {
            "_id": ObjectId("507f1f77bcf86cd799439011"),
            "title": "Different Book",
            "oclc_number": "12345678",
        }
        mock_database = MagicMock()
        mock_database.__getitem__.return_value = mock_collection
        mock_client.__getitem__.return_value = mock_database

        dao = BookDao(mock_client)
        
        is_duplicate, error_message = dao.check_duplicate(title="New Book", oclc_number="12345678")
        assert is_duplicate is True
        assert "OCLC" in error_message

    def test_check_duplicate_no_duplicate(self):
        """Test that no duplicate is detected when book doesn't exist."""
        mock_client = MagicMock()
        mock_collection = MagicMock()
        mock_collection.find_one.return_value = None
        mock_database = MagicMock()
        mock_database.__getitem__.return_value = mock_collection
        mock_client.__getitem__.return_value = mock_database

        dao = BookDao(mock_client)
        
        is_duplicate, error_message = dao.check_duplicate(title="New Book", isbn="9780123456789")
        assert is_duplicate is False
        assert error_message == ""

    def test_check_duplicate_exclude_id(self):
        """Test that exclude_id parameter works for updates."""
        mock_client = MagicMock()
        mock_collection = MagicMock()
        mock_collection.find_one.return_value = None
        mock_database = MagicMock()
        mock_database.__getitem__.return_value = mock_collection
        mock_client.__getitem__.return_value = mock_database

        dao = BookDao(mock_client)
        
        # When excluding the current book ID, it should not detect itself as duplicate
        is_duplicate, error_message = dao.check_duplicate(
            title="Test Book",
            isbn="9780123456789",
            exclude_id="507f1f77bcf86cd799439011"
        )
        assert is_duplicate is False

    def test_add_book_raises_duplicate_error(self):
        """Test that add_book raises DuplicateBookError for duplicates."""
        mock_client = MagicMock()
        mock_collection = MagicMock()
        mock_collection.find_one.return_value = {
            "_id": ObjectId("507f1f77bcf86cd799439011"),
            "title": "Test Book",
        }
        mock_collection.insert_one.return_value = MagicMock(inserted_id=ObjectId("507f1f77bcf86cd799439012"))
        mock_database = MagicMock()
        mock_database.__getitem__.return_value = mock_collection
        mock_client.__getitem__.return_value = mock_database

        dao = BookDao(mock_client)
        
        with pytest.raises(DuplicateBookError) as exc_info:
            dao.add_book(title="Test Book", authors=["Author"])
        assert "title" in str(exc_info.value).lower()

    def test_add_book_success_when_no_duplicate(self):
        """Test that add_book succeeds when no duplicate exists."""
        mock_client = MagicMock()
        mock_collection = MagicMock()
        mock_collection.find_one.return_value = None
        mock_collection.insert_one.return_value = MagicMock(inserted_id=ObjectId("507f1f77bcf86cd799439011"))
        mock_database = MagicMock()
        mock_database.__getitem__.return_value = mock_collection
        mock_client.__getitem__.return_value = mock_database

        dao = BookDao(mock_client)
        
        book_id = dao.add_book(title="New Book", authors=["Author"])
        assert book_id == "507f1f77bcf86cd799439011"

    def test_update_book_raises_duplicate_error(self):
        """Test that update_book raises DuplicateBookError for duplicates."""
        mock_client = MagicMock()
        mock_collection = MagicMock()
        mock_collection.find_one.return_value = {
            "_id": ObjectId("507f1f77bcf86cd799439013"),  # Different book
            "title": "Existing Book",
            "isbn": "9780123456789",
        }
        mock_collection.update_one.return_value = MagicMock(modified_count=1)
        mock_database = MagicMock()
        mock_database.__getitem__.return_value = mock_collection
        mock_client.__getitem__.return_value = mock_database

        dao = BookDao(mock_client)
        
        with pytest.raises(DuplicateBookError) as exc_info:
            dao.update_book(
                book_id="507f1f77bcf86cd799439011",
                title="My Book",
                authors=["Author"],
                isbn="9780123456789"  # This ISBN belongs to another book
            )
        assert "ISBN" in str(exc_info.value)

    def test_update_book_success_when_no_duplicate(self):
        """Test that update_book succeeds when no duplicate exists."""
        mock_client = MagicMock()
        mock_collection = MagicMock()
        mock_collection.find_one.return_value = None
        mock_collection.update_one.return_value = MagicMock(modified_count=1)
        mock_database = MagicMock()
        mock_database.__getitem__.return_value = mock_collection
        mock_client.__getitem__.return_value = mock_database

        dao = BookDao(mock_client)
        
        result = dao.update_book(
            book_id="507f1f77bcf86cd799439011",
            title="Updated Book",
            authors=["Author"]
        )
        assert result is True

    def test_case_insensitive_title_matching(self):
        """Test that title matching is case-insensitive."""
        mock_client = MagicMock()
        mock_collection = MagicMock()
        mock_collection.find_one.return_value = {
            "_id": ObjectId("507f1f77bcf86cd799439011"),
            "title": "test book",  # lowercase in DB
        }
        mock_database = MagicMock()
        mock_database.__getitem__.return_value = mock_collection
        mock_client.__getitem__.return_value = mock_database

        dao = BookDao(mock_client)
        
        # Should match even with different case
        is_duplicate, error_message = dao.check_duplicate(title="TEST BOOK")
        assert is_duplicate is True
        assert "title" in error_message.lower()
