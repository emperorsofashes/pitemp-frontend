import logging
import secrets
from datetime import datetime
from io import BytesIO
from urllib.parse import urljoin, urlparse

import requests
from flask import Blueprint, current_app, flash, jsonify, redirect, render_template, request, session, url_for

from application import DISKS_DATABASE_CONFIG_KEY, DisksDao
from application.constants.app_constants import (
    BEERS_DATABASE_CONFIG_KEY,
    BIRDS_DATABASE_CONFIG_KEY,
    BOOKS_DATABASE_CONFIG_KEY,
    DATABASE_CONFIG_KEY,
    DATETIME_FORMAT_STRING,
    R2_CLIENT_CONFIG_KEY,
)
from application.constants.beer_constants import BEER_STYLES_V1, BEER_STYLES_V2, ROWDY_USERNAME
from application.constants.bird_constants import CARTO_API_KEY
from application.data.beer.dao import BeerDao
from application.data.bird.dao import BirdDao
from application.data.book.dao import BookDao
from application.data.book.image_processor import ImageValidationError, process_book_cover
from application.data.book.providers import (
    BookSearchMerger,
    GoogleBooksProvider,
    LibraryOfCongressProvider,
    MetadataMerger,
    NDLSearchProvider,
    OpenBDProvider,
    OpenLibraryProvider,
)
from application.data.storage.r2_storage import R2Storage
from application.data.storage.ssrf_protection import (
    MAX_REMOTE_IMAGE_SIZE,
    REQUEST_TIMEOUT,
    SSRFValidationError,
    validate_url_for_ssrf,
    validate_redirect_url,
)
from application.data.temperature.dao import ApplicationDao

LOG = logging.getLogger(__name__)
HTML_BLUEPRINT = Blueprint("routes_html", __name__)
DEFAULT_DAYS_BACK = 7


class RemoteImageDownloadError(Exception):
    """Raised when remote image download fails."""
    pass


@HTML_BLUEPRINT.route("/")
def homepage():
    return render_template("index.html")


@HTML_BLUEPRINT.route("/temp")
def temp_index():
    return render_template("temperature/temp_index.html")


@HTML_BLUEPRINT.route("/temp/<int:days_back>")
def days_page(days_back: int):
    return _get_page(days_back)


@HTML_BLUEPRINT.route("/beers")
def beer_index():
    return render_template("beers/index.html")


@HTML_BLUEPRINT.route("/beers/breweries")
def breweries_page():
    breweries = _get_beers_dao().get_breweries()

    return render_template("beers/breweries.html", breweries=breweries)


@HTML_BLUEPRINT.route("/beers/beers")
def beers_page():
    beers_dao = _get_beers_dao()
    beers = beers_dao.get_beers(limit=20)
    total_count = beers_dao.get_num_total_beers()

    return render_template("beers/beers.html", beers=beers, total_count=total_count)


@HTML_BLUEPRINT.route("/beers/beers_data")
def beers_data():
    """API endpoint to fetch all beers as JSON for async loading"""
    username = request.args.get('username', None, type=str)

    beers = _get_beers_dao().get_beers(username=username)

    return jsonify({
        'beers': [
            {
                'name': beer.name,
                'id': beer.id,
                'brewery': beer.brewery,
                'country': beer.country,
                'rating': beer.rating,
                'style': beer.style,
                'abv': beer.abv,
                'first_checkin': beer.first_checkin.isoformat()
            }
            for beer in beers
        ]
    })


@HTML_BLUEPRINT.route("/beers/beers_rowdy")
def beers_rowdy_page():
    beers_dao = _get_beers_dao()
    rowdy_beers = beers_dao.get_beers(username=ROWDY_USERNAME, limit=20)
    total_count = beers_dao.get_num_total_beers(username=ROWDY_USERNAME)

    return render_template("beers/beers.html", beers=rowdy_beers, total_count=total_count,
                           username=ROWDY_USERNAME.title())


@HTML_BLUEPRINT.route("/beers/countries")
def countries_page():
    countries = _get_beers_dao().get_countries()

    return render_template("beers/countries.html", countries=countries)


@HTML_BLUEPRINT.route("/beers/styles")
def styles_page():
    styles = _get_beers_dao().get_styles()

    return render_template("beers/styles.html", styles=styles)


@HTML_BLUEPRINT.route("/beers/missing_styles")
def missing_styles_page():
    """UI endpoint for missing styles page"""
    version = request.args.get('version', 'v2')  # Default to v2

    if version == 'v1':
        styles = BEER_STYLES_V1
    elif version == 'v2':
        styles = BEER_STYLES_V2
    else:
        styles = BEER_STYLES_V2  # Fallback to v2

    missing_styles = _get_beers_dao().get_missing_styles(styles)
    main_missing_count = sum(1 for s in missing_styles if s.is_main_missing)
    rowdy_missing_count = sum(1 for s in missing_styles if s.is_rowdy_missing)

    return render_template(
        "beers/missing_styles.html",
        missing_styles=missing_styles,
        main_missing_count=main_missing_count,
        rowdy_missing_count=rowdy_missing_count,
    )


@HTML_BLUEPRINT.route("/beers/missing_styles_data")
def missing_styles_data():
    """Data endpoint for missing styles API"""
    version = request.args.get('version', 'v2')  # Default to v2

    if version == 'v1':
        styles = BEER_STYLES_V1
    elif version == 'v2':
        styles = BEER_STYLES_V2
    else:
        styles = BEER_STYLES_V2  # Fallback to v2

    missing_styles = _get_beers_dao().get_missing_styles(styles)
    main_missing_count = sum(1 for s in missing_styles if s.is_main_missing)
    rowdy_missing_count = sum(1 for s in missing_styles if s.is_rowdy_missing)

    return jsonify({
        'missing_styles': [
            {
                'style_name': s.style_name,
                'is_main_missing': s.is_main_missing,
                'is_rowdy_missing': s.is_rowdy_missing
            } for s in missing_styles
        ],
        'main_missing_count': main_missing_count,
        'rowdy_missing_count': rowdy_missing_count
    })


