import logging
from concurrent.futures import ThreadPoolExecutor

from application.data.book.providers.base import BookMetadataProvider, SearchResult

LOG = logging.getLogger(__name__)


class BookSearchMerger:
    """Aggregates and deduplicates search results from multiple providers."""

    def __init__(self):
        self.providers = []

    def add_provider(self, provider: BookMetadataProvider):
        """Add a provider to the merger."""
        self.providers.append(provider)

    def search(self, query: str, max_results_per_provider: int = 10) -> tuple[list[SearchResult], dict[str, str]]:
        """
        Search across all providers and aggregate results.
        
        Args:
            query: Search query string
            max_results_per_provider: Maximum results to fetch from each provider
            
        Returns:
            Tuple of (deduplicated_results, provider_status)
            provider_status maps provider name to "success", "no_match", or "error"
         """
        all_results = []
        provider_status = {}

        # Fetch from all providers in parallel to avoid worst-case serial latency.
        with ThreadPoolExecutor(max_workers=len(self.providers)) as executor:
            futures = {provider: executor.submit(provider.search, query, max_results_per_provider) for provider in
                       self.providers}

            for provider, future in futures.items():
                try:
                    results = future.result()

                    if results:
                        all_results.extend(results)
                        provider_status[provider.name] = 'success'
                    else:
                        provider_status[provider.name] = 'no_match'

                except Exception as e:
                    LOG.error(f'Error in provider {provider.name}: {e}')
                    provider_status[provider.name] = 'error'

        # Deduplicate results
        deduplicated = self._deduplicate_results(all_results)

        return deduplicated, provider_status

    def _deduplicate_results(self, results: list[SearchResult]) -> list[SearchResult]:
        """
        Deduplicate search results using ISBN and title/author combinations.
        
        Strategy:
        1. Exact ISBN match (ISBN-13 or ISBN-10) is considered the same book
        2. Same title + same author(s) is considered potentially the same book
        3. Keep the result with more complete metadata when duplicates are found
        4. Prefer results from providers that returned more metadata
        """
        if not results:
            return []

        # Group by ISBN first
        isbn_groups: dict[str, list[SearchResult]] = {}
        no_isbn_results = []

        for result in results:
            isbn = result.get_isbn()
            if isbn:
                if isbn not in isbn_groups:
                    isbn_groups[isbn] = []
                isbn_groups[isbn].append(result)
            else:
                no_isbn_results.append(result)

        # For each ISBN group, keep the best result
        deduplicated = []

        for isbn, group in isbn_groups.items():
            best = self._select_best_result(group)
            deduplicated.append(best)

        # Now handle results without ISBN - group by title + author
        title_author_groups: dict[str, list[SearchResult]] = {}

        for result in no_isbn_results:
            # Create a key from title and sorted authors
            key = self._create_title_author_key(result)
            if key not in title_author_groups:
                title_author_groups[key] = []
            title_author_groups[key].append(result)

        # For each title/author group, keep the best result
        for group in title_author_groups.values():
            # Only deduplicate if we have multiple results for the same title/author
            if len(group) > 1:
                best = self._select_best_result(group)
                deduplicated.append(best)
            else:
                deduplicated.extend(group)

        return deduplicated

    def _create_title_author_key(self, result: SearchResult) -> str:
        """Create a key for grouping by title and author."""
        title_normalized = result.title.lower().strip() if result.title else ""
        authors_normalized = ",".join(sorted([a.lower().strip() for a in result.authors])) if result.authors else ""
        return f"{title_normalized}|{authors_normalized}"

    def _select_best_result(self, results: list[SearchResult]) -> SearchResult:
        """
        Select the best result from a group of duplicates.
        
        Criteria:
        1. More complete metadata (more non-None fields)
        2. Prefer results with ISBN
        3. Prefer results with description
        4. Prefer results with cover image
        """
        if len(results) == 1:
            return results[0]

        def score_result(result: SearchResult) -> int:
            score = 0
            if result.isbn_13:
                score += 10
            if result.isbn_10:
                score += 5
            if result.description:
                score += 3
            if result.cover_url:
                score += 2
            if result.publisher:
                score += 1
            if result.publication_date:
                score += 1
            if result.page_count:
                score += 1
            if result.edition:
                score += 1
            return score

        # Sort by score and return the highest
        results.sort(key=score_result, reverse=True)
        return results[0]
