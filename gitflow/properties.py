import io
from abc import abstractmethod, ABC
from configparser import ConfigParser

from gitflow.java_properties import JavaProperties


class PropertyIO(ABC):
    __java_property_reader = None
    __python_config_property_reader = None

    @abstractmethod
    def from_stream(self, stream: io.TextIOBase) -> dict:
        pass

    @abstractmethod
    def to_stream(self, stream: io.TextIOBase, properties: dict):
        pass

    def read_file(self, property_file: str) -> dict:
        with open(property_file, "r") as input_stream:
            return self.from_stream(input_stream)

    def write_file(self, property_file: str, properties: dict):
        with open(property_file, "w") as output_stream:
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
    def get_instance_by_filename(cls, file_name: str):
        if file_name.endswith('.properties'):
            if cls.__java_property_reader is None:
                cls.__java_property_reader = JavaPropertyIO()
            return cls.__java_property_reader
        elif file_name.endswith('.ini'):
            if cls.__python_config_property_reader is None:
                cls.__python_config_property_reader = PythonConfigPropertyIO()
            return cls.__python_config_property_reader
        else:
            raise RuntimeError('unsupported property file: ' + file_name)


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
