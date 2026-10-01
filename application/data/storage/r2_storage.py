import logging
from typing import Any
import boto3
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
    ):
        self.account_id = account_id
        self.bucket_name = bucket_name
        self.public_url = public_url.rstrip("/") if public_url else ""

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