@HTML_BLUEPRINT.route("/disks")
def disks_index():
    return render_template("disks/index.html")


@HTML_BLUEPRINT.route("/disks/snapshot")
def disks_snapshot():
    disk_dao = _get_disks_dao()
    data = disk_dao.get_drive_letter_to_data()
    drive_snapshot = {key: values[-1] for key, values in data.items() if values}
    total_capacity = sum(snapshot.capacity_bytes for snapshot in drive_snapshot.values())
    total_free = sum(snapshot.free_bytes for snapshot in drive_snapshot.values())
    total_used = sum(snapshot.used_bytes for snapshot in drive_snapshot.values())
    total_percent_used = (total_used / total_capacity) * 100 if total_capacity > 0 else 0.0
    return render_template(
        "disks/snapshot.html",
        drives=drive_snapshot,
        total_capacity=total_capacity,
        total_free=total_free,
        total_used=total_used,
        total_percent_used=total_percent_used,
    )


@HTML_BLUEPRINT.route("/disks/overview")
def disks_overview():
    disk_dao = _get_disks_dao()
    data = disk_dao.get_drive_letter_to_data()
    drive_snapshot = {key: values[-1] for key, values in data.items() if values}
    total_capacity = sum(snapshot.capacity_bytes for snapshot in drive_snapshot.values())
    total_free = sum(snapshot.free_bytes for snapshot in drive_snapshot.values())
    total_used = sum(snapshot.used_bytes for snapshot in drive_snapshot.values())
    total_percent_used = (total_used / total_capacity) * 100 if total_capacity > 0 else 0.0
    return render_template(
        "disks/overview.html",
        drives=drive_snapshot,
        total_capacity=total_capacity,
        total_free=total_free,
        total_used=total_used,
        total_percent_used=total_percent_used,
    )


@HTML_BLUEPRINT.route("/disks/free_space")
def free_space_graph():
    disk_dao = _get_disks_dao()
    data = disk_dao.get_drive_letter_to_data()

    # Prepare data for Chart.js
    time_labels = []
    drive_data = []
    drive_letters = list(data.keys())

    # Collect all unique timestamps across all snapshots and sort them from oldest to newest
    for snapshots in data.values():
        for snapshot in snapshots:
            timestamp = snapshot.timestamp.strftime(DATETIME_FORMAT_STRING)
            if timestamp not in time_labels:
                time_labels.append(timestamp)
    time_labels = sorted(time_labels)

    # Create a dictionary to map timestamps to their index for easier lookup
    timestamp_indices: dict[str, int] = {ts: idx for idx, ts in enumerate(time_labels)}

    # Initialize with 0 for all timestamps, then fill in actual values if we have them
    for drive_letter, snapshots in data.items():
        free_space = [0] * len(time_labels)

        # Fill in the actual values we have
        for snapshot in snapshots:
            timestamp = snapshot.timestamp.strftime(DATETIME_FORMAT_STRING)
            if timestamp in timestamp_indices:  # Should always be true, but safe check
                idx = timestamp_indices[timestamp]
                free_space[idx] = snapshot.free_bytes

        drive_data.append(free_space)

    # Sort drive data based on the most recent free space (last value in each list)
    sorted_drive_data = sorted(zip(drive_letters, drive_data), key=lambda x: x[1][-1], reverse=True)
    sorted_drive_letters = [x[0] for x in sorted_drive_data]
    sorted_drive_data = [x[1] for x in sorted_drive_data]

    return render_template(
        "disks/disks_free_space.html",
        time_labels=time_labels,
        drive_data=sorted_drive_data,
        drive_letters=sorted_drive_letters,
    )


@HTML_BLUEPRINT.route("/games")
def games_index():
    return render_template("games/index.html")


@HTML_BLUEPRINT.route("/games/5crowns")
def five_crowns():
    return render_template("games/5crowns.html")


@HTML_BLUEPRINT.route("/games/books-runs")
def books_runs():
    return render_template("games/books_runs.html")


@HTML_BLUEPRINT.route("/birds")
def birds_index():
    bird_dao = _get_birds_dao()
    if bird_dao is None:
        return render_template("birds/not_configured.html")

    life_list = bird_dao.get_life_list()
    return render_template("birds/life_list.html", life_list=life_list, edit_mode=False)


@HTML_BLUEPRINT.route("/birds/edit")
def birds_edit():
    bird_dao = _get_birds_dao()
    if bird_dao is None:
        return render_template("birds/not_configured.html")

    if not session.get("authenticated"):
        return redirect(url_for(
            "routes_html.login",
            next=request.full_path.rstrip("?")
        ))

    life_list = bird_dao.get_life_list()
    return render_template("birds/life_list.html", life_list=life_list, edit_mode=True)


@HTML_BLUEPRINT.route("/birds/add", methods=["GET", "POST"])
def birds_add():
    bird_dao = _get_birds_dao()
    if bird_dao is None:
        return render_template("birds/not_configured.html")

    if request.method == "POST":
        bird_id = request.form.get("bird_id")
        scientific_name = request.form.get("scientific_name")
        common_name = request.form.get("common_name")
        date_sighted = datetime.strptime(request.form.get("date_sighted"), "%Y-%m-%d")
        notes = request.form.get("notes")

        existing_entry = bird_dao.get_life_list_entry_by_bird_id(bird_id)
        if existing_entry:
            return redirect(f"/birds/edit_entry/{existing_entry.id}")

        bird_dao.add_to_life_list(bird_id, scientific_name, common_name, date_sighted, notes)
        return redirect("/birds")

    # Require login first
    if not session.get("authenticated"):
        return redirect(url_for(
            "routes_html.login",
            next=request.full_path.rstrip("?")
        ))

    query = request.args.get("query", "")
    birds = bird_dao.search_birds(query) if query else []
    life_list = bird_dao.get_life_list()
    life_list_by_bird_id = {entry.bird_id: entry for entry in life_list}

    return render_template(
        "birds/add_bird.html",
        birds=birds,
        query=query,
        life_list_by_bird_id=life_list_by_bird_id,
    )


