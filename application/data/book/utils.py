"""Utility functions for book data processing."""

import re


def normalize_authors(authors: list[str] | str | None) -> list[str]:
    """
    Normalize and clean up author names.
    
    This function:
    - Handles both comma and semicolon separators
    - Converts "Last Name, First Name" format to "First Name Last Name" for individuals
    - Preserves company/organization names (e.g., "Penguin Books", "O'Reilly Media")
    - Trims whitespace and removes empty entries
    
    Args:
        authors: Either a list of author names or a comma/semicolon-separated string
        
    Returns:
        A list of normalized author names
    """
    if not authors:
        return []
    
    # Convert to list if it's a string
    if isinstance(authors, str):
        # If semicolons are present, use them as the primary separator between authors
        if ';' in authors:
            authors = re.split(r';', authors)
        else:
            # No semicolons - need to determine if commas are separators or Last, First format
            # First check if the string contains company keywords - if so, keep as-is
            company_keywords = {
                'inc', 'corp', 'ltd', 'llc', 'company', 'co', 'press', 'publishing',
                'books', 'media', 'publications', 'group', 'associates', 'partners',
                'institute', 'society', 'foundation', 'university', 'college',
                'library', 'archives', 'museum', 'gallery', 'studio', 'labs',
                'records', 'productions', 'entertainment', 'communications',
                'technologies', 'systems', 'solutions', 'services', 'international',
                'worldwide', 'global', 'enterprises', 'industries'
            }
            
            authors_lower = authors.lower()
            has_company_keyword = any(keyword in authors_lower for keyword in company_keywords)
            
            if has_company_keyword:
                # Contains company keywords - keep as single string (don't split by commas)
                authors = [authors]
            else:
                # No company keywords - check if it looks like Last, First pairs
                parts = [p.strip() for p in authors.split(',')]
                
                all_look_like_names = all(
                    len(p) > 0 and len(p) < 30 and not any(c.isdigit() for c in p)
                    for p in parts
                )
                
                if len(parts) == 2 and all_look_like_names:
                    # Check if this looks like "Last, First" or "First Last, First Last"
                    # If both parts have spaces, likely already "First Last" format (multiple authors)
                    # If only one has space or neither has space, likely "Last, First" format
                    first_has_space = ' ' in parts[0]
                    second_has_space = ' ' in parts[1]
                    
                    if first_has_space and second_has_space:
                        # Both have spaces - likely "First Last, First Last" (already formatted)
                        authors = parts
                    else:
                        # One or none have spaces - likely "Last, First" format
                        authors = [authors]
                elif len(parts) == 3 and all_look_like_names:
                    # Likely a person name with suffix (e.g., "Doe, John, Jr.") - keep as-is
                    authors = [authors]
                elif len(parts) > 2 and all_look_like_names and len(parts) % 2 == 0:
                    # Multiple authors in "Last, First" format - pair them up
                    authors = [f"{parts[i+1]} {parts[i]}" for i in range(0, len(parts), 2)]
                else:
                    # Treat commas as separators between authors
                    authors = parts
    
    # Company/organization keywords that indicate the name should not be reversed
    company_keywords = {
        'inc', 'corp', 'ltd', 'llc', 'company', 'co', 'press', 'publishing',
        'books', 'media', 'publications', 'group', 'associates', 'partners',
        'institute', 'society', 'foundation', 'university', 'college',
        'library', 'archives', 'museum', 'gallery', 'studio', 'labs',
        'records', 'productions', 'entertainment', 'communications',
        'technologies', 'systems', 'solutions', 'services', 'international',
        'worldwide', 'global', 'enterprises', 'industries'
    }
    
    normalized = []
    
    for author in authors:
        if not author:
            continue
            
        # Trim whitespace
        author = author.strip()
        if not author:
            continue
        
        # Check if this looks like a company name
        # Heuristic: if it contains company keywords (case-insensitive), don't reverse
        author_lower = author.lower()
        has_company_keyword = any(keyword in author_lower for keyword in company_keywords)
        
        # Also check for patterns that suggest it's not a person's name
        # - More than 2 commas (likely already formatted correctly or a company)
        # - Very long segments (likely a company description)
        parts = [p.strip() for p in author.split(',')]
        
        if has_company_keyword or len(parts) > 2:
            # Keep as-is, likely a company or already properly formatted
            normalized.append(author)
        elif len(parts) == 2:
            # Check if this looks like "Last, First" format
            # Heuristics:
            # - Both parts should be relatively short (person names)
            # - Neither part should contain company keywords
            # - First part (last name) shouldn't be too long
            last_name, first_name = parts
            
            # Additional checks to avoid mangling companies
            last_name_lower = last_name.lower()
            first_name_lower = first_name.lower()
            
            # If either part has company keywords, don't reverse
            if any(keyword in last_name_lower for keyword in company_keywords) or \
               any(keyword in first_name_lower for keyword in company_keywords):
                normalized.append(author)
            # If last name is very long (>30 chars), it's probably not a person
            elif len(last_name) > 30:
                normalized.append(author)
            # If first name is very long (>30 chars), it's probably not a person
            elif len(first_name) > 30:
                normalized.append(author)
            # If either part contains numbers, it's probably not a person
            elif any(c.isdigit() for c in last_name) or any(c.isdigit() for c in first_name):
                normalized.append(author)
            else:
                # Looks like "Last, First" - convert to "First Last"
                normalized.append(f"{first_name} {last_name}")
        else:
            # No comma or only one part, keep as-is
            normalized.append(author)
    
    return normalized


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
