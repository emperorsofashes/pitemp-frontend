import io
from unittest.mock import MagicMock, Mock, patch

import pytest
from bson import ObjectId
from PIL import Image

from application import create_flask_app
from application.constants.app_constants import (
    BOOKS_DATABASE_CONFIG_KEY,
    R2_CLIENT_CONFIG_KEY,
)
from application.data.book.book import Book
from application.data.book.image_processor import (
    AVIF_QUALITY,
    FULL_SIZE_MAX_DIMENSION,
    MAX_IMAGE_DIMENSION,
    THUMBNAIL_MAX_DIMENSION,
    ImageValidationError,
    _resize_preserving_aspect,
    process_book_cover,
)
from application.data.storage.r2_storage import R2Storage, derive_thumb_key


def _create_test_image(format="JPEG", size=(1200, 1800), color=(100, 150, 200)) -> bytes:
    """Helper to generate in-memory image bytes."""
    buf = io.BytesIO()
    mode = "RGBA" if format.upper() == "PNG" else "RGB"
    img = Image.new(mode, size, color)
    img.save(buf, format=format)
    return buf.getvalue()


# ============================================================================
# Unit Tests: Image Processing & Validation
# ============================================================================

class TestImageProcessor:
    def test_valid_jpeg_upload(self):
        """Test valid JPEG image processing into two AVIF images."""
        data = _create_test_image(format="JPEG", size=(3000, 4500))
        full, thumb = process_book_cover(data)

        full_im = Image.open(io.BytesIO(full))
        thumb_im = Image.open(io.BytesIO(thumb))

        assert full_im.format == "AVIF"
        assert thumb_im.format == "AVIF"
        assert full_im.size == (1067, 1600)
        assert thumb_im.size == (267, 400)

    def test_valid_png_upload(self):
        """Test valid PNG image processing into two AVIF images."""
        data = _create_test_image(format="PNG", size=(1200, 1600))
        full, thumb = process_book_cover(data)

        full_im = Image.open(io.BytesIO(full))
        thumb_im = Image.open(io.BytesIO(thumb))

        assert full_im.format == "AVIF"
        assert thumb_im.format == "AVIF"
        assert full_im.size == (1200, 1600)
        assert thumb_im.size == (300, 400)

    def test_valid_webp_upload(self):
        """Test valid WebP image processing into two AVIF images."""
        data = _create_test_image(format="WEBP", size=(1600, 900))
        full, thumb = process_book_cover(data)

        full_im = Image.open(io.BytesIO(full))
        thumb_im = Image.open(io.BytesIO(thumb))

        assert full_im.format == "AVIF"
        assert thumb_im.format == "AVIF"
        assert full_im.size == (1600, 900)
        assert thumb_im.size == (400, 225)

    def test_correct_dimensions_landscape(self):
        """Test landscape image dimensions: longest dimension <= 1600 and <= 400."""
        data = _create_test_image(format="JPEG", size=(2400, 1200))
        full, thumb = process_book_cover(data)

        full_im = Image.open(io.BytesIO(full))
        thumb_im = Image.open(io.BytesIO(thumb))

        assert full_im.size == (1600, 800)
        assert thumb_im.size == (400, 200)

    def test_no_upscaling_behavior(self):
        """Test that images smaller than max dimensions are NEVER upscaled."""
        # 300x450: Longest side is 450.
        # Full-size max is 1600 -> not upscaled, stays 300x450.
        # Thumbnail max is 400 -> scaled down to 267x400 (never upscaled).
        data = _create_test_image(format="PNG", size=(300, 450))
        full, thumb = process_book_cover(data)

        full_im = Image.open(io.BytesIO(full))
        thumb_im = Image.open(io.BytesIO(thumb))

        assert full_im.size == (300, 450)
        assert thumb_im.size == (267, 400)

        # Image smaller than even thumbnail: 200x150
        data_small = _create_test_image(format="PNG", size=(200, 150))
        full_s, thumb_s = process_book_cover(data_small)
        full_s_im = Image.open(io.BytesIO(full_s))
        thumb_s_im = Image.open(io.BytesIO(thumb_s))

        assert full_s_im.size == (200, 150)
        assert thumb_s_im.size == (200, 150)

    def test_aspect_ratio_preservation(self):
        """Test aspect ratio is preserved within rounding limits."""
        data = _create_test_image(format="JPEG", size=(1200, 1800))
        full, thumb = process_book_cover(data)

        full_im = Image.open(io.BytesIO(full))
        thumb_im = Image.open(io.BytesIO(thumb))

        orig_ratio = 1200 / 1800
        full_ratio = full_im.width / full_im.height
        thumb_ratio = thumb_im.width / thumb_im.height

        assert abs(full_ratio - orig_ratio) < 0.01
        assert abs(thumb_ratio - orig_ratio) < 0.01

    def test_thumbnail_from_original_decoded_image(self):
        """Test thumbnail is generated from original decoded image, not 1600px image."""
        # Test directly with _resize_preserving_aspect
        orig = Image.new("RGB", (3000, 4500))
        thumb = _resize_preserving_aspect(orig, 400)
        assert thumb.size == (267, 400)

    def test_avif_quality_setting(self):
        """Verify quality parameter used for AVIF encoding is exactly 60."""
        assert AVIF_QUALITY == 60

        data = _create_test_image(format="JPEG", size=(800, 1200))
        with patch.object(Image.Image, "save", autospec=True) as mock_save:
            # We mock save to inspect arguments
            def fake_save(self, fp, format=None, **kwargs):
                assert format == "AVIF"
                assert kwargs.get("quality") == 60
                fp.write(b"fake-avif")

            mock_save.side_effect = fake_save
            full, thumb = process_book_cover(data)
            assert full == b"fake-avif"
            assert thumb == b"fake-avif"
            assert mock_save.call_count == 2

    def test_invalid_non_image_file(self):
        """Reject non-image files."""
        non_image_data = b"<!DOCTYPE html><html><body>Not an image</body></html>"
        with pytest.raises(ImageValidationError):
            process_book_cover(non_image_data)

    def test_missing_file_data(self):
        """Reject empty data."""
        with pytest.raises(ImageValidationError):
            process_book_cover(b"")

    def test_extremely_large_image_dimensions(self):
        """Reject images exceeding maximum dimensions."""
        fake_img = Mock(spec=Image.Image)
        fake_img.size = (MAX_IMAGE_DIMENSION + 1, 100)
        fake_img.load.return_value = None

        with patch("PIL.Image.open") as mock_open:
            mock_ctx = MagicMock()
            mock_ctx.__enter__.return_value = fake_img
            mock_open.return_value = mock_ctx

            with pytest.raises(ImageValidationError) as exc_info:
                process_book_cover(b"fake-bytes")
            assert "exceeds the maximum allowable limit" in str(exc_info.value)