@HTML_BLUEPRINT.route("/birds/near_me")
def birds_near_me():
    bird_dao = _get_birds_dao()
    if bird_dao is None:
        return render_template("birds/not_configured.html")

    if not session.get("authenticated"):
        return redirect(url_for(
            "routes_html.login",
            next=request.full_path.rstrip("?")
        ))

    return render_template("birds/near_me.html")


@HTML_BLUEPRINT.route("/birds/nearby_birds")
def birds_nearby_api():
    bird_dao = _get_birds_dao()
    if bird_dao is None:
        return jsonify({"birds": [], "error": "Database not configured"}), 500

    lat = request.args.get("lat", type=float)
    lng = request.args.get("lng", type=float)
    radius = request.args.get("radius", default=50, type=int)

    if lat is None or lng is None:
        return jsonify({"birds": [], "error": "lat and lng query parameters are required"}), 400

    url = (
        f"https://api.inaturalist.org/v1/observations/species_counts"
        f"?lat={lat}&lng={lng}&radius={radius}&iconic_taxa=Aves"
        f"&quality_grade=research&page=1&per_page=50"
    )

    try:
        resp = requests.get(url, timeout=6)
        if resp.status_code != 200:
            return jsonify({"birds": [], "error": "Failed to fetch nearby observations"}), 502
        inat_data = resp.json()
    except Exception as e:
        LOG.error(f"Error fetching nearby birds from iNaturalist: {e}")
        return jsonify({"birds": [], "error": str(e)}), 500

    results = inat_data.get("results", [])
    if not results:
        return jsonify({"birds": [], "total_results": 0})

    inat_ids = [r["taxon"]["id"] for r in results if r.get("taxon") and r["taxon"].get("id")]
    scientific_names = [r["taxon"]["name"] for r in results if r.get("taxon") and r["taxon"].get("name")]

    db_birds = bird_dao.find_birds_by_inat_ids_or_names(inat_ids, scientific_names)
    db_by_inat_id = {b.inat_id: b for b in db_birds if b.inat_id}
    db_by_sci_name = {b.scientific_name.lower(): b for b in db_birds if b.scientific_name}

    life_list = bird_dao.get_life_list()
    life_list_by_bird_id = {entry.bird_id: entry for entry in life_list if entry.bird_id}
    life_list_by_sci_name = {entry.scientific_name.lower(): entry for entry in life_list if entry.scientific_name}

    output_birds = []
    for item in results:
        taxon = item.get("taxon") or {}
        inat_id = taxon.get("id")
        sci_name = taxon.get("name") or ""
        common_name = taxon.get("preferred_common_name") or sci_name
        count = item.get("count", 0)

        # Match against our database
        db_bird = db_by_inat_id.get(inat_id) or db_by_sci_name.get(sci_name.lower())
        bird_id = db_bird.id if db_bird else None

        # Check life list
        entry = None
        if bird_id and bird_id in life_list_by_bird_id:
            entry = life_list_by_bird_id[bird_id]
        elif sci_name.lower() in life_list_by_sci_name:
            entry = life_list_by_sci_name[sci_name.lower()]

        # Thumbnail URL
        if db_bird and db_bird.thumb_url:
            thumb_url = db_bird.thumb_url
        elif taxon.get("default_photo") and taxon["default_photo"].get("square_url"):
            thumb_url = taxon["default_photo"]["square_url"]
        else:
            thumb_url = None

        output_birds.append({
            "bird_id": bird_id,
            "inat_id": inat_id,
            "common_name": db_bird.common_name if db_bird else common_name,
            "scientific_name": db_bird.scientific_name if db_bird else sci_name,
            "count": count,
            "thumb_url": thumb_url,
            "on_life_list": entry is not None,
            "life_list_entry_id": entry.id if entry else None,
            "date_sighted": entry.date_sighted.strftime("%Y-%m-%d") if entry else None,
        })

    return jsonify({"birds": output_birds, "total_results": inat_data.get("total_results", len(output_birds))})


@HTML_BLUEPRINT.route("/birds/api/add_sighting", methods=["POST"])
def birds_api_add_sighting():
    bird_dao = _get_birds_dao()
    if bird_dao is None:
        return jsonify({"success": False, "error": "Database not configured"}), 500

    data = request.get_json(silent=True) or request.form
    bird_id = data.get("bird_id") or ""
    scientific_name = data.get("scientific_name")
    common_name = data.get("common_name")
    date_sighted_str = data.get("date_sighted")
    notes = data.get("notes") or None

    if not scientific_name or not common_name or not date_sighted_str:
        return jsonify({"success": False, "error": "Missing required fields"}), 400

    try:
        date_sighted = datetime.strptime(date_sighted_str, "%Y-%m-%d")
    except ValueError:
        return jsonify({"success": False, "error": "Invalid date format, expected YYYY-MM-DD"}), 400

    if bird_id:
        existing = bird_dao.get_life_list_entry_by_bird_id(bird_id)
        if existing:
            return jsonify({"success": True, "entry_id": existing.id, "already_existed": True})

    entry_id = bird_dao.add_to_life_list(bird_id, scientific_name, common_name, date_sighted, notes)
    return jsonify({"success": True, "entry_id": entry_id, "already_existed": False})


