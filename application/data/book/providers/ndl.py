import logging
import re
from datetime import datetime
from urllib.parse import quote
from xml.etree import ElementTree as ET

import requests

from application.data.book.providers.base import BookMetadata, BookMetadataProvider, SearchResult

LOG = logging.getLogger(__name__)


class NDLSearchProvider(BookMetadataProvider):
    """Provider for National Diet Library Search API (Japanese books)."""

    def __init__(self, timeout: int = 10):
        super().__init__(timeout)
        self.name = "NDL Search"
        self.base_url = "https://iss.ndl.go.jp/api/sru"

    def lookup(self, isbn: str) -> BookMetadata | None:
        """Look up book metadata by ISBN using NDL Search SRU API."""
        isbn_clean = self.normalize_isbn(isbn)

        try:
            # Use SRU API with ISBN query
            url = (
                f"{self.base_url}?"
                f"operation=searchRetrieve&"
                f"query=isbn={quote(isbn_clean)}&"
                f"maximumRecords=1&"
                f"recordSchema=dcndl"
            )
            
            resp = requests.get(url, timeout=self.timeout, headers={"User-Agent": "BookCatalog/1.0"})

            if resp.status_code != 200:
                LOG.warning(f"NDL Search API returned status {resp.status_code}")
                return None

            # Parse XML response
            root = ET.fromstring(resp.text)

            # Define namespaces for SRU and DCNDL schema
            ns = {
                "srw": "http://www.loc.gov/zing/srw/",
                "dc": "http://purl.org/dc/elements/1.1/",
                "dcterms": "http://purl.org/dc/terms/",
                "dcndl": "http://ndl.go.jp/dcndl/terms/",
                "rdf": "http://www.w3.org/1999/02/22-rdf-syntax-ns#",
            }

            # Check if records were found
            records = root.findall(".//srw:recordData", ns)
            if not records:
                return None

            record_data = records[0]
            metadata = BookMetadata()

            # Extract title (dc:title)
            title_elements = record_data.findall(".//dc:title", ns)
            if title_elements:
                # Use the first title
                metadata.title = title_elements[0].text

            # Extract authors (dc:creator)
            creator_elements = record_data.findall(".//dc:creator", ns)
            if creator_elements:
                metadata.authors = [elem.text for elem in creator_elements if elem.text]

            # Extract publisher (dc:publisher)
            publisher_elements = record_data.findall(".//dc:publisher", ns)
            if publisher_elements:
                metadata.publisher = publisher_elements[0].text

            # Extract publication date (dcterms:issued or dc:date)
            date_elements = record_data.findall(".//dcterms:issued", ns) or record_data.findall(".//dc:date", ns)
            if date_elements and date_elements[0].text:
                date_str = date_elements[0].text
                # Try to parse various date formats (YYYY, YYYY-MM, YYYY-MM-DD)
                for fmt in ["%Y-%m-%d", "%Y-%m", "%Y"]:
                    try:
                        if fmt == "%Y":
                            metadata.date_published = datetime.strptime(date_str[:4], fmt)
                        else:
                            metadata.date_published = datetime.strptime(date_str, fmt)
                        break
                    except ValueError:
                        continue

            # Extract ISBN (dc:identifier with isbn scheme)
            identifier_elements = record_data.findall(".//dc:identifier", ns)
            for elem in identifier_elements:
                if elem.text and "isbn" in elem.text.lower():
                    # Extract ISBN from identifier string
                    isbn_match = re.search(r"\d{9,}[Xx0-9]", elem.text)
                    if isbn_match:
                        metadata.isbn = isbn_match.group()
                        break

            # Fallback to input ISBN
            if not metadata.isbn:
                metadata.isbn = isbn_clean

            # Extract page count (dcndl:extent)
            extent_elements = record_data.findall(".//dcndl:extent", ns)
            if extent_elements and extent_elements[0].text:
                extent_str = extent_elements[0].text
                # Try to extract number from extent (e.g., "300p")
                page_match = re.search(r"\d+", extent_str)
                if page_match:
                    try:
                        metadata.page_count = int(page_match.group())
                    except (ValueError, TypeError):
                        pass

            # Extract language (dc:language)
            language_elements = record_data.findall(".//dc:language", ns)
            if language_elements and language_elements[0].text:
                # Store language in description since BookMetadata doesn't have a language field
                lang = language_elements[0].text
                if not metadata.description:
                    metadata.description = f"Language: {lang}"

            # Extract description (dcterms:abstract or dc:description)
            desc_elements = record_data.findall(".//dcterms:abstract", ns) or record_data.findall(".//dc:description", ns)
            if desc_elements and desc_elements[0].text:
                if metadata.description:
                    metadata.description = f"{metadata.description}\n\n{desc_elements[0].text}"
                else:
                    metadata.description = desc_elements[0].text

            # Track source
            if self.has_data(metadata):
                metadata.source_providers = {self.name: "primary"}

            return metadata

        except requests.Timeout:
            LOG.warning("NDL Search API request timed out")
            return None
        except ET.ParseError as e:
            LOG.error(f"Error parsing NDL Search XML response: {e}")
            return None
        except requests.RequestException as e:
            LOG.error(f"NDL Search request failed: {e}")
            return None
        except Exception as e:
            LOG.error(f"Error during NDL Search lookup: {e}")
            return None

    def search(self, query: str, max_results: int = 10) -> list[SearchResult]:
        """Search for books by keyword using NDL Search SRU API."""
        try:
            # Use SRU API with keyword query
            url = (
                f"{self.base_url}?"
                f"operation=searchRetrieve&"
                f"query={quote(query)}&"
                f"maximumRecords={max_results}&"
                f"recordSchema=dcndl"
            )
            
            resp = requests.get(url, timeout=self.timeout, headers={"User-Agent": "BookCatalog/1.0"})

            if resp.status_code != 200:
                LOG.warning(f"NDL Search API returned status {resp.status_code}")
                return []

            # Parse XML response
            root = ET.fromstring(resp.text)

            # Define namespaces for SRU and DCNDL schema
            ns = {
                "srw": "http://www.loc.gov/zing/srw/",
                "dc": "http://purl.org/dc/elements/1.1/",
                "dcterms": "http://purl.org/dc/terms/",
                "dcndl": "http://ndl.go.jp/dcndl/terms/",
                "rdf": "http://www.w3.org/1999/02/22-rdf-syntax-ns#",
            }

            # Check if records were found
            records = root.findall(".//srw:recordData", ns)
            if not records:
                return []

            results = []

            for record_data in records[:max_results]:
                # Extract title
                title_elements = record_data.findall(".//dc:title", ns)
                title = title_elements[0].text if title_elements else None

                if not title:
                    continue

                # Extract authors (creators)
                creator_elements = record_data.findall(".//dc:creator", ns)
                authors = [elem.text for elem in creator_elements if elem.text]

                # Extract publisher
                publisher_elements = record_data.findall(".//dc:publisher", ns)
                publisher = publisher_elements[0].text if publisher_elements else None

                # Extract date
                publication_date = None
                publication_year = None
                date_elements = record_data.findall(".//dcterms:issued", ns) or record_data.findall(".//dc:date", ns)
                if date_elements and date_elements[0].text:
                    date_str = date_elements[0].text
                    # Try to parse various date formats
                    for fmt in ["%Y-%m-%d", "%Y-%m", "%Y"]:
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
                identifier_elements = record_data.findall(".//dc:identifier", ns)
                for elem in identifier_elements:
                    if elem.text and "isbn" in elem.text.lower():
                        isbn_match = re.search(r"\d{9,}[Xx0-9]", elem.text)
                        if isbn_match:
                            isbn = isbn_match.group()
                            if len(isbn) == 10:
                                isbn_10 = isbn
                            elif len(isbn) == 13:
                                isbn_13 = isbn

                # Extract page count
                page_count = None
                extent_elements = record_data.findall(".//dcndl:extent", ns)
                if extent_elements and extent_elements[0].text:
                    extent_str = extent_elements[0].text
                    page_match = re.search(r"\d+", extent_str)
                    if page_match:
                        try:
                            page_count = int(page_match.group())
                        except (ValueError, TypeError):
                            pass

                # Extract language
                language = None
                language_elements = record_data.findall(".//dc:language", ns)
                if language_elements and language_elements[0].text:
                    language = language_elements[0].text

                # Extract description
                description = None
                desc_elements = record_data.findall(".//dcterms:abstract", ns) or record_data.findall(".//dc:description", ns)
                if desc_elements and desc_elements[0].text:
                    description = desc_elements[0].text

                result = SearchResult(
                    title=title,
                    authors=authors,
                    publisher=publisher,
                    publication_date=publication_date,
                    publication_year=publication_year,
                    page_count=page_count,
                    isbn_10=isbn_10,
                    isbn_13=isbn_13,
                    description=description,
                    language=language,
                    provider=self.name,
                    provider_record_id=""
                )
                results.append(result)

            return results

        except requests.Timeout:
            LOG.warning("NDL Search API request timed out")
            return []
        except ET.ParseError as e:
            LOG.error(f"Error parsing NDL Search XML response: {e}")
            return []
        except requests.RequestException as e:
            LOG.error(f"NDL Search request failed: {e}")
            return []
        except Exception as e:
            LOG.error(f"Error during NDL Search search: {e}")
            return []
