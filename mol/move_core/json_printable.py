from dataclasses import fields, is_dataclass
import json

class JsonPrintable:

    def to_json_serializable(self):
        if not is_dataclass(self):
            raise TypeError(f"{type(self)} should implemente to_json_serializable method!")

        if len(fields(self)) == 1 and hasattr(self, 'v0'):
            return JsonPrintable._to_json_obj(self.v0)

        amap = {}
        for field in fields(self):
            obj = getattr(self, field.name)
            amap[field.name] = JsonPrintable._to_json_obj(obj)
        return amap

    @staticmethod
    def _to_json_obj(obj):
        if hasattr(obj, "to_json_serializable"):
            return obj.to_json_serializable()
        elif isinstance(obj, dict):
            return {JsonPrintable._to_str(k): JsonPrintable._to_json_obj(v)\
                    for k, v in obj.items()}
        elif isinstance(obj, list):
            return [JsonPrintable._to_json_obj(x) for x in obj]
        elif isinstance(obj, set):
            return [JsonPrintable._to_json_obj(x) for x in obj]
        else:
            return obj.__str__()

    @staticmethod
    def _to_str(obj, indent=None):
        if hasattr(obj, "to_json"):
            return obj.to_json()
        else:
            return obj.__str__()

    def str(self):
        return self.__class__.__qualname__ + self.to_json(indent=4)

    def __str__(self):
        return self.__class__.__qualname__ + self.to_json(indent=4)

    def __repr__(self):
        return self.__class__.__qualname__ + self.to_json(indent=4)

    def to_json(self, sort_keys=False, indent=4):
        amap = self.to_json_serializable()
        return json.dumps(amap, sort_keys=sort_keys, indent=indent)
