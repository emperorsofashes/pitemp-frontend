"""Utility functions for book data processing."""


def capitalize_title(title: str) -> str:
    """
    Capitalize a book title according to title case rules.
    
    Rules:
    - First and last words are always capitalized
    - Words after colons are always capitalized
    - Minor words (articles, conjunctions, prepositions, forms of "to be") are lowercase unless they're the first/last word
    - Words already in proper case (like acronyms or names) are preserved
    - Leading/trailing spaces are trimmed
    - Multiple spaces are collapsed to single spaces
    
    Args:
        title: The title to capitalize
        
    Returns:
        The capitalized title
    """
    if not title:
        return title
    
    # Trim leading/trailing spaces and collapse multiple spaces
    import re
    title = re.sub(r'\s+', ' ', title.strip())
    
    # Minor words that should be lowercase (unless first/last word or after colon)
    minor_words = {
        'a', 'an', 'the', 'and', 'but', 'or', 'for', 'nor', 'on', 'at', 
        'to', 'by', 'in', 'of', 'with', 'from', 'as', 'into', 'is', 'are',
        'was', 'were', 'be', 'been', 'being'
    }
    
    words = title.split()
    if not words:
        return title
    
    result = []
    
    for i, word in enumerate(words):
        # Check if this word follows a colon
        follows_colon = i > 0 and words[i-1].endswith(':')
        
        # Check if this is the first or last word
        is_first = i == 0
        is_last = i == len(words) - 1
        
        # Check if word is already properly capitalized (mixed case, not all caps)
        is_proper_case = len(word) > 1 and any(c.isupper() for c in word[1:]) and not word.isupper()
        
        if is_proper_case:
            # Preserve words that are already in proper case (like names, iPhone, etc.)
            result.append(word)
        elif follows_colon or is_first or is_last:
            # Always capitalize these
            result.append(word.capitalize())
        elif word.lower() in minor_words:
            # Keep minor words lowercase
            result.append(word.lower())
        else:
            # Capitalize other words
            result.append(word.capitalize())
    
    return ' '.join(result)