@HTML_BLUEPRINT.route("/birds/species/<bird_id>")
def birds_species(bird_id):
    bird_dao = _get_birds_dao()
    if bird_dao is None:
        return render_template("birds/not_configured.html")

    bird = bird_dao.get_bird(bird_id)
    if bird is None:
        return redirect("/birds")

    life_list_entry = bird_dao.get_life_list_entry_by_bird_id(bird_id)
    return render_template(
        "birds/species.html",
        bird=bird,
        life_list_entry=life_list_entry,
        carto_api_key=CARTO_API_KEY,
    )


@HTML_BLUEPRINT.route("/birds/delete/<entry_id>", methods=["POST"])
def birds_delete(entry_id):
    bird_dao = _get_birds_dao()
    if bird_dao is not None:
        bird_dao.delete_from_life_list(entry_id)
    return redirect("/birds")


@HTML_BLUEPRINT.route("/birds/edit_entry/<entry_id>", methods=["GET", "POST"])
def birds_edit_entry(entry_id):
    bird_dao = _get_birds_dao()
    if bird_dao is None:
        return redirect("/birds")

    if request.method == "POST":
        date_sighted = datetime.strptime(request.form.get("date_sighted"), "%Y-%m-%d")
        notes = request.form.get("notes")
        bird_dao.update_life_list_entry(entry_id, date_sighted, notes)
        return redirect("/birds")

    entry = bird_dao.get_life_list_entry(entry_id)
    if entry is None:
        return redirect("/birds")

    return render_template("birds/edit_entry.html", entry=entry)


@HTML_BLUEPRINT.route("/birds/search")
def birds_search():
    bird_dao = _get_birds_dao()
    if bird_dao is None:
        return jsonify({"birds": []})

    query = request.args.get("query", "")
    birds = bird_dao.search_birds(query) if query else []

    return jsonify({
        "birds": [
            {
                "id": bird.id,
                "scientific_name": bird.scientific_name,
                "common_name": bird.common_name,
            }
            for bird in birds
        ]
    })


@HTML_BLUEPRINT.route("/books")
def books_index():
    book_dao = _get_books_dao()
    if book_dao is None:
        return render_template("books/not_configured.html")

    books = book_dao.get_all_books()
    return render_template("books/index.html", books=books, edit_mode=False)


@HTML_BLUEPRINT.route("/books/edit")
def books_edit():
    book_dao = _get_books_dao()
    if book_dao is None:
        return render_template("books/not_configured.html")

    if not session.get("authenticated"):
        return redirect(url_for(
            "routes_html.login",
            next=request.full_path.rstrip("?")
        ))

    books = book_dao.get_all_books()
    return render_template("books/index.html", books=books, edit_mode=True)


@HTML_BLUEPRINT.route("/books/<book_id>")
def book_details(book_id):
    book_dao = _get_books_dao()
    if book_dao is None:
        return render_template("books/not_configured.html")

    book = book_dao.get_book(book_id)
    if book is None:
        return redirect("/books")

    return render_template("books/book.html", book=book)


@HTML_BLUEPRINT.route("/books/add", methods=["GET", "POST"])
def books_add():
    book_dao = _get_books_dao()
    if book_dao is None:
        return render_template("books/not_configured.html")

    if request.method == "POST":
        title = request.form.get("title")
        authors_str = request.form.get("authors")
        date_published_str = request.form.get("date_published")
        isbn = request.form.get("isbn")
        oclc_number = request.form.get("oclc_number")
        page_count_str = request.form.get("page_count")
        cover_url = request.form.get("cover_url")

        # Parse authors (comma-separated)
        authors = [a.strip() for a in authors_str.split(",") if a.strip()]

        LOG.info(f"Adding new book: {title}")

        # Parse date published
        date_published = None
        if date_published_str:
            try:
                date_published = datetime.strptime(date_published_str, "%Y-%m-%d")
            except ValueError:
                pass

        # Parse page count
        page_count = None
        if page_count_str:
            try:
                page_count = int(page_count_str)
            except ValueError:
                pass

        # Add the book first
        book_id = book_dao.add_book(
            title=title,
            authors=authors,
            date_published=date_published,
            isbn=isbn,
            oclc_number=oclc_number,
            page_count=page_count,
        )

        # Handle cover image upload
        r2_storage = _get_r2_storage()
        cover_file = request.files.get("cover_image")

        LOG.info(f"Cover file check: cover_file={cover_file}, r2_storage={r2_storage is not None}")
        if cover_file:
            LOG.info(f"Cover file details: filename={cover_file.filename}, content_length={cover_file.content_length}")

        # Priority: uploaded file > cover URL from search
        if cover_file:
            # Process uploaded file (check for filename OR content)
            if r2_storage and (cover_file.filename or cover_file.content_length):
                try:
                    file_bytes = cover_file.read()
                    if file_bytes:
                        LOG.info(f"Processing cover image for new book {book_id}, size: {len(file_bytes)} bytes")
                        _process_and_upload_cover(book_id, file_bytes, book_dao, r2_storage)
                    else:
                        LOG.warning(f"Cover file is empty for new book {book_id}")
                except ImageValidationError as e:
                    LOG.warning(f"Image validation failed for new book {book_id}: {e}")
                    flash(str(e), "danger")
                except RuntimeError as e:
                    LOG.error(f"Cover upload failed for new book {book_id}: {e}")
                    flash(str(e), "danger")
                except Exception as e:
                    LOG.error(f"Unexpected error uploading cover for new book {book_id}: {e}")
                    flash("Failed to upload cover image.", "danger")
            else:
                if not r2_storage:
                    LOG.warning("R2 storage not configured, skipping cover upload")
                elif not cover_file.filename and not cover_file.content_length:
                    LOG.warning(f"Cover file has no filename and no content length for new book {book_id}")
        elif cover_url and r2_storage:
            # Download and process cover from URL
            try:
                image_bytes = download_remote_image(cover_url)
                _process_and_upload_cover(book_id, image_bytes, book_dao, r2_storage)
            except (RemoteImageDownloadError, SSRFValidationError) as e:
                LOG.warning(f"Failed to download cover from URL for new book {book_id}: {e}")
            except (ImageValidationError, RuntimeError) as e:
                LOG.warning(f"Failed to process cover from URL for new book {book_id}: {e}")
            except Exception as e:
                LOG.error(f"Unexpected error processing cover from URL for new book {book_id}: {e}")

        return redirect("/books")

    # Require login for adding books
    if not session.get("authenticated"):
        return redirect(url_for(
            "routes_html.login",
            next=request.full_path.rstrip("?")
        ))

    return render_template("books/add_book.html")