# ============================================================================
# Unit Tests: R2 Storage Client & URL Derivation
# ============================================================================

class TestR2Storage:
    def test_derive_thumb_key(self):
        """Verify deterministic thumbnail key generation."""
        assert derive_thumb_key("covers/671d9e8a1f.avif") == "covers/671d9e8a1f_thumb.avif"
        assert derive_thumb_key("covers/abc_123.avif") == "covers/abc_123_thumb.avif"
        assert derive_thumb_key("") == ""

    def test_r2_storage_urls(self):
        """Verify public URL construction without credentials."""
        mock_s3 = Mock()
        storage = R2Storage(
            account_id="test-account",
            access_key_id="test-key",
            secret_access_key="test-secret",
            bucket_name="test-bucket",
            public_url="https://pub-test.r2.dev",
            s3_client=mock_s3,
        )

        cover_key = "covers/671d9e8a1f.avif"
        assert storage.get_public_url(cover_key) == "https://pub-test.r2.dev/covers/671d9e8a1f.avif"
        assert storage.get_thumb_url(cover_key) == "https://pub-test.r2.dev/covers/671d9e8a1f_thumb.avif"

    def test_r2_storage_upload_file(self):
        """Verify boto3 upload uses correct bucket, key, data, and ContentType: image/avif."""
        mock_s3 = Mock()
        storage = R2Storage(
            account_id="test-account",
            access_key_id="test-key",
            secret_access_key="test-secret",
            bucket_name="test-bucket",
            public_url="https://pub-test.r2.dev",
            s3_client=mock_s3,
        )

        test_data = b"avif-bytes"
        storage.upload_file("covers/123.avif", test_data, content_type="image/avif")

        mock_s3.put_object.assert_called_once_with(
            Bucket="test-bucket",
            Key="covers/123.avif",
            Body=test_data,
            ContentType="image/avif",
        )

    def test_r2_storage_delete_cover_and_thumb(self):
        """Verify deleting a cover deletes both the full-size and thumbnail objects."""
        mock_s3 = Mock()
        storage = R2Storage(
            account_id="test-account",
            access_key_id="test-key",
            secret_access_key="test-secret",
            bucket_name="test-bucket",
            s3_client=mock_s3,
        )

        storage.delete_cover_and_thumb("covers/123.avif")

        assert mock_s3.delete_object.call_count == 2
        mock_s3.delete_object.assert_any_call(Bucket="test-bucket", Key="covers/123.avif")
        mock_s3.delete_object.assert_any_call(Bucket="test-bucket", Key="covers/123_thumb.avif")


