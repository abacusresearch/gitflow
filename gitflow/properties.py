import os
from abc import abstractmethod, ABC

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
