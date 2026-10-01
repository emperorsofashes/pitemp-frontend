import logging
import re
from datetime import datetime
from urllib.parse import quote
from xml.etree import ElementTree as ET

import requests

from application.data.book.providers.base import BookMetadata, BookMetadataProvider, SearchResult

LOG = logging.getLogger(__name__)


class LibraryOfCongressProvider(BookMetadataProvider):
    """Provider for Library of Congress SRU API."""

    def __init__(self, timeout: int = 10):
        super().__init__(timeout)
        self.name = "Library of Congress"
        self.base_url = "https://lx2.loc.gov:210/LCDB"

    def lookup(self, isbn: str) -> BookMetadata | None:
        """Look up book metadata by ISBN using Library of Congress SRU API."""
        isbn_clean = self.normalize_isbn(isbn)

        try:
            # Use SRU API with Dublin Core schema for easier parsing
            url = (
                f"{self.base_url}?"
                f"version=1.1&"
                f"operation=searchRetrieve&"
                f"query=bath.isbn={isbn_clean}&"
                f"maximumRecords=1&"
                f"recordSchema=dc"
            )
            resp = requests.get(url, timeout=self.timeout, headers={"User-Agent": "BookCatalog/1.0"})

            if resp.status_code != 200:
                LOG.warning(f"Library of Congress API returned status {resp.status_code}")
                return None

            # Parse XML response
            root = ET.fromstring(resp.text)

            # Define namespace
            ns = {
                "srw": "https://www.loc.gov/zing/srw/",
                "dc": "https://purl.org/dc/elements/1.1/",
                "oai_dc": "https://www.openarchives.org/OAI/2.0/oai_dc/",
            }

            # Check if records were found
            records = root.findall(".//srw:recordData/oai_dc:dc/dc:dc", ns)
            if not records:
                # Try alternative namespace path
                records = root.findall(".//srw:recordData/dc:dc", ns)
                if not records:
                    return None

            record = records[0]
            metadata = BookMetadata()

            # Extract title
            title_elements = record.findall("dc:title", ns)
            if title_elements:
                metadata.title = title_elements[0].text

            # Extract authors (creators)
            creator_elements = record.findall("dc:creator", ns)
            if creator_elements:
                metadata.authors = [elem.text for elem in creator_elements if elem.text]

            # Extract publisher
            publisher_elements = record.findall("dc:publisher", ns)
            if publisher_elements:
                metadata.publisher = publisher_elements[0].text

            # Extract date
            date_elements = record.findall("dc:date", ns)
            if date_elements and date_elements[0].text:
                date_str = date_elements[0].text
                # Try to parse various date formats
                for fmt in ["%Y-%m-%d", "%Y", "%Y-%m"]:
                    try:
                        if fmt == "%Y":
                            metadata.date_published = datetime.strptime(date_str[:4], fmt)
                        else:
                            metadata.date_published = datetime.strptime(date_str, fmt)
                        break
                    except ValueError:
                        continue

            # Extract ISBN from identifiers
            identifier_elements = record.findall("dc:identifier", ns)
            for elem in identifier_elements:
                if elem.text and "isbn" in elem.text.lower():
                    # Extract ISBN from identifier string (e.g., "ISBN 1234567890")
                    isbn_match = re.search(r"\d{9,}[Xx0-9]", elem.text)
                    if isbn_match:
                        metadata.isbn = isbn_match.group()
                        break

            # Fallback to input ISBN
            if not metadata.isbn:
                metadata.isbn = isbn_clean

            # Track source
            if self.has_data(metadata):
                metadata.source_providers = {self.name: "primary"}

            return metadata

        except requests.Timeout:
            LOG.warning("Library of Congress API request timed out")
            return None
        except ET.ParseError as e:
            LOG.error(f"Error parsing Library of Congress XML response: {e}")
            return None
        except requests.RequestException as e:
            LOG.error(f"Library of Congress request failed: {e}")
            return None
        except Exception as e:
            LOG.error(f"Error during Library of Congress lookup: {e}")
            return None

    def search(self, query: str, max_results: int = 10) -> list[SearchResult]:
        """Search for books by keyword using Library of Congress SRU API."""
        try:
            # Use SRU API with Dublin Core schema for easier parsing
            url = (
                f"{self.base_url}?"
                f"version=1.1&"
                f"operation=searchRetrieve&"
                f"query={quote(query)}&"
                f"maximumRecords={max_results}&"
                f"recordSchema=dc"
            )
            resp = requests.get(url, timeout=self.timeout, headers={"User-Agent": "BookCatalog/1.0"})

            if resp.status_code != 200:
                LOG.warning(f"Library of Congress API returned status {resp.status_code}")
                return []

            # Parse XML response
            root = ET.fromstring(resp.text)

            # Define namespace
            ns = {
                "srw": "https://www.loc.gov/zing/srw/",
                "dc": "https://purl.org/dc/elements/1.1/",
                "oai_dc": "https://www.openarchives.org/OAI/2.0/oai_dc/",
            }

            # Check if records were found
            records = root.findall(".//srw:recordData/oai_dc:dc/dc:dc", ns)
            if not records:
                # Try alternative namespace path
                records = root.findall(".//srw:recordData/dc:dc", ns)
                if not records:
                    return []

            results = []

            for record in records[:max_results]:
                # Extract title
                title_elements = record.findall("dc:title", ns)
                title = title_elements[0].text if title_elements else None

                if not title:
                    continue

                # Extract authors (creators)
                creator_elements = record.findall("dc:creator", ns)
                authors = [elem.text for elem in creator_elements if elem.text]

                # Extract publisher
                publisher_elements = record.findall("dc:publisher", ns)
                publisher = publisher_elements[0].text if publisher_elements else None

                # Extract date
                publication_date = None
                publication_year = None
                date_elements = record.findall("dc:date", ns)
                if date_elements and date_elements[0].text:
                    date_str = date_elements[0].text
                    # Try to parse various date formats
                    for fmt in ["%Y-%m-%d", "%Y", "%Y-%m"]:
                        try:
                            if fmt == "%Y":
                                publication_year = int(date_str[:4])
                                publication_date = datetime(publication_year, 1, 1)
                            else:
                                publication_date = datetime.strptime(date_str, fmt)
                                publication_year = publication_date.year
                            break
                        except ValueError:
                            continue

                # Extract ISBN from identifiers
                isbn_10 = None
                isbn_13 = None
                identifier_elements = record.findall("dc:identifier", ns)
                for elem in identifier_elements:
                    if elem.text and "isbn" in elem.text.lower():
                        # Extract ISBN from identifier string (e.g., "ISBN 1234567890")
                        isbn_match = re.search(r"\d{9,}[Xx0-9]", elem.text)
                        if isbn_match:
                            isbn = isbn_match.group()
                            if len(isbn) == 10:
                                isbn_10 = isbn
                            elif len(isbn) == 13:
                                isbn_13 = isbn

                result = SearchResult(
                    title=title,
                    authors=authors,
                    publisher=publisher,
                    publication_date=publication_date,
                    publication_year=publication_year,
                    isbn_10=isbn_10,
                    isbn_13=isbn_13,
                    provider=self.name,
                    provider_record_id=""
                )
                results.append(result)

            return results

        except requests.Timeout:
            LOG.warning("Library of Congress API request timed out")
            return []
        except ET.ParseError as e:
            LOG.error(f"Error parsing Library of Congress XML response: {e}")
            return []
        except requests.RequestException as e:
            LOG.error(f"Library of Congress request failed: {e}")
            return []
        except Exception as e:
            LOG.error(f"Error during Library of Congress search: {e}")
            return []
