import logging

from flask import Blueprint, current_app, render_template

from application.constants.app_constants import (
    DATABASE_CONFIG_KEY,
)
from application.data.dao import ApplicationDao

LOG = logging.getLogger(__name__)
HTML_BLUEPRINT = Blueprint("routes_html", __name__)
DEFAULT_DAYS_BACK = 7


@HTML_BLUEPRINT.route("/")
def homepage():
    return _get_page(DEFAULT_DAYS_BACK)


@HTML_BLUEPRINT.route("/<int:days_back>")
def days_page(days_back: int):
    return _get_page(days_back)


def _get_page(days_back: int):
    dao = _get_dao()

    pi_data_set = dao.get_temperature_history(sensor_id="pi", days_back=days_back)
    pidown_data_set = dao.get_temperature_history(sensor_id="pidown", days_back=days_back)
    nsw_data_set = dao.get_temperature_history(sensor_id="KATT", days_back=days_back)

    return render_template(
        "index.html",
        piDataSet=pi_data_set,
        pidownDataSet=pidown_data_set,
        nswDataSet=nsw_data_set,
        minimum_temp=min(pi_data_set.minimum_temp, pidown_data_set.minimum_temp),
        maximum_temp=max(pi_data_set.maximum_temp, pidown_data_set.maximum_temp),
    )


def _get_dao() -> ApplicationDao:
    return current_app.config[DATABASE_CONFIG_KEY]
