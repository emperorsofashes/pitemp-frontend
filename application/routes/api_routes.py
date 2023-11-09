import logging

from flask import Blueprint, current_app, redirect, request, flash, session
from flask_accept import accept

from application.constants.app_constants import (
    USERS_CONFIG_KEY,
    SESSION_USER_NAME_KEY,
    SESSION_USER_EMAIL_KEY,
    SESSION_USER_ID_KEY,
)
from application.data.users import Users

LOG = logging.getLogger(__name__)

API_BLUEPRINT = Blueprint("routes_api", __name__, url_prefix="/api/v1/")


@API_BLUEPRINT.route("/signup", methods=["POST"])
@accept("application/x-www-form-urlencoded", "multipart/form-data", "text/html")
def signup_api():
    user_name = None
    user_email = None
    password = None

    if request.form:
        user_name = request.form.get("user_name", None)
        user_email = request.form.get("user_email", None)
        password = request.form.get("password1", None)

    if (user_name is None) or (user_email is None) or (password is None):
        flash("Did not supply necessary information!")
        return redirect("/login_signup")
    else:
        try:
            user_id = _get_users().create_user(user_name, user_email, password)
            session[SESSION_USER_ID_KEY] = user_id
            session[SESSION_USER_EMAIL_KEY] = user_email
            session[SESSION_USER_NAME_KEY] = user_name
            return redirect("/")
        except ValueError as e:
            flash(str(e))
            return redirect("/login_signup")


@API_BLUEPRINT.route("/login", methods=["POST"])
@accept("application/x-www-form-urlencoded", "multipart/form-data", "text/html")
def login_api():
    user_email = None
    password = None
    if request.form:
        user_email = request.form.get("user_email", None)
        password = request.form.get("password", None)

    if (user_email is None) or (password is None):
        return "Did not supply user name and password!", 400
    else:
        users = _get_users()
        user_id = users.user_auth(user_email, password)
        if user_id:
            LOG.info(f"User {user_id} has logged in")
            session[SESSION_USER_ID_KEY] = user_id
            session[SESSION_USER_EMAIL_KEY] = user_email
            session[SESSION_USER_NAME_KEY] = users.get_user_name(user_email)
            return redirect("/")
        else:
            flash("User email or password is incorrect!")
            return redirect("/login_signup")


@API_BLUEPRINT.route("/toggle_favorite/<product_id>", methods=["POST"])
def toggle_favorite(product_id: int):
    product_id = int(product_id)

    if SESSION_USER_ID_KEY in session:
        user_id = session[SESSION_USER_ID_KEY]
    else:
        raise ValueError("Cannot favorite an item if not logged in!")

    is_favorite = _get_users().toggle_favorite(user_id=user_id, product_id=product_id)
    LOG.info(f"Toggled favorite status of product {product_id} for user {user_id}")
    return {"is_favorite": is_favorite}, 201


def _get_users() -> Users:
    return current_app.config[USERS_CONFIG_KEY]
