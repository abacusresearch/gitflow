import os
import shutil

import appdirs

from gitflow import const


def replace_file(src, dst):
    if const.OS_IS_POSIX:
        os.rename(src, dst)
    else:
        os.remove(dst)
        os.rename(src, dst)


def __get_or_create_dir(parent: str, name: str, mode: int = 0o700) -> str:
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


def get_cache_root_dir() -> str:
    cache_parent_dir = appdirs.user_cache_dir(appname=const.NAME, appauthor=const.AUTHOR, version=const.VERSION)
    return cache_parent_dir


def delete_all_cache_dirs():
    cache_parent_dir = get_cache_root_dir()
    if os.path.isdir(cache_parent_dir):
        shutil.rmtree(path=cache_parent_dir)


def get_cache_dir(name: str):
    cache_parent_dir = get_cache_root_dir()
    return __get_or_create_dir(cache_parent_dir, name, 0o700)


build_tools_cache_dir = get_cache_dir('build-tools')
