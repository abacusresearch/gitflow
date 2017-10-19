import os
from tempfile import TemporaryDirectory

import pytest

from gitflow.properties import PropertyFile


@pytest.mark.slow
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

    def test_ini_file(self):
        self.__test_load_store('test.ini')

    def __test_load_store(self, file_name: str):
        property_file: PropertyFile = PropertyFile.newInstance(file_name)
        properties = property_file.load()

        assert len(properties) == 0

        properties['bla'] = 'blub'
        property_file.store(properties)

        print('---------- FILE CONTENTS ----------')
        with open(file_name, 'r') as file:
            print(file.read())
        print('-----------------------------------')

        stored_properties = property_file.load()

        assert stored_properties == properties
