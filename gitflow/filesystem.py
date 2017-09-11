import os

import appdirs
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


def __get_or_create_dir(parent: str, name: str, mode: int = 0o700):
    from stat import S_ISDIR, S_IMODE

    path = os.path.join(parent, name)
    path = os.path.abspath(path)

    create = True

    try:
        stat = os.stat(path)
        if not S_ISDIR(stat.st_mode):
            raise Exception('Not a directory: ' + repr(path))
        elif S_IMODE(stat.st_mode) != mode:
            os.chmod(path=path, mode=mode)
        else:
            create = False
    except FileNotFoundError:
        pass

    if create:
        os.makedirs(path, 0o700, True)

    return path


def get_cache_dir(name: str):
    cache_parent_dir = appdirs.user_cache_dir(appname=const.NAME, appauthor=const.AUTHOR, version=const.VERSION)

    return __get_or_create_dir(cache_parent_dir, name, 0o700)
