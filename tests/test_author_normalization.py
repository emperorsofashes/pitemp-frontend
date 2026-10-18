import pytest
from application.data.book.utils import normalize_authors


class TestAuthorNormalization:
    """Test author name normalization logic."""

    def test_empty_input(self):
        """Test that empty input returns empty list."""
        assert normalize_authors(None) == []
        assert normalize_authors([]) == []
        assert normalize_authors("") == []

    def test_comma_separated_authors(self):
        """Test handling of comma-separated authors (already in First Last format)."""
        result = normalize_authors("John Doe, Jane Smith")
        assert result == ["John Doe", "Jane Smith"]

    def test_semicolon_separated_authors(self):
        """Test handling of semicolon-separated authors."""
        result = normalize_authors("John Doe; Jane Smith")
        assert result == ["John Doe", "Jane Smith"]

    def test_list_input(self):
        """Test handling of list input."""
        result = normalize_authors(["John Doe", "Jane Smith"])
        assert result == ["John Doe", "Jane Smith"]

    def test_last_first_to_first_last(self):
        """Test conversion from 'Last, First' to 'First Last'."""
        result = normalize_authors("Doe, John")
        assert result == ["John Doe"]

    def test_multiple_last_first_format(self):
        """Test multiple authors in 'Last, First' format separated by semicolons."""
        result = normalize_authors("Doe, John; Smith, Jane")
        assert result == ["John Doe", "Jane Smith"]

    def test_company_names_preserved(self):
        """Test that company names are not reversed."""
        result = normalize_authors("Penguin Books")
        assert result == ["Penguin Books"]
        
        result = normalize_authors("O'Reilly Media")
        assert result == ["O'Reilly Media"]
        
        result = normalize_authors("Penguin Publishing")
        assert result == ["Penguin Publishing"]

    def test_company_with_comma_not_reversed(self):
        """Test that company names with commas are not reversed."""
        # Companies with commas should use semicolons as separators to avoid ambiguity
        result = normalize_authors("Penguin Books, Inc.")
        assert result == ["Penguin Books, Inc."]

    def test_university_names_preserved(self):
        """Test that university names are preserved."""
        result = normalize_authors("Oxford University Press")
        assert result == ["Oxford University Press"]

    def test_long_names_preserved(self):
        """Test that very long names (likely companies) are not reversed."""
        result = normalize_authors("This is a very long company name that exceeds thirty characters, Inc.")
        assert result == ["This is a very long company name that exceeds thirty characters, Inc."]

    def test_names_with_numbers_preserved(self):
        """Test that names with numbers are not reversed."""
        result = normalize_authors("Company 123, LLC")
        assert result == ["Company 123, LLC"]

    def test_whitespace_trimming(self):
        """Test that whitespace is trimmed."""
        result = normalize_authors("  John Doe  ;  Jane Smith  ")
        assert result == ["John Doe", "Jane Smith"]

    def test_empty_entries_removed(self):
        """Test that empty entries are removed."""
        result = normalize_authors("John Doe; ; Jane Smith; ")
        assert result == ["John Doe", "Jane Smith"]

    def test_already_properly_formatted(self):
        """Test that already properly formatted names are preserved."""
        result = normalize_authors("John Doe")
        assert result == ["John Doe"]

    def test_mixed_person_and_company(self):
        """Test mixed person and company names."""
        result = normalize_authors("Doe, John; Penguin Books; Smith, Jane")
        assert result == ["John Doe", "Penguin Books", "Jane Smith"]

    def test_single_name_no_comma(self):
        """Test single name without comma."""
        result = normalize_authors("John Doe")
        assert result == ["John Doe"]

    def test_multiple_commas_preserved(self):
        """Test that names with multiple commas are preserved."""
        result = normalize_authors("Doe, John, Jr.")
        assert result == ["Doe, John, Jr."]

    def test_case_insensitive_company_detection(self):
        """Test that company keyword detection is case-insensitive."""
        result = normalize_authors("PENGUIN BOOKS")
        assert result == ["PENGUIN BOOKS"]
        
        result = normalize_authors("O'Reilly Media Inc")
        assert result == ["O'Reilly Media Inc"]

    def test_various_company_keywords(self):
        """Test various company keywords are detected."""
        test_cases = [
            "Test Company Inc",
            "Test Corp LLC",
            "Test Ltd",
            "Test Publishing Group",
            "Test Press",
            "Test Media",
            "Test Institute",
            "Test Foundation",
            "Test University",
            "Test Technologies",
            "Test Systems",
            "Test Solutions",
            "Test Services",
            "Test Associates",
            "Test Partners",
            "Test Enterprises",
            "Test Industries",
        ]
        
        for company in test_cases:
            result = normalize_authors(company)
            assert result == [company], f"Failed for: {company}"

    def test_real_world_examples(self):
        """Test with real-world author name examples."""
        # Person names in Last, First format
        result = normalize_authors("King, Stephen")
        assert result == ["Stephen King"]
        
        result = normalize_authors("Tolkien, J.R.R.")
        assert result == ["J.R.R. Tolkien"]
        
        # Company names
        result = normalize_authors("National Geographic Society")
        assert result == ["National Geographic Society"]
        
        # Mixed
        result = normalize_authors("King, Stephen; Penguin Random House")
        assert result == ["Stephen King", "Penguin Random House"]
