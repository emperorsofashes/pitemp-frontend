import io
import logging
from PIL import Image, ImageOps, UnidentifiedImageError

LOG = logging.getLogger(__name__)

# Max allowable dimensions to prevent decompression bombs and memory exhaustion
MAX_IMAGE_DIMENSION = 10_000
MAX_IMAGE_PIXELS = 50_000_000
FULL_SIZE_MAX_DIMENSION = 1600
THUMBNAIL_MAX_DIMENSION = 400
AVIF_QUALITY = 60

# Configure Pillow decompression bomb protection
Image.MAX_IMAGE_PIXELS = MAX_IMAGE_PIXELS


class ImageValidationError(Exception):
    """Raised when an uploaded image fails validation or decoding."""
    pass


def _resize_preserving_aspect(image: Image.Image, max_dimension: int) -> Image.Image:
    """
    Resize image so that its longest dimension does not exceed max_dimension.
    Preserves aspect ratio and never upscales.
    """
    orig_w, orig_h = image.size
    longest = max(orig_w, orig_h)

    # Never upscale
    if longest <= max_dimension:
        return image.copy()

    # Image.thumbnail modifies in place, maintains aspect ratio, and avoids upscaling
    resized = image.copy()
    resized.thumbnail((max_dimension, max_dimension), Image.Resampling.LANCZOS)
    return resized


def _prepare_image_for_avif(image: Image.Image) -> Image.Image:
    """
    Ensure the image is in an appropriate color mode for AVIF encoding.
    Preserves RGBA transparency if present, otherwise converts to RGB.
    Applies EXIF orientation if available.
    """
    # Auto-rotate according to EXIF orientation tag if present
    try:
        image = ImageOps.exif_transpose(image) or image
    except Exception:
        pass

    if image.mode in ("RGBA", "LA"):
        return image
    elif image.mode == "P":
        # Palette mode - convert to RGBA if transparency is defined, else RGB
        if "transparency" in image.info:
            return image.convert("RGBA")
        return image.convert("RGB")
    elif image.mode in ("RGB", "L"):
        return image
    else:
        # CMYK, YCbCr, 1, etc. -> RGB
        return image.convert("RGB")


def process_book_cover(file_bytes: bytes) -> tuple[bytes, bytes]:
    """
    Validates and processes uploaded raw image bytes into two AVIF images:
    1. Full-size cover (max 1600px longest dimension, q60 AVIF, no upscaling, aspect ratio preserved)
    2. Thumbnail (max 400px longest dimension, q60 AVIF, from original decoded image, no upscaling, aspect ratio preserved)

    Returns:
        tuple[bytes, bytes]: (full_size_avif_bytes, thumbnail_avif_bytes)
        
    Raises:
        ImageValidationError: If the file cannot be decoded or exceeds safety limits.
    """
    if not file_bytes:
        raise ImageValidationError("No image data provided.")

    # Step 1: Pillow verify to ensure file integrity without full decompression
    try:
        with Image.open(io.BytesIO(file_bytes)) as verify_img:
            verify_img.verify()
    except (Image.DecompressionBombError, Image.DecompressionBombWarning) as e:
        LOG.warning(f"Decompression bomb detected during image verification: {e}")
        raise ImageValidationError("Image exceeds safe decompression limits.")
    except Exception as e:
        LOG.warning(f"Image verification failed: {e}")
        raise ImageValidationError("Uploaded file is not a valid image.")

    # Step 2: Decode and inspect dimensions
    try:
        with Image.open(io.BytesIO(file_bytes)) as img:
            w, h = img.size
            if w <= 0 or h <= 0:
                raise ImageValidationError("Invalid image dimensions.")

            if w > MAX_IMAGE_DIMENSION or h > MAX_IMAGE_DIMENSION:
                raise ImageValidationError(
                    f"Image dimension ({w}x{h}) exceeds the maximum allowable limit of {MAX_IMAGE_DIMENSION}px."
                )

            if w * h > MAX_IMAGE_PIXELS:
                raise ImageValidationError("Image pixel count exceeds the maximum allowable safety limit.")

            # Load image data into memory before closing context
            img.load()
            prepared = _prepare_image_for_avif(img)

    except ImageValidationError:
        raise
    except (Image.DecompressionBombError, Image.DecompressionBombWarning) as e:
        LOG.warning(f"Decompression bomb detected during image loading: {e}")
        raise ImageValidationError("Image exceeds safe decompression limits.")
    except UnidentifiedImageError as e:
        LOG.warning(f"Unidentified image: {e}")
        raise ImageValidationError("Uploaded file could not be decoded as an image.")
    except Exception as e:
        LOG.error(f"Error opening image: {e}")
        raise ImageValidationError(f"Could not process image: {e}")

    # Step 3: Generate full-size image (max 1600px longest side, q60 AVIF)
    try:
        full_img = _resize_preserving_aspect(prepared, FULL_SIZE_MAX_DIMENSION)
        full_buf = io.BytesIO()
        full_img.save(full_buf, format="AVIF", quality=AVIF_QUALITY)
        full_bytes = full_buf.getvalue()
    except Exception as e:
        LOG.error(f"Error generating full-size AVIF: {e}")
        raise ImageValidationError(f"Failed to generate full-size AVIF cover: {e}")

    # Step 4: Generate thumbnail from the ORIGINAL decoded image (max 400px longest side, q60 AVIF)
    try:
        thumb_img = _resize_preserving_aspect(prepared, THUMBNAIL_MAX_DIMENSION)
        thumb_buf = io.BytesIO()
        thumb_img.save(thumb_buf, format="AVIF", quality=AVIF_QUALITY)
        thumb_bytes = thumb_buf.getvalue()
    except Exception as e:
        LOG.error(f"Error generating thumbnail AVIF: {e}")
        raise ImageValidationError(f"Failed to generate thumbnail AVIF: {e}")

    return full_bytes, thumb_bytes