@HTML_BLUEPRINT.route("/books/edit/<book_id>", methods=["GET", "POST"])
def books_edit_book(book_id):
    book_dao = _get_books_dao()
    if book_dao is None:
        return redirect("/books")

    if request.method == "POST":
        title = request.form.get("title")
        authors_str = request.form.get("authors")
        date_published_str = request.form.get("date_published")
        isbn = request.form.get("isbn")
        oclc_number = request.form.get("oclc_number")
        page_count_str = request.form.get("page_count")

        # Parse authors (comma-separated)
        authors = [a.strip() for a in authors_str.split(",") if a.strip()]

        # Parse date published
        date_published = None
        if date_published_str:
            try:
                date_published = datetime.strptime(date_published_str, "%Y-%m-%d")
            except ValueError:
                pass

        # Parse page count
        page_count = None
        if page_count_str:
            try:
                page_count = int(page_count_str)
            except ValueError:
                pass

        book_dao.update_book(
            book_id=book_id,
            title=title,
            authors=authors,
            date_published=date_published,
            isbn=isbn,
            oclc_number=oclc_number,
            page_count=page_count,
        )
        return redirect(f"/books/{book_id}")

    if not session.get("authenticated"):
        return redirect(url_for(
            "routes_html.login",
            next=request.full_path.rstrip("?")
        ))

    book = book_dao.get_book(book_id)
    if book is None:
        return redirect("/books")

    return render_template("books/edit_book.html", book=book)


@HTML_BLUEPRINT.route("/books/<book_id>/cover", methods=["POST"])
def books_upload_cover(book_id):
    if not session.get("authenticated"):
        return redirect(url_for(
            "routes_html.login",
            next=request.full_path.rstrip("?")
        ))

    book_dao = _get_books_dao()
    if book_dao is None:
        flash("Database is not configured.", "danger")
        return redirect("/books")

    book = book_dao.get_book(book_id)
    if book is None:
        flash("Book not found.", "danger")
        return redirect("/books")

    r2_storage = _get_r2_storage()
    if r2_storage is None:
        LOG.error("Cloudflare R2 storage is not configured.")
        flash("Cloudflare R2 storage is not configured.", "danger")
        return redirect(f"/books/edit/{book_id}")

    # Verify an image file was supplied
    file = request.files.get("cover_image") or request.files.get("cover")
    if not file or not file.filename:
        flash("No image file was selected.", "danger")
        return redirect(f"/books/edit/{book_id}")

    # Read file bytes
    try:
        file_bytes = file.read()
        if not file_bytes:
            flash("The uploaded file is empty.", "danger")
            return redirect(f"/books/edit/{book_id}")
    except Exception as e:
        LOG.error(f"Error reading uploaded file for book {book_id}: {e}")
        flash("Failed to read uploaded file.", "danger")
        return redirect(f"/books/edit/{book_id}")

    # Process and upload using shared helper
    try:
        _process_and_upload_cover(book_id, file_bytes, book_dao, r2_storage)
    except ImageValidationError as e:
        LOG.warning(f"Image validation failed for book {book_id}: {e}")
        flash(str(e), "danger")
        return redirect(f"/books/edit/{book_id}")
    except RuntimeError as e:
        LOG.error(f"Cover upload failed for book {book_id}: {e}")
        flash(str(e), "danger")
        return redirect(f"/books/edit/{book_id}")
    except Exception as e:
        LOG.error(f"Unexpected error uploading cover for book {book_id}: {e}")
        flash("Failed to upload cover image.", "danger")
        return redirect(f"/books/edit/{book_id}")

    flash("Cover image uploaded successfully.", "success")
    return redirect(f"/books/edit/{book_id}")


@HTML_BLUEPRINT.route("/books/<book_id>/cover-from-url", methods=["POST"])
def books_upload_cover_from_url(book_id):
    """Upload a book cover by fetching it from a URL (for drag-from-browser-tab)."""
    if not session.get("authenticated"):
        return redirect(url_for(
            "routes_html.login",
            next=request.full_path.rstrip("?")
        ))

    book_dao = _get_books_dao()
    if book_dao is None:
        flash("Database is not configured.", "danger")
        return redirect("/books")

    book = book_dao.get_book(book_id)
    if book is None:
        flash("Book not found.", "danger")
        return redirect("/books")

    r2_storage = _get_r2_storage()
    if r2_storage is None:
        LOG.error("Cloudflare R2 storage is not configured.")
        flash("Cloudflare R2 storage is not configured.", "danger")
        return redirect(f"/books/edit/{book_id}")

    # Get URL from request
    if request.is_json:
        data = request.get_json()
        url = data.get("url") if data else None
    else:
        url = request.form.get("url")

    if not url:
        flash("No URL provided.", "danger")
        return redirect(f"/books/edit/{book_id}")

    # Download remote image with SSRF protection
    try:
        image_bytes = download_remote_image(url)
    except RemoteImageDownloadError as e:
        LOG.warning("Remote image download failed for book %s: %s", book_id, e)
        flash("Failed to download image from the provided URL.", "danger")
        return redirect(f"/books/edit/{book_id}")
    except SSRFValidationError as e:
        LOG.warning("SSRF validation failed for remote cover URL for book %s: %s", book_id, e)
        flash("Invalid or restricted URL.", "danger")
        return redirect(f"/books/edit/{book_id}")

    # Process and upload using shared helper
    try:
        _process_and_upload_cover(book_id, image_bytes, book_dao, r2_storage)
    except ImageValidationError as e:
        LOG.warning("Image validation failed for book %s from URL: %s", book_id, e)
        flash(str(e), "danger")
        return redirect(f"/books/edit/{book_id}")
    except RuntimeError as e:
        LOG.error("Cover upload from URL failed for book %s: %s", book_id, e)
        flash(str(e), "danger")
        return redirect(f"/books/edit/{book_id}")
    except Exception as e:
        LOG.error("Unexpected error uploading cover from URL for book %s: %s", book_id, e)
        flash("Failed to process cover image from URL.", "danger")
        return redirect(f"/books/edit/{book_id}")

    flash("Cover image imported successfully.", "success")
    return redirect(f"/books/edit/{book_id}")


