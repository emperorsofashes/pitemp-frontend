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

    pi_data_set = dao.get_temperature_history(sensor_id="pi", days_back=7)

    return render_template(
        "index.html",
        piDataSet=pi_data_set,
        current_temp=pi_data_set.current_temp,
        minimum_temp=pi_data_set.minimum_temp,
        maximum_temp=pi_data_set.maximum_temp,
    )


@HTML_BLUEPRINT.route("/<int:days_back>")
def days_page(days_back: int):
    dao = _get_dao()

    pi_data_set = dao.get_temperature_history(sensor_id="pi", days_back=days_back)

    return render_template(
        "index.html",
        piDataSet=pi_data_set,
        current_temp=pi_data_set.current_temp,
        minimum_temp=pi_data_set.minimum_temp,
        maximum_temp=pi_data_set.maximum_temp,
    )


def _get_dao() -> ApplicationDao:
    return current_app.config[DATABASE_CONFIG_KEY]
