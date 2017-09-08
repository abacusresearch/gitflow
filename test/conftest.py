import os

test_root = os.path.dirname(os.path.realpath(__file__))


def is_subdir(path, directory):
    path = os.path.realpath(path)
    directory = os.path.realpath(directory)
    relative = os.path.relpath(path, directory)
    return not relative.startswith(os.pardir + os.sep)


def pytest_collect_file(path, parent):
    if is_subdir(path.strpath, test_root) and path.ext == ".py":
        return parent.Module(path, parent)
