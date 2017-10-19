import os
from abc import abstractmethod, ABC
from configparser import ConfigParser

from pyjavaprops.javaproperties import JavaProperties

from gitflow.filesystem import replace_file


class PropertyFile(ABC):
    @abstractmethod
    def load(self) -> dict:
        pass

    @abstractmethod
    def store(self, properties: dict):
        pass

    @classmethod
    def newInstance(cls, property_file: str):
        if property_file.endswith('.properties'):
            return JavaPropertyFile(property_file)
        elif property_file.endswith('.ini'):
            return PythonConfigPropertyFile(property_file)
        else:
            raise RuntimeError('unsupported property file: ' + property_file)


class JavaPropertyFile(PropertyFile):
    __property_file = None

    def __init__(self, property_file):
        self.__property_file = property_file

    def load(self) -> dict:
        java_properties = JavaProperties()
        if os.path.exists(self.__property_file):
            java_properties.load(open(self.__property_file, "r"))
        return java_properties.get_property_dict()

    def store(self, properties: dict):
        java_properties = JavaProperties()
        for key, value in properties.items():
            java_properties.set_property(key, value)
        temp_file = self.__property_file + ".~"
        java_properties.store(open(temp_file, "w"))
        replace_file(temp_file, self.__property_file)


class PythonConfigPropertyFile(PropertyFile):
    __property_file = None

    def __init__(self, property_file):
        self.__property_file = property_file

    def load(self) -> dict:
        config = ConfigParser()
        if os.path.exists(self.__property_file):
            config.read_file(f=open(self.__property_file, 'r'))
        return dict(config.items(section=config.default_section))

    def store(self, properties: dict):
        config = ConfigParser()
        if os.path.exists(self.__property_file):
            config.read_file(f=open(self.__property_file, 'r'))
        for key, value in properties.items():
            config.set(section=config.default_section, option=key, value=value)
        config.write(fp=open(self.__property_file, 'w+'), space_around_delimiters=True)
