import pytest
from datetime import datetime
from unittest.mock import Mock, patch

from application.data.book.providers.base import BookMetadata, BookMetadataProvider, SearchResult
from application.data.book.providers.googlebooks import GoogleBooksProvider
from application.data.book.providers.loc import LibraryOfCongressProvider
from application.data.book.providers.merger import MetadataMerger
from application.data.book.providers.ndl import NDLSearchProvider
from application.data.book.providers.openbd import OpenBDProvider
from application.data.book.providers.openlibrary import OpenLibraryProvider
from application.data.book.providers.search_merger import BookSearchMerger


class TestOpenLibraryProvider:
    """Test Open Library provider."""

    def test_lookup_complete_record(self):
        """Test Open Library returns a complete record."""
        provider = OpenLibraryProvider()
        
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "ISBN:9780140328721": {
                "title": "Charlotte's Web",
                "authors": [{"name": "E.B. White"}],
                "publish_date": "1952",
                "number_of_pages": 184,
                "publishers": [{"name": "Harper & Brothers"}],
                "cover": {"medium": "http://example.com/cover.jpg"}
            }
        }
        
        with patch('requests.get', return_value=mock_response):
            metadata = provider.lookup("9780140328721")
            
            assert metadata is not None
            assert metadata.title == "Charlotte's Web"
            assert metadata.authors == ["E.B. White"]
            assert metadata.page_count == 184
            assert metadata.publisher == "Harper & Brothers"
            assert metadata.cover_url == "http://example.com/cover.jpg"

    def test_lookup_no_match(self):
        """Test Open Library returns no match."""
        provider = OpenLibraryProvider()
        
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {}
        
        with patch('requests.get', return_value=mock_response):
            metadata = provider.lookup("9999999999")
            
            assert metadata is None

    def test_lookup_timeout(self):
        """Test Open Library request times out."""
        provider = OpenLibraryProvider()
        
        with patch('requests.get', side_effect=Exception("Timeout")):
            metadata = provider.lookup("9780140328721")
            
            assert metadata is None

    def test_search_returns_results(self):
        """Test Open Library search returns results."""
        provider = OpenLibraryProvider()
        
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "docs": [
                {
                    "title": "Test Book",
                    "author_name": ["Test Author"],
                    "publisher": ["Test Publisher"],
                    "first_publish_year": 2020,
                    "number_of_pages": 300,
                    "isbn": ["1234567890"],
                    "cover_i": 12345,
                    "key": "/works/OL123W"
                }
            ]
        }
        
        with patch('requests.get', return_value=mock_response):
            results = provider.search("test book")
            
            assert len(results) == 1
            assert results[0].title == "Test Book"
            assert results[0].authors == ["Test Author"]
            assert results[0].publisher == "Test Publisher"
            assert results[0].publication_year == 2020
            assert results[0].page_count == 300
            assert results[0].isbn_10 == "1234567890"
            assert results[0].cover_url == "https://covers.openlibrary.org/b/id/12345-L.jpg"
            assert results[0].provider == "Open Library"

    def test_search_no_results(self):
        """Test Open Library search returns no results."""
        provider = OpenLibraryProvider()
        
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"docs": []}
        
        with patch('requests.get', return_value=mock_response):
            results = provider.search("nonexistent book")
            
            assert len(results) == 0


