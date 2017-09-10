import os

from pyjavaprops.javaproperties import JavaProperties

from gitflow import const


class JavaPropertyFile(object):
    __property_file = None

    def __init__(self, property_file):
        self.__property_file = property_file

    def load(self):
        java_properties = JavaProperties()
        if os.path.exists(self.__property_file):
            java_properties.load(open(self.__property_file, "r"))
        return java_properties.get_property_dict()

    def store(self, properties):
        java_properties = JavaProperties()
        for key, value in properties.items():
            java_properties.set_property(key, value)
        temp_file = self.__property_file + ".~"
        java_properties.store(open(temp_file, "w"))
        replace_file(temp_file, self.__property_file)


def replace_file(src, dst):
    if const.OS_IS_POSIX:
        os.rename(src, dst)
    else:
        os.remove(dst)
        os.rename(src, dst)