@HTML_BLUEPRINT.route("/books/<book_id>/cover/delete", methods=["POST"])
def books_delete_cover(book_id):
    if not session.get("authenticated"):
        return redirect(url_for(
            "routes_html.login",
            next=request.full_path.rstrip("?")
        ))

    book_dao = _get_books_dao()
    if book_dao is None:
        flash("Database is not configured.", "danger")
        return redirect("/books")

    book = book_dao.get_book(book_id)
    if book is None:
        flash("Book not found.", "danger")
        return redirect("/books")

    r2_storage = _get_r2_storage()
    old_cover_key = book.cover_key

    if old_cover_key:
        if r2_storage:
            try:
                r2_storage.delete_cover_and_thumb(old_cover_key)
            except Exception as e:
                LOG.error(f"Failed to delete cover from R2 for book {book_id}: {e}")

        # Remove cover_key from MongoDB
        book_dao.delete_cover_key(book_id)
        flash("Cover image deleted successfully.", "success")
    else:
        flash("Book does not have a cover image to delete.", "warning")

    return redirect(f"/books/edit/{book_id}")


@HTML_BLUEPRINT.route("/books/delete/<book_id>", methods=["POST"])
def books_delete(book_id):
    book_dao = _get_books_dao()
    if book_dao is not None:
        book = book_dao.get_book(book_id)
        if book and book.cover_key:
            r2_storage = _get_r2_storage()
            if r2_storage:
                try:
                    r2_storage.delete_cover_and_thumb(book.cover_key)
                except Exception as e:
                    LOG.error(f"Failed to delete cover from R2 for book {book_id}: {e}")
        book_dao.delete_book(book_id)
    return redirect("/books")


@HTML_BLUEPRINT.route("/api/book-lookup/")
def book_lookup():
    """API endpoint to lookup book metadata by ISBN using multiple providers."""
    isbn = request.args.get("isbn", "").strip()

    if not isbn:
        return jsonify({"error": "ISBN is required"}), 400

    # Clean ISBN - remove hyphens and spaces
    isbn_clean = isbn.replace("-", "").replace(" ", "")

    if not isbn_clean:
        return jsonify({"error": "Invalid ISBN"}), 400

    try:
        book_dao = _get_books_dao()
        
        # Check cache first
        if book_dao:
            cached_result = book_dao.get_cached_isbn_lookup(isbn_clean)
            if cached_result:
                return jsonify(cached_result)

        # Initialize merger with providers in order of preference
        merger = MetadataMerger()
        merger.add_provider(OpenLibraryProvider(timeout=10))
        merger.add_provider(GoogleBooksProvider(timeout=10))
        merger.add_provider(LibraryOfCongressProvider(timeout=10))
        merger.add_provider(OpenBDProvider(timeout=10))
        merger.add_provider(NDLSearchProvider(timeout=10))

        # Query all providers and merge results
        metadata, provider_status = merger.lookup(isbn_clean)

        # Check if any provider found data
        if not metadata.title and not metadata.authors:
            result = {
                "error": "No matching book found for this ISBN",
                "provider_status": provider_status,
            }
            # Do not cache negative results - allow re-querying later
            return jsonify(result), 404

        # Format date for response
        date_published_str = None
        if metadata.date_published:
            date_published_str = metadata.date_published.strftime("%Y-%m-%d")

        result = {
            "success": True,
            "title": metadata.title,
            "authors": metadata.authors or [],
            "date_published": date_published_str,
            "page_count": metadata.page_count,
            "isbn": metadata.isbn or isbn_clean,
            "publisher": metadata.publisher,
            "description": metadata.description,
            "cover_url": metadata.cover_url,
            "source_providers": metadata.source_providers,
            "provider_status": provider_status,
        }

        # Cache successful result
        if book_dao:
            book_dao.cache_isbn_lookup(isbn_clean, result)

        return jsonify(result)

    except Exception as e:
        LOG.error(f"Error during ISBN lookup: {e}")
        return jsonify({"error": "An error occurred during lookup"}), 500


