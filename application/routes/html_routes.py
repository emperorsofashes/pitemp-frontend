import logging

from flask import Blueprint, current_app, render_template

from application import DisksDao, DISKS_DATABASE_CONFIG_KEY
from application.constants.app_constants import (
    DATABASE_CONFIG_KEY, BEERS_DATABASE_CONFIG_KEY, DATETIME_FORMAT_STRING,
)
from application.data.beer.dao import BeerDao
from application.data.dao import ApplicationDao

LOG = logging.getLogger(__name__)
HTML_BLUEPRINT = Blueprint("routes_html", __name__)
DEFAULT_DAYS_BACK = 7


@HTML_BLUEPRINT.route("/")
def homepage():
    return render_template("index.html")


@HTML_BLUEPRINT.route("/temp")
def temp_index():
    return render_template("temp_index.html")


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
    beers = _get_beers_dao().get_beers()

    return render_template("beers/beers.html", beers=beers)


@HTML_BLUEPRINT.route("/beers/countries")
def countries_page():
    countries = _get_beers_dao().get_countries()

    return render_template("beers/countries.html", countries=countries)


@HTML_BLUEPRINT.route("/beers/styles")
def styles_page():
    styles = _get_beers_dao().get_styles()

    return render_template("beers/styles.html", styles=styles)


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
    return render_template("disks/snapshot.html", drives=drive_snapshot, total_capacity=total_capacity,
                           total_free=total_free, total_used=total_used, total_percent_used=total_percent_used)


@HTML_BLUEPRINT.route("/disks/overview")
def disks_overview():
    disk_dao = _get_disks_dao()
    data = disk_dao.get_drive_letter_to_data()
    drive_snapshot = {key: values[-1] for key, values in data.items() if values}
    total_capacity = sum(snapshot.capacity_bytes for snapshot in drive_snapshot.values())
    total_free = sum(snapshot.free_bytes for snapshot in drive_snapshot.values())
    total_used = sum(snapshot.used_bytes for snapshot in drive_snapshot.values())
    total_percent_used = (total_used / total_capacity) * 100 if total_capacity > 0 else 0.0
    return render_template("disks/overview.html", drives=drive_snapshot, total_capacity=total_capacity,
                           total_free=total_free, total_used=total_used, total_percent_used=total_percent_used)


@HTML_BLUEPRINT.route("/disks/free_space")
def free_space_graph():
    disk_dao = _get_disks_dao()
    data = disk_dao.get_drive_letter_to_data()

    # Prepare data for Chart.js
    time_labels = []
    drive_data = []
    drive_letters = list(data.keys())

    # Organize time labels and free space data
    for drive_letter, snapshots in data.items():
        free_space = []
        for snapshot in snapshots:
            timestamp = snapshot.timestamp.strftime(DATETIME_FORMAT_STRING)
            if timestamp not in time_labels:
                time_labels.append(timestamp)
            free_space.append(snapshot.free_bytes)
        drive_data.append(free_space)

    # Sort time labels and align data
    time_labels = sorted(time_labels)
    for i, free_space in enumerate(drive_data):
        drive_data[i] = [free_space[time_labels.index(ts)] if ts in time_labels else 0 for ts in time_labels]

    return render_template(
        "disks/disks_free_space.html",
        time_labels=time_labels,
        drive_data=drive_data,
        drive_letters=drive_letters
    )


def _get_page(days_back: int):
    dao = _get_dao()

    pi_data_set = dao.get_temperature_history(sensor_id="pi", days_back=days_back)
    pidown_data_set = dao.get_temperature_history(sensor_id="pidown", days_back=days_back)
    nsw_data_set = dao.get_temperature_history(sensor_id="KATT", days_back=days_back)

    return render_template(
        "temps.html",
        piDataSet=pi_data_set,
        pidownDataSet=pidown_data_set,
        nswDataSet=nsw_data_set,
        minimum_temp=min(pi_data_set.minimum_temp, pidown_data_set.minimum_temp),
        maximum_temp=max(pi_data_set.maximum_temp, pidown_data_set.maximum_temp),
    )


def _get_dao() -> ApplicationDao:
    return current_app.config[DATABASE_CONFIG_KEY]


def _get_beers_dao() -> BeerDao:
    return current_app.config[BEERS_DATABASE_CONFIG_KEY]


def _get_disks_dao() -> DisksDao:
    return current_app.config[DISKS_DATABASE_CONFIG_KEY]
