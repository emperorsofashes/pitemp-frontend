import logging
from datetime import datetime

import requests
from flask import Blueprint, current_app, jsonify, make_response, redirect, render_template, request

from application import DISKS_DATABASE_CONFIG_KEY, DisksDao
from application.constants.app_constants import (
    BEERS_DATABASE_CONFIG_KEY,
    BIRDS_DATABASE_CONFIG_KEY,
    DATABASE_CONFIG_KEY,
    DATETIME_FORMAT_STRING,
)
from application.constants.beer_constants import BEER_STYLES_V1, BEER_STYLES_V2, ROWDY_USERNAME
from application.constants.bird_constants import BIRD_IMAGE_HOST, CARTO_API_KEY
from application.data.beer.dao import BeerDao
from application.data.bird.dao import BirdDao
from application.data.temperature.dao import ApplicationDao

LOG = logging.getLogger(__name__)
HTML_BLUEPRINT = Blueprint("routes_html", __name__)
DEFAULT_DAYS_BACK = 7


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

    sort_by = request.args.get("sort_by", "date_added_desc")
    life_list = bird_dao.get_life_list(sort_by=sort_by)
    return render_template("birds/life_list.html", life_list=life_list, edit_mode=False, sort_by=sort_by)


@HTML_BLUEPRINT.route("/birds/edit")
def birds_edit():
    bird_dao = _get_birds_dao()
    if bird_dao is None:
        return render_template("birds/not_configured.html")

    sort_by = request.args.get("sort_by", "date_added_desc")
    life_list = bird_dao.get_life_list(sort_by=sort_by)
    return render_template("birds/life_list.html", life_list=life_list, edit_mode=True, sort_by=sort_by)


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


@HTML_BLUEPRINT.route("/birds/image/<filename>")
def birds_image(filename):
    """Proxy bird images from R2 with caching headers."""
    if not BIRD_IMAGE_HOST:
        return "Image host not configured", 404

    image_url = f"{BIRD_IMAGE_HOST}/{filename}"
    try:
        resp = requests.get(image_url, stream=True)
        if resp.status_code != 200:
            return "Image not found", 404

        response = make_response(resp.content)
        response.mimetype = resp.headers.get("Content-Type", "image/avif")
        response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
        return response
    except Exception as e:
        LOG.error(f"Error fetching image from R2: {e}")
        return "Error fetching image", 500


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
