import os
import subprocess
import sys
from io import StringIO
from tempfile import TemporaryDirectory
from typing import Tuple

import pytest

from gitflow import __main__
from gitflow.filesystem import JavaPropertyFile


class TestFlowBase(object):
    tempdir: TemporaryDirectory
    orig_cwd: str
    git_origin: str
    git_working_copy: str
    project_property_file: str

    def setup_method(self, method):
        self.orig_cwd = os.getcwd()
        self.tempdir = TemporaryDirectory()

        self.git_origin = os.path.join(self.tempdir.name, 'origin.git')
        self.git_working_copy = os.path.join(self.tempdir.name, 'working_copy.git')

        proc = subprocess.Popen(args=['git', 'init', '--bare', self.git_origin])
        proc.wait()
        assert proc.returncode == os.EX_OK
        proc = subprocess.Popen(args=['git', 'clone', self.git_origin, self.git_working_copy])
        proc.wait()
        assert proc.returncode == os.EX_OK

        # switch to the working copy
        os.chdir(self.git_working_copy)

    def teardown_method(self, method):
        exit_code = self.git_flow('status')
        assert exit_code == os.EX_OK

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

    def list_refs(self, *args) -> list:
        proc = subprocess.Popen(args=['git', 'for-each-ref', '--format', '%(refname)'] + [*args],
                                stdout=subprocess.PIPE)
        out, err = proc.communicate()
        assert proc.returncode == os.EX_OK
        return out.decode('utf-8').splitlines()

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

    def assert_same_elements(self, expected: list, actual: list):
        expected = sorted(expected)
        actual = sorted(actual)
        if expected != actual:
            pytest.fail("Comparison assertion failed")

    def assert_refs(self, expected: list, actual: list = None):
        if actual is None:
            actual = self.list_refs()
        self.assert_same_elements(expected, actual)

    def assert_head(self, expected: str):
        current_head = self.current_head()
        assert current_head == expected

    def assert_project_properties_contain(self, expected: dict):
        property_reader = JavaPropertyFile(self.project_property_file)
        actual = property_reader.load()
        assert all(property_entry in actual.items() for property_entry in expected.items())