@HTML_BLUEPRINT.route("/api/book-search/")
def book_search():
    """API endpoint to search for books by keyword using multiple providers."""
    query = request.args.get("q", "").strip()

    if not query:
        return jsonify({"error": "Search query is required"}), 400

    if len(query) < 2:
        return jsonify({"error": "Search query must be at least 2 characters"}), 400

    try:
        book_dao = _get_books_dao()
        
        # Check cache first
        if book_dao:
            cached_result = book_dao.get_cached_book_search(query)
            if cached_result:
                return jsonify({
                    "success": True,
                    "results": cached_result[0],
                    "provider_status": cached_result[1],
                    "cached": True
                })

        # Initialize search merger with providers
        merger = BookSearchMerger()
        merger.add_provider(OpenLibraryProvider(timeout=10))
        merger.add_provider(GoogleBooksProvider(timeout=10))
        merger.add_provider(LibraryOfCongressProvider(timeout=10))
        merger.add_provider(OpenBDProvider(timeout=10))
        merger.add_provider(NDLSearchProvider(timeout=10))

        # Search across all providers
        results, provider_status = merger.search(query, max_results_per_provider=10)

        # Convert SearchResult objects to dicts for JSON response
        results_dicts = []
        for result in results:
            result_dict = {
                "title": result.title,
                "authors": result.authors,
                "publisher": result.publisher,
                "publication_date": result.publication_date.strftime("%Y-%m-%d") if result.publication_date else None,
                "publication_year": result.publication_year,
                "page_count": result.page_count,
                "isbn_10": result.isbn_10,
                "isbn_13": result.isbn_13,
                "description": result.description,
                "edition": result.edition,
                "series": result.series,
                "subjects": result.subjects,
                "language": result.language,
                "cover_url": result.cover_url,
                "provider": result.provider,
                "provider_record_id": result.provider_record_id,
                "source_url": result.source_url
            }
            results_dicts.append(result_dict)

        # Cache successful result
        if book_dao and results_dicts:
            book_dao.cache_book_search(query, results_dicts, provider_status)

        return jsonify({
            "success": True,
            "results": results_dicts,
            "provider_status": provider_status,
            "cached": False
        })

    except Exception as e:
        LOG.error(f"Error during book search: {e}")
        return jsonify({"error": "An error occurred during search"}), 500


def download_remote_image(url: str) -> bytes:
    """
    Download an image from a remote URL with SSRF protection and size limits.
    
    Args:
        url: The URL to download from
        
    Returns:
        The downloaded image bytes
        
    Raises:
        RemoteImageDownloadError: If download fails for any reason
        SSRFValidationError: If URL or redirect fails SSRF validation
    """
    # Validate initial URL
    try:
        validated_url = validate_url_for_ssrf(url)
    except SSRFValidationError as e:
        LOG.warning("SSRF validation failed for remote cover URL: %s", e)
        raise
    
    response = None
    try:
        # Initial request with automatic redirects disabled
        response = requests.get(
            validated_url,
            timeout=REQUEST_TIMEOUT,
            stream=True,
            allow_redirects=False,
        )
        
        # Manual redirect handling with validation
        redirect_count = 0
        max_redirects = 5
        current_url = validated_url

        while response.is_redirect and redirect_count < max_redirects:
            redirect_url = response.headers.get("Location")

            if not redirect_url:
                raise RemoteImageDownloadError("Redirect without Location header")

            response.close()

            redirect_count += 1

            redirect_url = urljoin(current_url, redirect_url)

            LOG.info("Following remote image redirect %d", redirect_count)

            if not validate_redirect_url(redirect_url):
                raise SSRFValidationError("Redirect to restricted address blocked")

            response = requests.get(
                redirect_url,
                timeout=REQUEST_TIMEOUT,
                stream=True,
                allow_redirects=False,
            )
            current_url = redirect_url
            
            if not redirect_url:
                raise RemoteImageDownloadError("Redirect without Location header")
            
            # Always resolve to absolute URL
            redirect_url = urljoin(current_url, redirect_url)
            
            LOG.info("Following remote image redirect %d", redirect_count)
            
            # Validate redirect URL
            if not validate_redirect_url(redirect_url):
                raise SSRFValidationError("Redirect to restricted address blocked")
            
            # Follow redirect
            response = requests.get(
                redirect_url,
                timeout=REQUEST_TIMEOUT,
                stream=True,
                allow_redirects=False,
            )
            current_url = redirect_url
        
        if redirect_count >= max_redirects:
            raise RemoteImageDownloadError("Too many redirects")
        
        response.raise_for_status()
        
        # Optional early Content-Type check
        content_type = response.headers.get("Content-Type", "").lower()
        if content_type and not content_type.startswith("image/"):
            # Only reject obviously non-image types
            if content_type.startswith(("text/", "application/", "video/", "audio/")):
                raise RemoteImageDownloadError(f"Remote server returned non-image content type: {content_type}")
        
        # Safely parse Content-Length for early rejection
        content_length = response.headers.get("Content-Length")
        if content_length:
            try:
                content_length_int = int(content_length)
                if content_length_int > MAX_REMOTE_IMAGE_SIZE:
                    LOG.warning("Remote image too large (Content-Length: %d bytes)", content_length_int)
                    raise RemoteImageDownloadError("Remote image is too large (max 10 MB)")
            except ValueError:
                # Malformed Content-Length header, ignore and rely on streaming limit
                LOG.debug("Malformed Content-Length header, ignoring")
        
        # Stream download with BytesIO and size limit
        buffer = BytesIO()
        
        for chunk in response.iter_content(chunk_size=8192):
            if chunk:
                buffer.write(chunk)
            
            if buffer.tell() > MAX_REMOTE_IMAGE_SIZE:
                LOG.warning("Remote image exceeded size limit during download")
                raise RemoteImageDownloadError("Remote image is too large (max 10 MB)")
        
        image_bytes = buffer.getvalue()
        
        if not image_bytes:
            raise RemoteImageDownloadError("Remote image is empty")
        
        return image_bytes
        
    except requests.exceptions.RequestException as e:
        LOG.error("Failed to download remote image: %s", e)
        raise RemoteImageDownloadError(f"Failed to download image: {e}")
    finally:
        # Ensure response is always closed
        if response is not None:
            response.close()


def _is_safe_redirect_url(url: str) -> bool:
    if not url:
        return False

    parsed = urlparse(url)

    if parsed.scheme or parsed.netloc:
        return False

    return url.startswith("/") and not url.startswith("//")


