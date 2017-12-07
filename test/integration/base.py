import os
import subprocess
import sys
from io import StringIO
from tempfile import TemporaryDirectory
from typing import Tuple

import pytest

from gitflow import __main__
from gitflow.properties import PropertyFile


def eprint(*args, **kwargs):
    print(*args, file=sys.stderr, **kwargs)


class DictDiffer(object):
    """
    Calculate the difference between two dictionaries as:
    (1) items added
    (2) items removed
    (3) keys same in both but changed values
    (4) keys same in both and unchanged values
    """

    def __init__(self, a: dict, b: dict):
        self.a = a
        self.b = b
        self.intersect = set(self.a.keys()).intersection(self.b.keys())

    def has_changed(self) -> bool:
        return self.a != self.b

    def added(self) -> dict:
        return dict(
            (key, self.a[key]) for key in (self.b.keys() - self.intersect)
        )

    def removed(self) -> dict:
        return dict(
            (key, self.a[key]) for key in (self.a.keys() - self.intersect)
        )

    def changed(self) -> dict:
        return dict(
            (key, self.a[key]) for key in self.intersect if self.a[key] != self.b[key]
        )

    def unchanged(self) -> dict:
        return dict(
            (key, self.a[key]) for key in self.intersect if self.a[key] == self.b[key]
        )


class SetDiffer(object):
    """
    Calculate the difference between two sets as:
    (1) items added
    (2) items removed
    """

    def __init__(self, a: set, b: set):
        self.a = a
        self.b = b
        self.intersect = self.a.intersection(self.b)

    def has_changed(self) -> bool:
        return self.b != self.a

    def added(self) -> set:
        return self.b - self.intersect

    def removed(self) -> set:
        return self.a - self.intersect


class TestInTempDir(object):
    tempdir: TemporaryDirectory = None
    orig_cwd: str = None

    def setup_method(self, method):
        self.orig_cwd = os.getcwd()
        self.tempdir = TemporaryDirectory()

        # switch to the working copy
        os.chdir(self.tempdir.name)

    def teardown_method(self, method):
        self.tempdir.cleanup()
        os.chdir(self.orig_cwd)

    def git_flow(self, *args) -> int:
        return __main__.main([__name__, '-B'] + [*args])

    def git_flow_for_lines(self, *args) -> Tuple[int, str]:
        prev_stdout = sys.stdout
        sys.stdout = stdout_buf = StringIO()

        exit_code = __main__.main([__name__, '-B'] + [*args])

        sys.stdout.flush()
        out_lines = stdout_buf.getvalue().splitlines()

        sys.stdout = prev_stdout

        return exit_code, out_lines

    def assert_same_elements(self, expected: set, actual: set):
        diff = SetDiffer(expected, actual)
        if diff.has_changed():
            eprint("extra:")
            eprint(*["    " + value for value in diff.added()], sep='\n')
            eprint("missing:")
            eprint(*["    " + value for value in diff.removed()], sep='\n')

            pytest.fail("Mismatching lists")

    def assert_same_pairs(self, expected: dict, actual: dict):
        diff = DictDiffer(expected, actual)
        if diff.has_changed():
            eprint("extra:")
            eprint(*["    " + key + ": " + value for key, value in diff.added().items()], sep='\n')
            eprint("missing:")
            eprint(*["    " + key + ": " + value for key, value in diff.removed()], sep='\n')
            eprint("changed:")
            eprint(*["    " + key + ": " + value for key, value in diff.changed()], sep='\n')

            pytest.fail("Mismatching dictionaries")