class TestGoogleBooksProvider:
    """Test Google Books provider."""

    def test_lookup_complete_record(self):
        """Test Google Books returns a complete record."""
        provider = GoogleBooksProvider()
        
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "items": [{
                "volumeInfo": {
                    "title": "The Great Gatsby",
                    "authors": ["F. Scott Fitzgerald"],
                    "publishedDate": "1925",
                    "pageCount": 180,
                    "publisher": "Scribner",
                    "description": "A classic novel",
                    "imageLinks": {"thumbnail": "http://example.com/cover.jpg"},
                    "industryIdentifiers": [{"type": "ISBN_13", "identifier": "9780743273565"}]
                }
            }]
        }
        
        with patch('requests.get', return_value=mock_response):
            metadata = provider.lookup("9780743273565")
            
            assert metadata is not None
            assert metadata.title == "The Great Gatsby"
            assert metadata.authors == ["F. Scott Fitzgerald"]
            assert metadata.page_count == 180
            assert metadata.publisher == "Scribner"
            assert metadata.description == "A classic novel"

    def test_lookup_no_match(self):
        """Test Google Books returns no match."""
        provider = GoogleBooksProvider()
        
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {}
        
        with patch('requests.get', return_value=mock_response):
            metadata = provider.lookup("9999999999")
            
            assert metadata is None

    def test_search_returns_results(self):
        """Test Google Books search returns results."""
        provider = GoogleBooksProvider()
        
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "items": [{
                "volumeInfo": {
                    "title": "Search Result Book",
                    "authors": ["Author One"],
                    "publishedDate": "2020",
                    "pageCount": 250,
                    "publisher": "Publisher Inc",
                    "description": "A description",
                    "imageLinks": {"thumbnail": "http://example.com/cover.jpg"},
                    "industryIdentifiers": [{"type": "ISBN_13", "identifier": "9781234567890"}],
                    "infoLink": "https://books.google.com/books?id=test"
                },
                "id": "test_id"
            }]
        }
        
        with patch('requests.get', return_value=mock_response):
            results = provider.search("search query")
            
            assert len(results) == 1
            assert results[0].title == "Search Result Book"
            assert results[0].authors == ["Author One"]
            assert results[0].publication_year == 2020
            assert results[0].page_count == 250
            assert results[0].isbn_13 == "9781234567890"
            assert results[0].provider == "Google Books"


class TestLibraryOfCongressProvider:
    """Test Library of Congress provider."""

    def test_lookup_complete_record(self):
        """Test Library of Congress returns a complete record."""
        provider = LibraryOfCongressProvider()
        
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.text = """<?xml version="1.0"?>
        <srw:searchRetrieveResponse xmlns:srw="http://www.loc.gov/zing/srw/">
            <srw:records>
                <srw:record>
                    <srw:recordData>
                        <oai_dc:dc xmlns:oai_dc="http://www.openarchives.org/OAI/2.0/oai_dc/">
                            <dc:dc xmlns:dc="http://purl.org/dc/elements/1.1/">
                                <dc:title>Test Book</dc:title>
                                <dc:creator>Test Author</dc:creator>
                                <dc:publisher>Test Publisher</dc:publisher>
                                <dc:date>2020</dc:date>
                                <dc:identifier>ISBN 1234567890</dc:identifier>
                            </dc:dc>
                        </oai_dc:dc>
                    </srw:recordData>
                </srw:record>
            </srw:records>
        </srw:searchRetrieveResponse>"""
        
        with patch('requests.get', return_value=mock_response):
            metadata = provider.lookup("1234567890")
            
            assert metadata is not None
            assert metadata.title == "Test Book"
            assert metadata.authors == ["Test Author"]
            assert metadata.publisher == "Test Publisher"

    def test_lookup_no_match(self):
        """Test Library of Congress returns no match."""
        provider = LibraryOfCongressProvider()
        
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.text = """<?xml version="1.0"?>
        <srw:searchRetrieveResponse xmlns:srw="http://www.loc.gov/zing/srw/">
            <srw:records>
            </srw:records>
        </srw:searchRetrieveResponse>"""
        
        with patch('requests.get', return_value=mock_response):
            metadata = provider.lookup("9999999999")
            
            assert metadata is None


