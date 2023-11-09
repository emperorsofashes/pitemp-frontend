import logging
import os

from flask import Blueprint, current_app, render_template, session, redirect

from application.constants.app_constants import (
    USERS_CONFIG_KEY,
    DATABASE_CONFIG_KEY,
    SESSION_USER_EMAIL_KEY,
    SESSION_USER_NAME_KEY,
    SESSION_USER_ID_KEY,
)
from application.data.dao import ApplicationDao
from application.data.users import Users

LOG = logging.getLogger(__name__)

HTML_BLUEPRINT = Blueprint("routes_html", __name__)

PRODUCT_IMAGE_URL_PREFIX = os.environ.get("PRODUCT_IMAGE_URL_PREFIX")


@HTML_BLUEPRINT.route("/")
def homepage():
    dao = _get_dao()

    categories = dao.get_categories()

    if SESSION_USER_ID_KEY in session:
        user_id = session[SESSION_USER_ID_KEY]
        favorites = _get_users().get_favorites(user_id=user_id)
    else:
        favorites = []

    return render_template("index.html", categories=categories, favorites=favorites)


@HTML_BLUEPRINT.route("/profile")
def profile_page():
    if _is_user_logged_in():
        return render_template("profile.html")
    else:
        return redirect("/login_signup")


@HTML_BLUEPRINT.route("/login_signup")
def login_signup_page():
    return render_template("login_signup.html")


@HTML_BLUEPRINT.route("/price_history/<product_id>")
def price_history_page(product_id: int):
    product_id = int(product_id)

    dao = _get_dao()
    price_history = dao.get_product_price_history(product_id)
    product_display_name = dao.get_product_display_name(product_id)

    if PRODUCT_IMAGE_URL_PREFIX:
        padded_product_id = str(product_id).zfill(9)
        product_image_url = f"{PRODUCT_IMAGE_URL_PREFIX.rstrip('/')}/{padded_product_id}.jpg"
    else:
        product_image_url = None

    if SESSION_USER_ID_KEY in session:
        user_id = session[SESSION_USER_ID_KEY]
        is_favorite = _get_users().is_favorite(user_id, product_id)
    else:
        is_favorite = False

    return render_template(
        "price_history.html",
        product_id=product_id,
        dates=price_history.dates,
        prices=price_history.prices,
        current_price=price_history.current_price,
        minimum_price=price_history.minimum_price,
        maximum_price=price_history.maximum_price,
        minimum_price_date=price_history.minimum_price_date,
        maximum_price_date=price_history.maximum_price_date,
        product_image_url=product_image_url,
        product_display_name=product_display_name,
        is_favorite=is_favorite,
    )


@HTML_BLUEPRINT.route("/products/<search_query>")
def products_page(search_query: str):
    dao = _get_dao()
    products = dao.get_products(search_query)
    num_results = len(products)

    return render_template("products.html", search_query=search_query, products=products, num_results=num_results)


@HTML_BLUEPRINT.route("/category/<category_id>")
def category_page(category_id: int):
    category_id = int(category_id)
    dao = _get_dao()

    display_name = dao.get_category_display_name(category_id)
    products = dao.get_category_products(category_id)
    num_products = len(products)

    return render_template("category.html", display_name=display_name, products=products, num_products=num_products)


@HTML_BLUEPRINT.route("/logout")
def logout_page():
    _logout_user()
    return redirect("/")


@HTML_BLUEPRINT.route("/about")
def about_page():
    dao = _get_dao()

    num_products = dao.get_num_products()
    num_prices = dao.get_num_prices()
    oldest_price_date = dao.get_oldest_price_document_date()
    newest_price_date = dao.get_newest_price_document_date()
    product_with_most_prices = dao.get_product_with_most_price_documents()

    return render_template(
        "about.html",
        num_products=f"{num_products:,}",
        num_prices=f"{num_prices:,}",
        oldest_price_date=oldest_price_date,
        newest_price_date=newest_price_date,
        product_with_most_prices=product_with_most_prices,
    )


def _logout_user():
    if SESSION_USER_ID_KEY in session:
        LOG.info(f"Logging out user {session[SESSION_USER_ID_KEY]}")
        session.pop(SESSION_USER_ID_KEY)
    if SESSION_USER_EMAIL_KEY in session:
        session.pop(SESSION_USER_EMAIL_KEY)
    if SESSION_USER_NAME_KEY in session:
        session.pop(SESSION_USER_NAME_KEY)


def _is_user_logged_in() -> bool:
    id_in_session = SESSION_USER_ID_KEY in session
    email_in_session = SESSION_USER_EMAIL_KEY in session
    name_in_session = SESSION_USER_NAME_KEY in session
    if email_in_session != name_in_session != id_in_session:
        LOG.error("Mismatch between keys in session! Resetting session.")
        _logout_user()
        return False
    else:
        return id_in_session and email_in_session and name_in_session


def _get_dao() -> ApplicationDao:
    return current_app.config[DATABASE_CONFIG_KEY]


def _get_users() -> Users:
    return current_app.config[USERS_CONFIG_KEY]