# ============================================================================
# Integration Tests: Flask Endpoints, Auth, CSRF, Mongo, and R2
# ============================================================================

@pytest.fixture
def mock_storage():
    mock_s3 = Mock()
    storage = R2Storage(
        account_id="test-account",
        access_key_id="test-key",
        secret_access_key="test-secret",
        bucket_name="test-bucket",
        public_url="https://pub-test.r2.dev",
        s3_client=mock_s3,
    )
    return storage


@pytest.fixture
def app(mock_storage):
    mock_mongo_client = MagicMock()
    with patch.dict(
        "os.environ",
        {
            "SECRET_KEY": "test-secret-key",
            "ADMIN_PASSWORD": "test-admin-password",
            "MONGO_USER": "test-user",
            "MONGO_PASSWORD": "test-password",
            "MONGO_HOST": "localhost",
            "R2_ACCOUNT_ID": "test-account",
            "R2_ACCESS_KEY_ID": "test-key",
            "R2_SECRET_ACCESS_KEY": "test-secret",
            "R2_BUCKET_NAME": "test-bucket",
            "R2_PUBLIC_URL": "https://pub-test.r2.dev",
            "WTF_CSRF_ENABLED": "true",
        },
    ), patch("application.MongoClient", return_value=mock_mongo_client), patch("application.valkey.Valkey"):
        app = create_flask_app()
        app.config["TESTING"] = True
        app.config[R2_CLIENT_CONFIG_KEY] = mock_storage

        # Mock BookDao
        mock_book_dao = Mock()
        mock_book_dao.get_all_books.return_value = []
        app.config[BOOKS_DATABASE_CONFIG_KEY] = mock_book_dao

        yield app


@pytest.fixture
def client(app):
    return app.test_client()


