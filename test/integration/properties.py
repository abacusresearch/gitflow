import os
from tempfile import TemporaryDirectory

from gitflow.properties import PropertyIO


class TestLoadStore(object):
    tempdir: TemporaryDirectory = None
    orig_cwd: str = None

    def setup_method(self, method):
        self.tempdir = TemporaryDirectory()
        self.orig_cwd = os.getcwd()
        os.chdir(self.tempdir.name)

    def teardown_method(self, method):
        self.tempdir.cleanup()
        os.chdir(self.orig_cwd)

    def test_java_properties(self):
        self.__test_load_store('test.properties')

    def test_java_properties_string(self):
        self.__test_load_store_string('test.properties')

    def test_java_properties_bytes(self):
        self.__test_load_store_bytes('test.properties')

    def test_ini(self):
        self.__test_load_store('test.ini')

    def test_ini_string(self):
        self.__test_load_store_string('test.ini')

    def test_ini_bytes(self):
        self.__test_load_store_bytes('test.ini')

    def __test_load_store(self, file_name: str):
        property_file: PropertyIO = PropertyIO.get_instance_by_filename(file_name)
        properties = dict()

        properties['bla'] = 'blub'
        property_file.write_file(file_name, properties)

        print('---------- FILE CONTENTS ----------')
        with open(file_name, 'r') as file:
            print(file.read())
        print('-----------------------------------')

        stored_properties = property_file.read_file(file_name)

        assert properties == stored_properties

    def __test_load_store_string(self, file_name: str):
        property_file: PropertyIO = PropertyIO.get_instance_by_filename(file_name)
        properties = property_file.from_str("")

        assert len(properties) == 0

        properties['bla'] = 'blub'
        written_string = property_file.to_str(properties)

        print('---------- FILE CONTENTS ----------')
        print(written_string)
        print('-----------------------------------')

        stored_properties = property_file.from_str(written_string)

        assert properties == stored_properties

    def __test_load_store_bytes(self, file_name: str):
        property_file: PropertyIO = PropertyIO.get_instance_by_filename(file_name)
        properties = property_file.from_bytes(bytes(), 'UTF-8')

        assert len(properties) == 0

        properties['bla'] = 'blub'
        written_bytes = property_file.to_bytes(properties, 'UTF-8')

        print('---------- FILE CONTENTS ----------')
        print(str(written_bytes, 'UTF-8'))
        print('-----------------------------------')

        stored_properties = property_file.from_bytes(written_bytes, 'UTF-8')

        assert properties == stored_properties