class TestOpenBDProvider:
    """Test openBD provider."""

    def test_lookup_complete_record(self):
        """Test openBD returns a complete record."""
        provider = OpenBDProvider()
        
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = [{
            "summary": {
                "title": "Test Book",
                "author": "Test Author",
                "publisher": "Test Publisher",
                "pubdate": "20200101",
                "extent": "300p",
                "isbn": "9784000000000",
                "cover": "http://example.com/cover.jpg"
            }
        }]
        
        with patch('requests.get', return_value=mock_response):
            metadata = provider.lookup("9784000000000")
            
            assert metadata is not None
            assert metadata.title == "Test Book"
            assert metadata.authors == ["Test Author"]
            assert metadata.publisher == "Test Publisher"
            assert metadata.page_count == 300
            assert metadata.cover_url == "https://example.com/cover.jpg"

    def test_lookup_no_match(self):
        """Test openBD returns no match."""
        provider = OpenBDProvider()
        
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = []
        
        with patch('requests.get', return_value=mock_response):
            metadata = provider.lookup("9999999999")
            
            assert metadata is None

    def test_lookup_timeout(self):
        """Test openBD request times out."""
        provider = OpenBDProvider()
        
        with patch('requests.get', side_effect=Exception("Timeout")):
            metadata = provider.lookup("9784000000000")
            
            assert metadata is None


class TestNDLSearchProvider:
    """Test NDL Search provider."""

    def test_lookup_complete_record(self):
        """Test NDL Search returns a complete record."""
        provider = NDLSearchProvider()
        
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.text = """<?xml version="1.0"?>
        <srw:searchRetrieveResponse xmlns:srw="http://www.loc.gov/zing/srw/">
            <srw:records>
                <srw:record>
                    <srw:recordData>
                        <rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">
                            <dc:dc xmlns:dc="http://purl.org/dc/elements/1.1/">
                                <dc:title>Test Book</dc:title>
                                <dc:creator>Test Author</dc:creator>
                                <dc:publisher>Test Publisher</dc:publisher>
                                <dcterms:issued xmlns:dcterms="http://purl.org/dc/terms/">2020</dcterms:issued>
                                <dc:identifier>ISBN 1234567890</dc:identifier>
                                <dcndl:extent xmlns:dcndl="http://ndl.go.jp/dcndl/terms/">300p</dcndl:extent>
                            </dc:dc>
                        </rdf:RDF>
                    </srw:recordData>
                </srw:record>
            </srw:records>
        </srw:searchRetrieveResponse>"""
        
        with patch('requests.get', return_value=mock_response):
            metadata = provider.lookup("1234567890")
            
            assert metadata is not None
            assert metadata.title == "Test Book"
            assert metadata.authors == ["Test Author"]
            assert metadata.publisher == "Test Publisher"
            assert metadata.page_count == 300

    def test_lookup_no_match(self):
        """Test NDL Search returns no match."""
        provider = NDLSearchProvider()
        
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.text = """<?xml version="1.0"?>
        <srw:searchRetrieveResponse xmlns:srw="http://www.loc.gov/zing/srw/">
            <srw:records>
            </srw:records>
        </srw:searchRetrieveResponse>"""
        
        with patch('requests.get', return_value=mock_response):
            metadata = provider.lookup("9999999999")
            
            assert metadata is None

    def test_lookup_timeout(self):
        """Test NDL Search request times out."""
        provider = NDLSearchProvider()
        
        with patch('requests.get', side_effect=Exception("Timeout")):
            metadata = provider.lookup("1234567890")
            
            assert metadata is None