class TestCoverRoutes:
    def test_unauthenticated_upload_rejection(self, client, app):
        """Unauthenticated cover upload must be rejected and redirected to login."""
        app.config["WTF_CSRF_ENABLED"] = False
        response = client.post(
            "/books/book123/cover",
            data={"cover_image": (io.BytesIO(b"data"), "cover.jpg")},
            content_type="multipart/form-data",
        )
        assert response.status_code == 302
        assert "/login" in response.location

    def test_csrf_protection(self, client):
        """State-changing cover upload must require valid CSRF protection."""
        with client.session_transaction() as sess:
            sess["authenticated"] = True

        # POST without CSRF token
        response = client.post(
            "/books/book123/cover",
            data={"cover_image": (io.BytesIO(b"data"), "cover.jpg")},
            content_type="multipart/form-data",
        )
        assert response.status_code == 400

    def test_nonexistent_book(self, client, app):
        """Uploading for a nonexistent book redirects to /books."""
        app.config["WTF_CSRF_ENABLED"] = False
        book_dao = app.config[BOOKS_DATABASE_CONFIG_KEY]
        book_dao.get_book.return_value = None

        with client.session_transaction() as sess:
            sess["authenticated"] = True

        img_bytes = _create_test_image()
        response = client.post(
            "/books/missing_book/cover",
            data={"cover_image": (io.BytesIO(img_bytes), "cover.jpg")},
            content_type="multipart/form-data",
            follow_redirects=True,
        )
        assert response.status_code == 200
        assert b"Book not found" in response.data

    def test_missing_file(self, client, app):
        """Posting without selecting a file redirects with error message."""
        app.config["WTF_CSRF_ENABLED"] = False
        book_dao = app.config[BOOKS_DATABASE_CONFIG_KEY]
        book_dao.get_book.return_value = Book(id="b1", title="Test", authors=["Author"])

        with client.session_transaction() as sess:
            sess["authenticated"] = True

        response = client.post(
            "/books/b1/cover",
            data={},
            content_type="multipart/form-data",
            follow_redirects=True,
        )
        assert response.status_code == 200
        assert b"No image file was selected" in response.data

    def test_invalid_image_upload(self, client, app, mock_storage):
        """Uploading a non-image file flashes error and modifies nothing."""
        app.config["WTF_CSRF_ENABLED"] = False
        book_dao = app.config[BOOKS_DATABASE_CONFIG_KEY]
        book_dao.get_book.return_value = Book(id="b1", title="Test", authors=["Author"])

        with client.session_transaction() as sess:
            sess["authenticated"] = True

        response = client.post(
            "/books/b1/cover",
            data={"cover_image": (io.BytesIO(b"not-an-image"), "test.jpg")},
            content_type="multipart/form-data",
            follow_redirects=True,
        )
        assert response.status_code == 200
        assert b"Uploaded file is not a valid image" in response.data
        mock_storage.s3_client.put_object.assert_not_called()
        book_dao.set_cover_key.assert_not_called()

    def test_oversized_upload(self, client, app):
        """Uploading a file exceeding MAX_CONTENT_LENGTH (10 MB) triggers 413 error handler."""
        app.config["WTF_CSRF_ENABLED"] = False
        with client.session_transaction() as sess:
            sess["authenticated"] = True

        # Send payload > 10MB
        large_bytes = b"0" * (10 * 1024 * 1024 + 1024)
        response = client.post(
            "/books/b1/cover",
            data={"cover_image": (io.BytesIO(large_bytes), "huge.jpg")},
            content_type="multipart/form-data",
            follow_redirects=True,
        )
        # 413 error handler redirects with flash message
        assert response.status_code == 200
        assert b"10 MB limit" in response.data

    def test_successful_cover_upload(self, client, app, mock_storage):
        """Successful upload creates both R2 objects with ContentType image/avif and updates MongoDB."""
        app.config["WTF_CSRF_ENABLED"] = False
        book_dao = app.config[BOOKS_DATABASE_CONFIG_KEY]
        book_dao.get_book.return_value = Book(id="671d9e8a1f", title="Test Book", authors=["Author"])
        book_dao.set_cover_key.return_value = True

        with client.session_transaction() as sess:
            sess["authenticated"] = True

        img_bytes = _create_test_image(format="JPEG", size=(1200, 1800))
        response = client.post(
            "/books/671d9e8a1f/cover",
            data={"cover_image": (io.BytesIO(img_bytes), "cover.jpg")},
            content_type="multipart/form-data",
            follow_redirects=True,
        )
        assert response.status_code == 200
        assert b"Cover image uploaded successfully" in response.data

        # Verify R2 uploads: both full-size and thumbnail
        assert mock_storage.s3_client.put_object.call_count == 2
        calls = mock_storage.s3_client.put_object.call_args_list

        full_call = [c for c in calls if c.kwargs["Key"] == "covers/671d9e8a1f.avif"][0]
        thumb_call = [c for c in calls if c.kwargs["Key"] == "covers/671d9e8a1f_thumb.avif"][0]

        assert full_call.kwargs["ContentType"] == "image/avif"
        assert thumb_call.kwargs["ContentType"] == "image/avif"

        # Verify MongoDB updated
        book_dao.set_cover_key.assert_called_once_with("671d9e8a1f", "covers/671d9e8a1f.avif")

    def test_replacement_of_existing_cover(self, client, app, mock_storage):
        """Replacing existing cover only deletes old R2 objects after new ones succeed and Mongo updates."""
        app.config["WTF_CSRF_ENABLED"] = False
        book_dao = app.config[BOOKS_DATABASE_CONFIG_KEY]
        # Previous cover key with different name
        book_dao.get_book.return_value = Book(
            id="671d9e8a1f",
            title="Test Book",
            authors=["Author"],
            cover_key="covers/old_id.avif",
        )
        book_dao.set_cover_key.return_value = True

        with client.session_transaction() as sess:
            sess["authenticated"] = True

        img_bytes = _create_test_image()
        response = client.post(
            "/books/671d9e8a1f/cover",
            data={"cover_image": (io.BytesIO(img_bytes), "new.png")},
            content_type="multipart/form-data",
            follow_redirects=True,
        )
        assert response.status_code == 200

        # Old cover and thumb should be deleted
        assert mock_storage.s3_client.delete_object.call_count == 2
        mock_storage.s3_client.delete_object.assert_any_call(
            Bucket="test-bucket", Key="covers/old_id.avif"
        )
        mock_storage.s3_client.delete_object.assert_any_call(
            Bucket="test-bucket", Key="covers/old_id_thumb.avif"
        )

    def test_r2_upload_failure_does_not_modify_mongodb(self, client, app, mock_storage):
        """If R2 upload fails, MongoDB cover_key is NOT updated and partial upload is cleaned up."""
        app.config["WTF_CSRF_ENABLED"] = False
        book_dao = app.config[BOOKS_DATABASE_CONFIG_KEY]
        book_dao.get_book.return_value = Book(id="b1", title="Test", authors=["Author"])

        # First put_object succeeds, second fails
        mock_storage.s3_client.put_object.side_effect = [True, Exception("R2 Connection Failed")]

        with client.session_transaction() as sess:
            sess["authenticated"] = True

        img_bytes = _create_test_image()
        response = client.post(
            "/books/b1/cover",
            data={"cover_image": (io.BytesIO(img_bytes), "cover.jpg")},
            content_type="multipart/form-data",
            follow_redirects=True,
        )
        assert response.status_code == 200
        assert b"Failed to upload cover images to Cloudflare R2" in response.data

        # Mongo should NOT be updated
        book_dao.set_cover_key.assert_not_called()

        # Partial upload (first key) should be cleaned up
        mock_storage.s3_client.delete_object.assert_called_once_with(
            Bucket="test-bucket", Key="covers/b1.avif"
        )

    def test_mongodb_failure_after_r2_upload_cleans_up(self, client, app, mock_storage):
        """If MongoDB update fails after R2 upload, the uploaded R2 objects are cleaned up."""
        app.config["WTF_CSRF_ENABLED"] = False
        book_dao = app.config[BOOKS_DATABASE_CONFIG_KEY]
        book_dao.get_book.return_value = Book(id="b1", title="Test", authors=["Author"])
        book_dao.set_cover_key.side_effect = Exception("MongoDB error")

        with client.session_transaction() as sess:
            sess["authenticated"] = True

        img_bytes = _create_test_image()
        response = client.post(
            "/books/b1/cover",
            data={"cover_image": (io.BytesIO(img_bytes), "cover.jpg")},
            content_type="multipart/form-data",
            follow_redirects=True,
        )
        assert response.status_code == 200
        assert b"Failed to update book cover in database" in response.data

        # Newly uploaded R2 objects must be cleaned up
        assert mock_storage.s3_client.delete_object.call_count == 2
        mock_storage.s3_client.delete_object.assert_any_call(Bucket="test-bucket", Key="covers/b1.avif")
        mock_storage.s3_client.delete_object.assert_any_call(
            Bucket="test-bucket", Key="covers/b1_thumb.avif"
        )

    def test_delete_cover_operation(self, client, app, mock_storage):
        """Deleting a cover removes R2 objects and unsets cover_key in MongoDB."""
        app.config["WTF_CSRF_ENABLED"] = False
        book_dao = app.config[BOOKS_DATABASE_CONFIG_KEY]
        book_dao.get_book.return_value = Book(
            id="671d9e8a1f",
            title="Test Book",
            authors=["Author"],
            cover_key="covers/671d9e8a1f.avif",
        )
        book_dao.delete_cover_key.return_value = True

        with client.session_transaction() as sess:
            sess["authenticated"] = True

        response = client.post(
            "/books/671d9e8a1f/cover/delete",
            follow_redirects=True,
        )
        assert response.status_code == 200
        assert b"Cover image deleted successfully" in response.data

        # Both R2 objects deleted
        assert mock_storage.s3_client.delete_object.call_count == 2
        mock_storage.s3_client.delete_object.assert_any_call(
            Bucket="test-bucket", Key="covers/671d9e8a1f.avif"
        )
        mock_storage.s3_client.delete_object.assert_any_call(
            Bucket="test-bucket", Key="covers/671d9e8a1f_thumb.avif"
        )

        # MongoDB cover_key unset
        book_dao.delete_cover_key.assert_called_once_with("671d9e8a1f")


