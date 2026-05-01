global CONFIG_MAPPING
CONFIG_MAPPING = {}


from pathlib import Path


# temp_folder =
avica_data_dir  =   str(Path().home() / ".avica")


class BaseConfig(type):
    def __new__(mcs, name, bases, attrs):
        def get_data(self):
            data_map = {}
            combined_attrs = {**type(self).__dict__, **self.__dict__}
            for _key, _value in combined_attrs.items():
                if not _key.startswith('_') and _key != 'data':
                    if _key in CONFIG_MAPPING: _key = CONFIG_MAPPING[_key]
                    data_map[_key] = _value
            return data_map
        attrs['data'] = property(get_data)
        return super().__new__(mcs, name, bases, attrs)


class Config(metaclass=BaseConfig):
    def __init__(self, **kwargs):
        for key, value in kwargs.items():
            setattr(self, key, value)
