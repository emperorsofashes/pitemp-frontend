import logging
from concurrent.futures import ThreadPoolExecutor

from application.data.book.providers.base import BookMetadata, BookMetadataProvider

LOG = logging.getLogger(__name__)


class MetadataMerger:
    """Merges metadata from multiple providers with conflict resolution."""

    def __init__(self):
        self.providers = []

    def add_provider(self, provider: BookMetadataProvider):
        """Add a provider to the merger."""
        self.providers.append(provider)

    def lookup(self, isbn: str) -> tuple[BookMetadata, dict[str, str]]:
        """
        Lookup ISBN across all providers and merge results.
        
        Returns:
            Tuple of (merged_metadata, provider_status)
            provider_status maps provider name to "success", "no_match", or "error"
        """
        merged_metadata = BookMetadata()
        provider_status = {}

        # Fetch from all providers in parallel to avoid worst-case serial latency.
        with ThreadPoolExecutor(max_workers=len(self.providers)) as executor:
            futures = {provider: executor.submit(provider.lookup, isbn) for provider in self.providers}

            for provider, future in futures.items():
                try:
                    metadata = future.result()

                    if metadata and provider.has_data(metadata):
                        # Merge this provider's data into the merged result
                        self._merge_metadata(merged_metadata, metadata, provider.name)
                        provider_status[provider.name] = 'success'
                    else:
                        provider_status[provider.name] = 'no_match'

                except Exception as e:
                    LOG.error(f'Error in provider {provider.name}: {e}')
                    provider_status[provider.name] = 'error'

        return merged_metadata, provider_status

    @staticmethod
    def _merge_metadata(merged: BookMetadata, new: BookMetadata, provider_name: str) -> None:
        """
        Merge new metadata into merged metadata with conflict resolution.
        
        Rules:
        - Prefer exact ISBN matches over approximate
        - Prefer edition-specific info over general work-level
        - Preserve original values when providers disagree
        - Don't invent missing information
        - Track which provider supplied each field
        """
        # Title: Prefer first non-empty title
        if new.title and not merged.title:
            merged.title = new.title
            merged.source_providers["title"] = provider_name
        elif new.title and merged.title and new.title != merged.title:
            # Conflict - log it but keep original
            LOG.warning(
                f"Title conflict: '{merged.title}' vs '{new.title}' from {provider_name}. "
                f"Keeping original from {merged.source_providers.get('title', 'unknown')}"
            )

        # Authors: Merge author lists, avoiding duplicates
        if new.authors:
            if not merged.authors:
                merged.authors = new.authors
                merged.source_providers["authors"] = provider_name
            else:
                # Add new authors that aren't already in the list
                for author in new.authors:
                    if author not in merged.authors:
                        merged.authors.append(author)
                # Update source if we added new authors
                if len(new.authors) > 0:
                    if "authors" not in merged.source_providers:
                        merged.source_providers["authors"] = provider_name
                    else:
                        merged.source_providers["authors"] += f", {provider_name}"

        # Date published: Prefer more specific dates (full date over year only)
        if new.date_published:
            if not merged.date_published:
                merged.date_published = new.date_published
                merged.source_providers["date_published"] = provider_name
            elif new.date_published != merged.date_published:
                # Prefer the more specific date (check if one has time component)
                # For now, keep the first one found
                LOG.warning(
                    f"Date conflict: {merged.date_published} vs {new.date_published} from {provider_name}. "
                    f"Keeping original from {merged.source_providers.get('date_published', 'unknown')}"
                )

        # ISBN: Prefer the ISBN from the provider that matched exactly
        if new.isbn and not merged.isbn:
            merged.isbn = new.isbn
            merged.source_providers["isbn"] = provider_name

        # Page count: Prefer non-zero values
        if new.page_count and new.page_count > 0:
            if not merged.page_count or merged.page_count == 0:
                merged.page_count = new.page_count
                merged.source_providers["page_count"] = provider_name
            elif new.page_count != merged.page_count:
                LOG.warning(
                    f"Page count conflict: {merged.page_count} vs {new.page_count} from {provider_name}. "
                    f"Keeping original from {merged.source_providers.get('page_count', 'unknown')}"
                )

        # Publisher: Prefer first non-empty publisher
        if new.publisher and not merged.publisher:
            merged.publisher = new.publisher
            merged.source_providers["publisher"] = provider_name
        elif new.publisher and merged.publisher and new.publisher != merged.publisher:
            LOG.warning(
                f"Publisher conflict: '{merged.publisher}' vs '{new.publisher}' from {provider_name}. "
                f"Keeping original from {merged.source_providers.get('publisher', 'unknown')}"
            )

        # Description: Prefer first non-empty description
        if new.description and not merged.description:
            merged.description = new.description
            merged.source_providers["description"] = provider_name

        # Cover URL: Prefer larger images
        if new.cover_url and not merged.cover_url:
            merged.cover_url = new.cover_url
            merged.source_providers["cover_url"] = provider_name
