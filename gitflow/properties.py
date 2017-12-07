import os
from abc import abstractmethod, ABC
from configparser import ConfigParser

from pyjavaprops.javaproperties import JavaProperties

from gitflow.filesystem import replace_file


class PropertyReader(ABC):
    __java_property_reader = None
    __python_config_property_reader = None

    @abstractmethod
    def load(self, property_file: str) -> dict:
        pass

    @abstractmethod
    def store(self, property_file: str, properties: dict):
        pass

    @classmethod
    def get_instance_by_filename(cls, file_name: str):
        if file_name.endswith('.properties'):
            if cls.__java_property_reader is None:
                cls.__java_property_reader = JavaPropertyReader()
            return cls.__java_property_reader
        elif file_name.endswith('.ini'):
            if cls.__python_config_property_reader is None:
                cls.__python_config_property_reader = PythonConfigPropertyReader()
            return cls.__python_config_property_reader
        else:
            raise RuntimeError('unsupported property file: ' + file_name)


class JavaPropertyReader(PropertyReader):
    def load(self, property_file: str) -> dict:
        java_properties = JavaProperties()
        if os.path.exists(property_file):
            java_properties.load(open(property_file, "r"))
        return java_properties.get_property_dict()

    def store(self, property_file: str, properties: dict):
        java_properties = JavaProperties()
        for key, value in properties.items():
            java_properties.set_property(key, value)
        temp_file = property_file + ".~"
        java_properties.store(open(temp_file, "w"))
        replace_file(temp_file, property_file)


class PythonConfigPropertyReader(PropertyReader):
    def load(self, property_file: str) -> dict:
        config = ConfigParser()
        if os.path.exists(property_file):
            config.read_file(f=open(property_file, 'r'))
        return dict(config.items(section=config.default_section))

    def store(self, property_file: str, properties: dict):
        config = ConfigParser()
        if os.path.exists(property_file):
            config.read_file(f=open(property_file, 'r'))
        for key, value in properties.items():
            config.set(section=config.default_section, option=key, value=value)
        config.write(fp=open(property_file, 'w+'), space_around_delimiters=True)
