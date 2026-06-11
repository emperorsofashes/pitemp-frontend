import logging

from flask import Blueprint, current_app, render_template, request, jsonify

from application import DisksDao, DISKS_DATABASE_CONFIG_KEY
from application.constants.app_constants import (
    DATABASE_CONFIG_KEY,
    BEERS_DATABASE_CONFIG_KEY,
    DATETIME_FORMAT_STRING,
)
from application.constants.beer_constants import ROWDY_USERNAME, BEER_STYLES_V1, BEER_STYLES_V2
from application.data.beer.dao import BeerDao
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