class TestFlowBase(TestInTempDir):
    git_origin: str = None
    git_working_copy: str = None
    project_property_file: str = None

    def setup_method(self, method):
        super().setup_method(self)

        self.git_origin = os.path.join(self.tempdir.name, 'origin.git')
        self.git_working_copy = os.path.join(self.tempdir.name, 'working_copy.git')

        proc = subprocess.Popen(args=['git', 'init', '--bare', self.git_origin])
        proc.wait()
        assert proc.returncode == os.EX_OK
        proc = subprocess.Popen(args=['git', 'clone', self.git_origin, self.git_working_copy])
        proc.wait()
        assert proc.returncode == os.EX_OK
        proc = subprocess.Popen(args=['git', '-C', self.git_working_copy, 'config', 'user.name', 'gitflow'])
        proc.wait()
        assert proc.returncode == os.EX_OK
        proc = subprocess.Popen(args=['git', '-C', self.git_working_copy, 'config', 'user.email', 'gitflow@test.void'])
        proc.wait()
        assert proc.returncode == os.EX_OK
        proc = subprocess.Popen(args=['git', '-C', self.git_working_copy, 'config', 'push.default', 'current'])
        proc.wait()
        assert proc.returncode == os.EX_OK

        # switch to the working copy
        os.chdir(self.git_working_copy)

    def teardown_method(self, method):
        try:
            exit_code = self.git_flow('status')
            assert exit_code == os.EX_OK
        finally:
            super().teardown_method(self)

    def git_flow(self, *args) -> int:
        return __main__.main([__name__, '-B'] + [*args])

    def git_flow_for_lines(self, *args) -> Tuple[int, str]:
        prev_stdout = sys.stdout
        sys.stdout = stdout_buf = StringIO()

        exit_code = __main__.main([__name__, '-B'] + [*args])

        sys.stdout.flush()
        out_lines = stdout_buf.getvalue().splitlines()

        sys.stdout = prev_stdout

        return exit_code, out_lines

    def git(self, *args) -> int:
        proc = subprocess.Popen(args=['git'] + [*args])
        proc.wait()
        return proc.returncode

    def git_get_commit_count(self) -> int:
        proc = subprocess.Popen(args=['git', 'rev-list', '--all', '--count'],
                                stdout=subprocess.PIPE)
        out, err = proc.communicate()
        assert proc.returncode == os.EX_OK
        return int(out.decode('utf-8').splitlines()[0])

    def list_refs(self, *args) -> set:
        proc = subprocess.Popen(args=['git', 'for-each-ref', '--format', '%(refname)'] + [*args],
                                stdout=subprocess.PIPE)
        out, err = proc.communicate()
        assert proc.returncode == os.EX_OK
        return set(out.decode('utf-8').splitlines())

    def commit(self, message: str = None):
        if message is None:
            message = "Test Commit #" + str(self.git_get_commit_count())
        exit_code = self.git('commit', '--allow-empty', '-m', message)
        assert exit_code == os.EX_OK

    def add(self, *files: str):
        exit_code = self.git('add', *files)
        assert exit_code == os.EX_OK

    def push(self, *args):
        exit_code = self.git('push', *args)
        assert exit_code == os.EX_OK

    def checkout(self, branch: str):
        exit_code = self.git('checkout', branch)
        assert exit_code == os.EX_OK

    def current_head(self):
        proc = subprocess.Popen(args=['git', 'rev-parse', '--revs-only', '--symbolic-full-name', 'HEAD'],
                                stdout=subprocess.PIPE)
        out, err = proc.communicate()
        assert proc.returncode == os.EX_OK
        current_head = out.decode('utf-8').splitlines()[0]
        return current_head

    def current_head_commit(self):
        proc = subprocess.Popen(args=['git', 'rev-parse', '--revs-only', 'HEAD'],
                                stdout=subprocess.PIPE)
        out, err = proc.communicate()
        assert proc.returncode == os.EX_OK
        current_head = out.decode('utf-8').splitlines()[0]
        return current_head

    def assert_refs(self, expected: set, actual: set = None):
        if actual is None:
            actual = self.list_refs()
        self.assert_same_elements(expected, actual)

    def assert_head(self, expected: str):
        current_head = self.current_head()
        assert current_head == expected

    def assert_project_properties_contain(self, expected: dict):
        property_reader = PropertyFile.newInstance(self.project_property_file)
        actual = property_reader.load()

        self.assert_same_pairs(expected, actual)