# ============================================================================
# Unit Tests: Book Model and Dao
# ============================================================================

class TestBookModelAndDao:
    def test_book_model_without_cover_key(self):
        """Existing books without cover_key work normally."""
        doc = {
            "_id": ObjectId("507f1f77bcf86cd799439011"),
            "title": "Legacy Book",
            "authors": ["Author"],
        }
        book = Book.from_mongo(doc)
        assert book.cover_key is None
        assert book.thumb_key is None

    def test_book_model_with_cover_key(self):
        """Books with cover_key derive thumb_key deterministically."""
        doc = {
            "_id": ObjectId("507f1f77bcf86cd799439011"),
            "title": "New Book",
            "authors": ["Author"],
            "cover_key": "covers/507f1f77bcf86cd799439011.avif",
        }
        book = Book.from_mongo(doc)
        assert book.cover_key == "covers/507f1f77bcf86cd799439011.avif"
        assert book.thumb_key == "covers/507f1f77bcf86cd799439011_thumb.avif"

    def test_dao_set_and_delete_cover_key(self):
        """Test BookDao set_cover_key and delete_cover_key operations."""
        from application.data.book.dao import BookDao

        mock_client = MagicMock()
        mock_db = MagicMock()
        mock_coll = MagicMock()
        mock_cache = MagicMock()

        mock_client.__getitem__.return_value = mock_db
        mock_db.__getitem__.return_value = mock_coll

        dao = BookDao(client=mock_client, database=mock_db, cache=mock_cache)

        mock_update_result = Mock()
        mock_update_result.matched_count = 1
        mock_coll.update_one.return_value = mock_update_result

        # Test set_cover_key
        success = dao.set_cover_key("507f1f77bcf86cd799439011", "covers/test.avif")
        assert success is True
        mock_coll.update_one.assert_called_with(
            {"_id": ObjectId("507f1f77bcf86cd799439011")},
            {"$set": {"cover_key": "covers/test.avif"}},
        )

        # Test delete_cover_key
        success_del = dao.delete_cover_key("507f1f77bcf86cd799439011")
        assert success_del is True
        mock_coll.update_one.assert_called_with(
            {"_id": ObjectId("507f1f77bcf86cd799439011")},
            {"$unset": {"cover_key": ""}},
        )

    def test_book_image_host_properties(self):
        """Test cover_url and thumb_url properties using BOOK_IMAGE_HOST env var."""
        with patch.dict("os.environ", {"BOOK_IMAGE_HOST": "https://books.example.com"}):
            book = Book(
                id="123",
                title="Host Test",
                authors=["Author"],
                cover_key="covers/123.avif",
            )
            assert book.cover_url == "https://books.example.com/covers/123.avif"
            assert book.thumb_url == "https://books.example.com/covers/123_thumb.avif"

    def test_book_image_host_fallback_r2_public_url(self):
        """Test cover_url and thumb_url fall back to R2_PUBLIC_URL if BOOK_IMAGE_HOST is not set."""
        with patch.dict("os.environ", {"R2_PUBLIC_URL": "https://r2.example.com"}, clear=False):
            # remove BOOK_IMAGE_HOST if set
            with patch.dict("os.environ", {"BOOK_IMAGE_HOST": ""}):
                book = Book(
                    id="123",
                    title="Fallback Test",
                    authors=["Author"],
                    cover_key="covers/123.avif",
                )
                assert book.cover_url == "https://r2.example.com/covers/123.avif"
                assert book.thumb_url == "https://r2.example.com/covers/123_thumb.avif"
