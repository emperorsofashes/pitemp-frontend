import dataclasses
from json import JSONEncoder

from bson import ObjectId


class CustomJsonEncoder(JSONEncoder):
    def default(self, obj):
        if isinstance(obj, ObjectId):
            return str(obj)
        elif dataclasses.is_dataclass(obj):
            return dataclasses.asdict(obj)
        return JSONEncoder.default(self, obj)
