import logging
import os

from flask import Blueprint, current_app, render_template

from application.constants.app_constants import (
    DATABASE_CONFIG_KEY,
)
from application.data.dao import ApplicationDao

LOG = logging.getLogger(__name__)

HTML_BLUEPRINT = Blueprint("routes_html", __name__)

PRODUCT_IMAGE_URL_PREFIX = os.environ.get("PRODUCT_IMAGE_URL_PREFIX")


@HTML_BLUEPRINT.route("/")
def homepage():
    dao = _get_dao()

    temp_history = dao.get_temperature_history(days_back=7)

    return render_template(
        "index.html",
        dates=temp_history.dates,
        temperatures=temp_history.temperatures,
        current_temp=temp_history.current_temp,
        minimum_temp=temp_history.minimum_temp,
        maximum_temp=temp_history.maximum_temp,
        minimum_temp_date=temp_history.minimum_temp_date,
        maximum_temp_date=temp_history.maximum_temp_date,
    )


@HTML_BLUEPRINT.route("/<int:days_back>")
def days_page(days_back: int):
    dao = _get_dao()

    temp_history = dao.get_temperature_history(days_back=days_back)

    return render_template(
        "index.html",
        dates=temp_history.dates,
        temperatures=temp_history.temperatures,
        current_temp=temp_history.current_temp,
        minimum_temp=temp_history.minimum_temp,
        maximum_temp=temp_history.maximum_temp,
        minimum_temp_date=temp_history.minimum_temp_date,
        maximum_temp_date=temp_history.maximum_temp_date,
    )


def _get_dao() -> ApplicationDao:
    return current_app.config[DATABASE_CONFIG_KEY]