@HTML_BLUEPRINT.route("/login", methods=["GET", "POST"])
def login():
    admin_password = current_app.config.get("ADMIN_PASSWORD")

    if not admin_password:
        return "Authentication not configured", 500

    if request.method == "POST":
        password = request.form.get("password")

        # Use secrets.compare_digest for secure password comparison
        if password is not None and secrets.compare_digest(password, admin_password):
            session["authenticated"] = True
            session.permanent = True

            # Redirect to the page the user was trying to access if one was stored
            next_url = session.pop("next", None)

            # Validate the redirect URL to prevent open redirect attacks or loops
            if next_url and _is_safe_redirect_url(next_url) and next_url != "/login":
                return redirect(next_url)

            # No valid destination was stored, so go to the site root
            return redirect("/")
        else:
            return render_template("login.html", error="Invalid password")

    return render_template("login.html")


@HTML_BLUEPRINT.route("/logout", methods=["POST"])
def logout():
    session.clear()
    return redirect("/")


def _get_page(days_back: int):
    dao = _get_dao()

    pi_data_set = dao.get_temperature_history(sensor_id="pi", days_back=days_back)
    pidown_data_set = dao.get_temperature_history(sensor_id="pidown", days_back=days_back)
    nsw_data_set = dao.get_temperature_history(sensor_id="KATT", days_back=days_back)

    # Calculate min/max temperatures safely, handling empty data sets
    all_min_temps = [ds.minimum_temp for ds in [pi_data_set, pidown_data_set, nsw_data_set] if ds.minimum_temp != -1]
    all_max_temps = [ds.maximum_temp for ds in [pi_data_set, pidown_data_set, nsw_data_set] if ds.maximum_temp != -1]

    minimum_temp = min(all_min_temps) if all_min_temps else 0
    maximum_temp = max(all_max_temps) if all_max_temps else 100

    return render_template(
        "temperature/temps.html",
        piDataSet=pi_data_set,
        pidownDataSet=pidown_data_set,
        nswDataSet=nsw_data_set,
        minimum_temp=minimum_temp,
        maximum_temp=maximum_temp,
    )


def _get_dao() -> ApplicationDao:
    return current_app.config[DATABASE_CONFIG_KEY]


def _get_beers_dao() -> BeerDao:
    return current_app.config[BEERS_DATABASE_CONFIG_KEY]


def _get_disks_dao() -> DisksDao:
    return current_app.config[DISKS_DATABASE_CONFIG_KEY]


def _get_birds_dao() -> BirdDao | None:
    return current_app.config.get(BIRDS_DATABASE_CONFIG_KEY)


def _get_books_dao() -> BookDao | None:
    return current_app.config.get(BOOKS_DATABASE_CONFIG_KEY)


def _get_r2_storage() -> R2Storage | None:
    return current_app.config.get(R2_CLIENT_CONFIG_KEY)


def _get_cover_url(cover_key: str | None) -> str | None:
    """Get the public URL for a book cover."""
    if not cover_key:
        return None
    r2_storage = _get_r2_storage()
    if r2_storage:
        return r2_storage.get_public_url(cover_key)
    return None


def _get_thumbnail_url(cover_key: str | None) -> str | None:
    """Get the public URL for a book cover thumbnail."""
    if not cover_key:
        return None
    r2_storage = _get_r2_storage()
    if r2_storage:
        return r2_storage.get_thumb_url(cover_key)
    return None


def _process_and_upload_cover(
    book_id: str,
    image_bytes: bytes,
    book_dao: BookDao,
    r2_storage: R2Storage,
) -> bool:
    """
    Process image bytes and upload to R2 as cover images.
    
    Shared helper for both file upload and URL-based import.
    
    Args:
        book_id: The book ID
        image_bytes: Raw image bytes
        book_dao: Book DAO instance
        r2_storage: R2 storage instance
        
    Returns:
        True if successful, False otherwise
    """
    # Process image into AVIF
    try:
        full_bytes, thumb_bytes = process_book_cover(image_bytes)
    except ImageValidationError as e:
        LOG.warning(f"Image validation failed for book {book_id}: {e}")
        raise
    except Exception as e:
        LOG.error(f"Unexpected error processing image for book {book_id}: {e}")
        raise RuntimeError(f"Failed to process cover image: {e}")

    new_cover_key = f"covers/{book_id}.avif"
    new_thumb_key = f"covers/{book_id}_thumb.avif"
    
    # Get current book to check for existing cover
    book = book_dao.get_book(book_id)
    old_cover_key = book.cover_key if book else None

    # Upload to R2 with rollback on failure
    uploaded_keys = []
    try:
        r2_storage.upload_file(new_cover_key, full_bytes, content_type="image/avif")
        uploaded_keys.append(new_cover_key)

        r2_storage.upload_file(new_thumb_key, thumb_bytes, content_type="image/avif")
        uploaded_keys.append(new_thumb_key)
    except Exception as e:
        LOG.error(f"Failed to upload images to R2 for book {book_id}: {e}")
        # Partial upload cleanup
        for key in uploaded_keys:
            try:
                r2_storage.delete_file(key)
            except Exception as cleanup_err:
                LOG.error(f"Error cleaning up R2 key '{key}': {cleanup_err}")
        raise RuntimeError("Failed to upload cover images to Cloudflare R2.")

    # Update MongoDB
    try:
        updated = book_dao.set_cover_key(book_id, new_cover_key)
        if not updated:
            raise RuntimeError(f"Could not update cover_key in MongoDB for book {book_id}")
    except Exception as e:
        LOG.error(f"MongoDB update failed for book {book_id} after R2 upload: {e}")
        # Roll back uploaded R2 objects
        for key in uploaded_keys:
            try:
                r2_storage.delete_file(key)
            except Exception as cleanup_err:
                LOG.error(f"Error cleaning up R2 key '{key}': {cleanup_err}")
        raise RuntimeError("Failed to update book cover in database.")

    # Delete old cover after successful upload
    if old_cover_key and old_cover_key != new_cover_key:
        try:
            r2_storage.delete_cover_and_thumb(old_cover_key)
        except Exception as e:
            LOG.warning(f"Failed to delete previous cover objects for book {book_id}: {e}")

    return True
