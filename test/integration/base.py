import os
import subprocess
import sys
from io import StringIO
from tempfile import TemporaryDirectory
from typing import Tuple, Optional, Union, List

import pytest

from gitflow import __main__
from gitflow.properties import PropertyIO


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
            (key, self.b[key]) for key in (self.b.keys() - self.intersect)
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
            eprint(*["    " + key + ": " + value for key, value in diff.removed().items()], sep='\n')
            eprint("changed:")
            eprint(*["    " + key + ": " + value for key, value in diff.changed().items()], sep='\n')

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

        exit_code = self.git_flow(*args)

        sys.stdout.flush()
        out_lines = stdout_buf.getvalue().splitlines()

        sys.stdout = prev_stdout

        return exit_code, out_lines

    def git(self, *args) -> int:
        proc = subprocess.Popen(args=['git'] + [*args])
        proc.wait()
        return proc.returncode

    def git_for_lines(self, *args) -> List[str]:
        proc = subprocess.Popen(args=args,
                                stdout=subprocess.PIPE)
        out, err = proc.communicate()
        assert proc.returncode == os.EX_OK
        return out.decode('utf-8').splitlines()

    def git_for_line(self, *args) -> str:
        lines = self.git_for_lines(*args)
        assert len(lines) == 1
        return lines[0]

    def git_get_commit_count(self) -> int:
        return int(self.git_for_line('git', 'rev-list', '--all', '--count'))

    def git_get_hash(self, object: str) -> str:
        return self.git_for_line('git', 'rev-parse', object)

    def get_ref_map(self, *args) -> dict:
        lines = self.git_for_lines('git', 'for-each-ref', '--format', '%(refname);%(objectname)', *args)

        result = dict()
        for line in lines:
            entry = line.split(';')
            result[entry[0]] = entry[1]
        return result

    def get_ref_set(self, *args) -> set:
        lines = self.git_for_lines('git', 'for-each-ref', '--format', '%(refname)', *args)
        return set(lines)

    def commit(self, message: str = None) -> str:
        # TODO atomic operation
        if message is None:
            message = "Test Commit #" + str(self.git_get_commit_count())
        exit_code = self.git('commit', '--allow-empty', '-m', message)
        assert exit_code == os.EX_OK
        return self.git_get_hash('HEAD')

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
        lines = self.git_for_lines('git', 'rev-parse', '--revs-only', '--symbolic-full-name', 'HEAD')
        return lines[0]

    def current_head_commit(self):
        lines = self.git_for_lines('git', 'rev-parse', '--revs-only', 'HEAD')
        return lines[0]

    def assert_refs(self,
                    refs: Optional[Union[set, dict]],
                    added: Optional[Union[set, dict]] = None,
                    removed: Optional[Union[set, dict]] = None):

        if isinstance(refs, dict):
            if isinstance(added, set):
                added = dict.fromkeys(added, None)
            if isinstance(removed, set):
                removed = dict.fromkeys(removed, None)

            actual_refs = self.get_ref_map()

            if added is not None and removed is not None:
                if not added.keys().isdisjoint(removed.keys()):
                    raise ValueError('added and removed elements are not disjoint')

            if added is not None:
                if not added.keys().isdisjoint(refs.keys()):
                    raise ValueError('added and refs are not disjoint')
                for refname, objectname in added.items():
                    if objectname is None:
                        objectname = actual_refs.get(refname)
                    else:
                        objectname = actual_refs.get(objectname) or objectname
                    refs[refname] = objectname
            if removed is not None:
                if not removed.keys() <= refs.keys():
                    raise ValueError('refs is not a superset of removed')
                for refname, objectname in removed.items():
                    if objectname is None:
                        objectname = actual_refs.get(refname)
                    else:
                        objectname = actual_refs.get(refname) or objectname
                    old_objectname = refs.pop(refname)

            self.assert_same_pairs(refs, actual_refs)
        else:
            if isinstance(added, dict) or isinstance(removed, dict):
                raise ValueError('cannot operate on a set using dict operands')

            if added is not None and removed is not None:
                if added.intersection(removed):
                    raise ValueError('added and removed elements intersect')

            if added is not None:
                if added.intersection(refs):
                    raise ValueError('added and refs intersect')
                refs.update(added)
            if removed is not None:
                if refs.issuperset(removed):
                    raise ValueError('refs is not a superset of removed')
                refs.difference_update(removed)
            self.assert_same_elements(refs, self.get_ref_set())

    def assert_first_parent(self, object: str, expected_parent: str):
        rev_entry = self.git_for_line('git', 'rev-list', '--parents', '--first-parent', '--max-count=1', object).split(
            ' ')

        expected_parent = self.git_for_line('git', 'rev-parse', expected_parent)
        actual_parent = rev_entry[1] if len(rev_entry) == 2 else None
        assert actual_parent == expected_parent

    def assert_head(self, expected: str):
        current_head = self.current_head()
        assert current_head == expected

    def assert_project_properties_contain(self, expected: dict):
        property_reader = PropertyIO.get_instance_by_filename(self.project_property_file)
        try:
            actual = property_reader.read_file(self.project_property_file)
        except FileNotFoundError:
            actual = dict()

        self.assert_same_pairs(expected, actual)
