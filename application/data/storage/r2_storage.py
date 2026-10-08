import logging
from typing import Any
import boto3
import requests
from botocore.config import Config
from botocore.exceptions import ClientError

LOG = logging.getLogger(__name__)


def derive_thumb_key(cover_key: str) -> str:
    """Derive thumbnail key deterministically from cover key by inserting '_thumb' before '.avif'."""
    if not cover_key:
        return ""
    if cover_key.endswith(".avif"):
        return f"{cover_key[:-5]}_thumb.avif"
    return f"{cover_key}_thumb"


class R2Storage:
    """Reusable Cloudflare R2 client using boto3 S3-compatible interface."""

    def __init__(
        self,
        account_id: str,
        access_key_id: str,
        secret_access_key: str,
        bucket_name: str,
        public_url: str | None = None,
        s3_client: Any | None = None,
        cf_api_token: str | None = None,
        cf_zone_id: str | None = None,
    ):
        self.account_id = account_id
        self.bucket_name = bucket_name
        self.public_url = public_url.rstrip("/") if public_url else ""
        self.cf_api_token = cf_api_token
        self.cf_zone_id = cf_zone_id

        if s3_client is not None:
            self.s3_client = s3_client
        else:
            endpoint_url = f"https://{account_id}.r2.cloudflarestorage.com"
            self.s3_client = boto3.client(
                "s3",
                endpoint_url=endpoint_url,
                aws_access_key_id=access_key_id,
                aws_secret_access_key=secret_access_key,
                region_name="auto",
                config=Config(signature_version="s3v4"),
            )

        LOG.info(f"Initialized R2Storage for bucket '{bucket_name}'")

    def upload_file(self, key: str, data: bytes, content_type: str = "image/avif") -> bool:
        """Upload raw bytes to R2 with the specified content type."""
        try:
            self.s3_client.put_object(
                Bucket=self.bucket_name,
                Key=key,
                Body=data,
                ContentType=content_type,
            )
            LOG.info(f"Successfully uploaded R2 object: {key} ({len(data)} bytes)")
            return True
        except ClientError as e:
            LOG.error(f"ClientError uploading to R2 ({key}): {e}")
            raise
        except Exception as e:
            LOG.error(f"Error uploading to R2 ({key}): {e}")
            raise

    def delete_file(self, key: str) -> bool:
        """Delete a single object from R2."""
        if not key:
            return False
        try:
            self.s3_client.delete_object(
                Bucket=self.bucket_name,
                Key=key,
            )
            LOG.info(f"Successfully deleted R2 object: {key}")
            return True
        except ClientError as e:
            LOG.error(f"ClientError deleting from R2 ({key}): {e}")
            return False
        except Exception as e:
            LOG.error(f"Error deleting from R2 ({key}): {e}")
            return False

    def delete_cover_and_thumb(self, cover_key: str) -> bool:
        """Delete both the full-size and thumbnail objects for a cover."""
        if not cover_key:
            return False
        thumb_key = derive_thumb_key(cover_key)
        success_full = self.delete_file(cover_key)
        success_thumb = self.delete_file(thumb_key)
        return success_full and success_thumb

    def get_public_url(self, key: str | None) -> str:
        """Construct full public URL for an R2 key."""
        if not key or not self.public_url:
            return ""
        return f"{self.public_url}/{key.lstrip('/')}"

    def get_thumb_url(self, cover_key: str | None) -> str:
        """Construct full public URL for a thumbnail derived from a cover key."""
        if not cover_key:
            return ""
        thumb_key = derive_thumb_key(cover_key)
        return self.get_public_url(thumb_key)

    def purge_cdn_cache(self, urls: list[str]) -> bool:
        """
        Purge specific URLs from Cloudflare CDN cache.

        Args:
            urls: List of complete public URLs to purge from cache

        Returns:
            True if purge was successful, False otherwise
        """
        if not self.cf_api_token or not self.cf_zone_id:
            LOG.warning("Cloudflare API token or zone ID not configured, skipping CDN cache purge")
            return False

        if not urls:
            LOG.warning("No URLs provided for CDN cache purge")
            return False

        # Filter out empty URLs
        valid_urls = [url for url in urls if url]
        if not valid_urls:
            LOG.warning("No valid URLs provided for CDN cache purge")
            return False

        endpoint = f"https://api.cloudflare.com/client/v4/zones/{self.cf_zone_id}/purge_cache"
        headers = {
            "Authorization": f"Bearer {self.cf_api_token}",
            "Content-Type": "application/json",
        }
        payload = {"files": valid_urls}

        try:
            response = requests.post(
                endpoint,
                headers=headers,
                json=payload,
                timeout=10,
            )
            response.raise_for_status()

            result = response.json()
            if result.get("success"):
                LOG.info(f"Successfully purged {len(valid_urls)} URL(s) from Cloudflare CDN cache")
                return True
            else:
                errors = result.get("errors", [])
                LOG.error(f"Cloudflare CDN cache purge failed: {errors}")
                return False

        except requests.exceptions.Timeout:
            LOG.error("Cloudflare CDN cache purge request timed out")
            return False
        except requests.exceptions.RequestException as e:
            LOG.error(f"Cloudflare CDN cache purge request failed: {e}")
            return False
        except Exception as e:
            LOG.error(f"Unexpected error during Cloudflare CDN cache purge: {e}")
            return False
