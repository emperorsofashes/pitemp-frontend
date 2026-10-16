"""Unit tests for title capitalization function."""

import pytest

from application.data.book.utils import capitalize_title


class TestCapitalizeTitle:
    """Test title capitalization function."""

    # Test cases: (input, expected_output)
    # Add your own test cases to this list - it's easy to extend!
    TEST_CASES = [
        ("My big fat Greek wedding", "My Big Fat Greek Wedding"),
        ("Mount everest: the beast", "Mount Everest: The Beast"),
        ("This is the End", "This is the End"),
        ("Of mice and of men", "Of Mice and of Men"),

        # Basic capitalization
        ("the great gatsby", "The Great Gatsby"),
        ("to kill a mockingbird", "To Kill a Mockingbird"),

        # Minor words in middle
        ("war and peace", "War and Peace"),
        ("lord of the flies", "Lord of the Flies"),
        ("the catcher in the rye", "The Catcher in the Rye"),

        # Colons
        ("harry potter: the philosopher's stone", "Harry Potter: The Philosopher's Stone"),
        ("star wars: a new hope", "Star Wars: A New Hope"),

        # Already capitalized words (proper nouns)
        ("The Lord of the Rings", "The Lord of the Rings"),
        ("The End of the World", "The End of the World"),

        # Single word
        ("dune", "Dune"),
        ("IT", "It"),  # Single word gets capitalized

        # Empty and edge cases
        ("", ""),
        ("a", "A"),
        ("the", "The"),

        # Multiple spaces (collapsed to single space)
        ("hello  world", "Hello World"),
        ("  hello  world  ", "Hello World"),  # Leading/trailing trimmed

        # Minor words at end
        ("the man in the iron mask", "The Man in the Iron Mask"),
        ("gone with the wind", "Gone with the Wind"),

        # Complex cases
        ("the hitchhiker's guide to the galaxy", "The Hitchhiker's Guide to the Galaxy"),
        ("a tale of two cities", "A Tale of Two Cities"),
    ]

    @pytest.mark.parametrize("input_title,expected", TEST_CASES)
    def test_capitalize_title_cases(self, input_title, expected):
        """Test various title capitalization cases."""
        result = capitalize_title(input_title)
        assert result == expected, f"Failed for '{input_title}': got '{result}', expected '{expected}'"

    def test_none_input(self):
        """Test with None input."""
        result = capitalize_title(None)
        assert result is None

    def test_already_capitalized(self):
        """Test that already properly capitalized titles are unchanged."""
        title = "The Great Gatsby"
        result = capitalize_title(title)
        assert result == title

    def test_all_uppercase(self):
        """Test with all uppercase input."""
        result = capitalize_title("THE GREAT GATSBY")
        assert result == "The Great Gatsby"  # All caps get title-cased

    def test_all_lowercase(self):
        """Test with all lowercase input."""
        result = capitalize_title("the great gatsby")
        assert result == "The Great Gatsby"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
