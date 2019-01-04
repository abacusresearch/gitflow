import io
import json
import os
from abc import abstractmethod, ABC
from configparser import ConfigParser

import yaml

from gitflow.java_properties import JavaProperties


class PropertyIO(ABC):
    __reader_instances: dict = dict()

    @abstractmethod
    def from_stream(self, stream: io.TextIOBase) -> dict:
        pass

    @abstractmethod
    def to_stream(self, stream: io.TextIOBase, properties: dict):
        pass

    def from_file(self, property_file: str) -> dict:
        with open(property_file, mode='r', encoding='utf-8') as input_stream:
            return self.from_stream(input_stream)

    def to_file(self, property_file: str, properties: dict):
        with open(property_file, mode='w', encoding='utf-8') as output_stream:
            return self.to_stream(output_stream, properties)

    def from_str(self, string: str) -> dict:
        with io.StringIO(string) as input_stream:
            return self.from_stream(input_stream)

    def to_str(self, properties: dict) -> str:
        with io.StringIO() as output_stream:
            self.to_stream(output_stream, properties)
            return output_stream.getvalue()

    def from_bytes(self, string: bytes, encoding: str) -> dict:
        return self.from_str(str(string, encoding))

    def to_bytes(self, properties: dict, encoding: str) -> bytes:
        return self.to_str(properties).encode(encoding)

    @classmethod
    def write_file(cls, file_path: str, properties: dict):
        PropertyIO.get_instance_by_filename(file_path).to_file(file_path, properties)

    @classmethod
    def get_instance_by_filename(cls, file_name: str):
        name, extension = os.path.splitext(file_name)
        reader = cls.__reader_instances.get(extension, None)

        if reader is not None:
            return reader

        if extension == '.properties':
            reader = JavaPropertyIO()
        elif extension == '.yml':
            reader = YAMLPropertyIO()
        elif extension == '.json':
            reader = JSONPropertyIO()
        elif extension == '.ini':
            reader = PythonConfigPropertyIO()
        else:
            raise RuntimeError('unsupported property file: ' + file_name)

        cls.__reader_instances[extension] = reader
        return reader


class JavaPropertyIO(PropertyIO):
    def from_stream(self, stream: io.TextIOBase) -> dict:
        java_properties = JavaProperties()
        java_properties.load(stream)
        return java_properties.get_property_dict()

    def to_stream(self, stream: io.TextIOBase, properties: dict):
        java_properties = JavaProperties()
        for key, value in properties.items():
            java_properties.set_property(key, value)
        java_properties.store(stream)


class YAMLPropertyIO(PropertyIO):
    def from_stream(self, stream: io.TextIOBase) -> dict:
        return yaml.safe_load(stream) or dict()

    def to_stream(self, stream: io.TextIOBase, properties: dict):
        yaml.safe_dump(properties, stream, default_flow_style=False)


class JSONPropertyIO(PropertyIO):
    def from_stream(self, stream: io.TextIOBase) -> dict:
        return json.load(stream)

    def to_stream(self, stream: io.TextIOBase, properties: dict):
        json.dump(properties, stream)

    def from_str(self, string: str) -> dict:
        return super().from_str(string) if len(string) else dict()


class PythonConfigPropertyIO(PropertyIO):
    def from_stream(self, stream: io.TextIOBase) -> dict:
        config = ConfigParser()
        config.read_file(stream)
        return dict(config.items(section=config.default_section))

    def to_stream(self, stream: io.TextIOBase, properties: dict):
        config = ConfigParser()
        for key, value in properties.items():
            config.set(section=config.default_section, option=key, value=value)
        config.write(stream)