class TestMetadataMerger:
    """Test metadata merger with multiple providers."""

    def test_open_library_complete_record(self):
        """Test when Open Library returns a complete record."""
        merger = MetadataMerger()
        
        mock_ol = Mock(spec=OpenLibraryProvider)
        mock_ol.name = "Open Library"
        mock_ol.lookup.return_value = BookMetadata(
            title="Test Book",
            authors=["Author One"],
            date_published=datetime(2020, 1, 1),
            page_count=200,
            isbn="1234567890"
        )
        mock_ol._has_data.return_value = True
        
        mock_gb = Mock(spec=GoogleBooksProvider)
        mock_gb.name = "Google Books"
        mock_gb.lookup.return_value = None
        
        merger.add_provider(mock_ol)
        merger.add_provider(mock_gb)
        
        metadata, status = merger.lookup("1234567890")
        
        assert metadata.title == "Test Book"
        assert metadata.authors == ["Author One"]
        assert status["Open Library"] == "success"
        assert status["Google Books"] == "no_match"

    def test_open_library_no_match_google_books_finds(self):
        """Test when Open Library returns no match but Google Books finds the ISBN."""
        merger = MetadataMerger()
        
        mock_ol = Mock(spec=OpenLibraryProvider)
        mock_ol.name = "Open Library"
        mock_ol.lookup.return_value = None
        
        mock_gb = Mock(spec=GoogleBooksProvider)
        mock_gb.name = "Google Books"
        mock_gb.lookup.return_value = BookMetadata(
            title="Found Book",
            authors=["Author Two"],
            page_count=150,
            isbn="9876543210"
        )
        mock_gb._has_data.return_value = True
        
        merger.add_provider(mock_ol)
        merger.add_provider(mock_gb)
        
        metadata, status = merger.lookup("9876543210")
        
        assert metadata.title == "Found Book"
        assert status["Open Library"] == "no_match"
        assert status["Google Books"] == "success"

    def test_open_library_incomplete_google_books_fills_missing(self):
        """Test when Open Library returns incomplete metadata and Google Books fills missing fields."""
        merger = MetadataMerger()
        
        mock_ol = Mock(spec=OpenLibraryProvider)
        mock_ol.name = "Open Library"
        mock_ol.lookup.return_value = BookMetadata(
            title="Partial Book",
            authors=["Author One"],
            page_count=None  # Missing
        )
        mock_ol._has_data.return_value = True
        
        mock_gb = Mock(spec=GoogleBooksProvider)
        mock_gb.name = "Google Books"
        mock_gb.lookup.return_value = BookMetadata(
            title="Partial Book",  # Same title
            authors=["Author One"],  # Same authors
            page_count=300,  # Fills missing field
            publisher="Publisher Inc."  # Additional field
        )
        mock_gb._has_data.return_value = True
        
        merger.add_provider(mock_ol)
        merger.add_provider(mock_gb)
        
        metadata, status = merger.lookup("1234567890")
        
        assert metadata.title == "Partial Book"
        assert metadata.page_count == 300  # Filled by Google Books
        assert metadata.publisher == "Publisher Inc."  # Added by Google Books
        assert status["Open Library"] == "success"
        assert status["Google Books"] == "success"

    def test_loc_provides_missing_metadata(self):
        """Test when Library of Congress provides metadata missing from other providers."""
        merger = MetadataMerger()
        
        mock_ol = Mock(spec=OpenLibraryProvider)
        mock_ol.name = "Open Library"
        mock_ol.lookup.return_value = BookMetadata(
            title="Book Title",
            authors=["Author"],
        )
        mock_ol._has_data.return_value = True
        
        mock_gb = Mock(spec=GoogleBooksProvider)
        mock_gb.name = "Google Books"
        mock_gb.lookup.return_value = BookMetadata(
            title="Book Title",
            authors=["Author"],
        )
        mock_gb._has_data.return_value = True
        
        mock_loc = Mock(spec=LibraryOfCongressProvider)
        mock_loc.name = "Library of Congress"
        mock_loc.lookup.return_value = BookMetadata(
            publisher="LOC Publisher",
            date_published=datetime(1990, 1, 1)
        )
        mock_loc._has_data.return_value = True
        
        merger.add_provider(mock_ol)
        merger.add_provider(mock_gb)
        merger.add_provider(mock_loc)
        
        metadata, status = merger.lookup("1234567890")
        
        assert metadata.publisher == "LOC Publisher"
        assert metadata.date_published == datetime(1990, 1, 1)
        assert status["Library of Congress"] == "success"

    def test_multiple_providers_complementary_info(self):
        """Test when multiple providers return complementary information."""
        merger = MetadataMerger()
        
        mock_ol = Mock(spec=OpenLibraryProvider)
        mock_ol.name = "Open Library"
        mock_ol.lookup.return_value = BookMetadata(
            title="Complete Book",
            authors=["Author One"],
            page_count=200
        )
        mock_ol._has_data.return_value = True
        
        mock_gb = Mock(spec=GoogleBooksProvider)
        mock_gb.name = "Google Books"
        mock_gb.lookup.return_value = BookMetadata(
            title="Complete Book",
            authors=["Author One"],
            publisher="Publisher",
            description="A description"
        )
        mock_gb._has_data.return_value = True
        
        merger.add_provider(mock_ol)
        merger.add_provider(mock_gb)
        
        metadata, status = merger.lookup("1234567890")
        
        assert metadata.title == "Complete Book"
        assert metadata.page_count == 200  # From Open Library
        assert metadata.publisher == "Publisher"  # From Google Books
        assert metadata.description == "A description"  # From Google Books

    def test_providers_disagree_field(self):
        """Test when providers disagree about a field."""
        merger = MetadataMerger()
        
        mock_ol = Mock(spec=OpenLibraryProvider)
        mock_ol.name = "Open Library"
        mock_ol.lookup.return_value = BookMetadata(
            title="Title A",
            page_count=200
        )
        mock_ol._has_data.return_value = True
        
        mock_gb = Mock(spec=GoogleBooksProvider)
        mock_gb.name = "Google Books"
        mock_gb.lookup.return_value = BookMetadata(
            title="Title B",  # Different title
            page_count=250  # Different page count
        )
        mock_gb._has_data.return_value = True
        
        merger.add_provider(mock_ol)
        merger.add_provider(mock_gb)
        
        metadata, status = merger.lookup("1234567890")
        
        # Should keep first provider's value
        assert metadata.title == "Title A"
        assert metadata.page_count == 200

    def test_one_provider_times_out_others_succeed(self):
        """Test when one provider times out while others succeed."""
        merger = MetadataMerger()
        
        mock_ol = Mock(spec=OpenLibraryProvider)
        mock_ol.name = "Open Library"
        mock_ol.lookup.side_effect = Exception("Timeout")
        
        mock_gb = Mock(spec=GoogleBooksProvider)
        mock_gb.name = "Google Books"
        mock_gb.lookup.return_value = BookMetadata(
            title="Survivor Book",
            authors=["Author"]
        )
        mock_gb._has_data.return_value = True
        
        merger.add_provider(mock_ol)
        merger.add_provider(mock_gb)
        
        metadata, status = merger.lookup("1234567890")
        
        assert metadata.title == "Survivor Book"
        assert status["Open Library"] == "error"
        assert status["Google Books"] == "success"

    def test_all_providers_fail(self):
        """Test when all providers fail or return no match."""
        merger = MetadataMerger()
        
        mock_ol = Mock(spec=OpenLibraryProvider)
        mock_ol.name = "Open Library"
        mock_ol.lookup.return_value = None
        
        mock_gb = Mock(spec=GoogleBooksProvider)
        mock_gb.name = "Google Books"
        mock_gb.lookup.return_value = None
        
        mock_loc = Mock(spec=LibraryOfCongressProvider)
        mock_loc.name = "Library of Congress"
        mock_loc.lookup.return_value = None
        
        merger.add_provider(mock_ol)
        merger.add_provider(mock_gb)
        merger.add_provider(mock_loc)
        
        metadata, status = merger.lookup("9999999999")
        
        assert not metadata.title
        assert not metadata.authors
        assert status["Open Library"] == "no_match"
        assert status["Google Books"] == "no_match"
        assert status["Library of Congress"] == "no_match"

    def test_invalid_isbn(self):
        """Test with invalid ISBN."""
        merger = MetadataMerger()
        
        mock_ol = Mock(spec=OpenLibraryProvider)
        mock_ol.name = "Open Library"
        mock_ol.lookup.return_value = None
        
        merger.add_provider(mock_ol)
        
        metadata, status = merger.lookup("")
        
        assert not metadata.title
        assert status["Open Library"] == "no_match"


if __name__ == "__main__":
    pytest.main([__file__])
