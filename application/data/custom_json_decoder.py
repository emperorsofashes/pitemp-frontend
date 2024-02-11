import datetime

from application.constants.app_constants import DATETIME_FORMAT_STRING


def decode_json(obj):
    if isinstance(obj, str) and ":" in obj and "-" in obj:
        return datetime.datetime.strptime(obj, DATETIME_FORMAT_STRING)
