import dataclasses
from datetime import datetime, date
from json import JSONEncoder

from bson import ObjectId

from application.constants import DATETIME_FORMAT_STRING


class CustomJsonEncoder(JSONEncoder):
    def default(self, obj):
        if isinstance(obj, ObjectId):
            return str(obj)
        elif dataclasses.is_dataclass(obj):
            return dataclasses.asdict(obj)
        elif isinstance(obj, (datetime, date)):
            return obj.strftime(DATETIME_FORMAT_STRING)
        return JSONEncoder.default(self, obj)
