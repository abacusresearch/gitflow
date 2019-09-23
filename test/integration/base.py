import os
import subprocess
import sys
from io import StringIO
from tempfile import TemporaryDirectory
from typing import Tuple, Optional, Union, List, Callable

from gitflow import __main__
from gitflow.properties import PropertyIO

git_flow_test_installed = os.environ.get('GIT_FLOW_TEST_INSTALLED')
if git_flow_test_installed is not None:
    git_flow_test_installed = int(git_flow_test_installed) != 0
else:
    git_flow_test_installed = False


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

    def __init__(self, a: dict, b: dict, value_matcher: Optional[Callable] = None):
        self.a = a
        self.b = b
        self.value_matcher = value_matcher if value_matcher is not None else lambda a, b: a is None or a == b
        self.intersect = set(self.a.keys()).intersection(self.b.keys())

    def has_changed(self) -> bool:
        return len(self.changed()) != 0

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
            (key, (self.a[key], self.b[key])) for key in self.intersect if not self.value_matcher(self.a[key], self.b[key])
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
        args_ = ['-B'] + [*args]

        if git_flow_test_installed:
            # git_flow_binary = shutil.which('git-flow')
            # proc = subprocess.Popen(args=[git_flow_binary, '-B'] + [*args])
            # return proc.wait()
            proc = subprocess.Popen(args=['git-flow'] + [*args_], stdout=subprocess.PIPE, stderr=subprocess.PIPE, cwd=os.getcwd())
            out, err = proc.communicate()
            print(out.decode("utf-8"))
            eprint(err.decode("utf-8"))
            return proc.returncode
        else:
            return __main__.main([__name__] + [*args_])

    def git_flow_for_lines(self, *args) -> Tuple[int, str]:
        prev_stdout = sys.stdout
        sys.stdout = stdout_buf = StringIO()

        exit_code = self.git_flow(*args)

        sys.stdout.flush()
        out_lines = stdout_buf.getvalue().splitlines()
        while len(out_lines) and len(out_lines[-1]) == 0:
            del out_lines[-1]

        sys.stdout = prev_stdout

        return exit_code, out_lines

    def assert_same_elements(self, expected: set, actual: set):
        diff = SetDiffer(expected, actual)
        if diff.has_changed():
            eprint("extra:")
            eprint(*["    " + value for value in diff.added()], sep='\n')
            eprint("missing:")
            eprint(*["    " + value for value in diff.removed()], sep='\n')

            assert False, "Mismatching lists"

    def assert_same_pairs(self, expected: dict, actual: dict, value_matcher: Callable = None):
        diff = DictDiffer(expected, actual, value_matcher)
        if diff.has_changed():
            eprint("extra:")
            eprint(*["    " + key + ": " + repr(value) for key, value in diff.added().items()], sep='\n')
            eprint("missing:")
            eprint(*["    " + key + ": " + repr(value) for key, value in diff.removed().items()], sep='\n')
            eprint("changed:")
            eprint(*["    " + key + ": " + repr(values[0]) + ", was " + repr(values[1]) for key, values in diff.changed().items()], sep='\n')

            assert False, "Mismatching dictionaries"


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

    @staticmethod
    def match_pattern(pattern, value):
        if isinstance(pattern, list):
            return int(value) >= int(pattern[0]) and int(value) <= int(pattern[1])
        elif isinstance(pattern, str):
            return value == pattern
        elif isinstance(pattern, Callable):
            return pattern(value)
        else:
            raise RuntimeError("illegal argument: pattern type is not supported: " + type(pattern))

    def assert_refs(self,
                    refs: Union[set, dict],
                    updated: Optional[Union[set, dict]] = None,
                    added: Optional[Union[set, dict]] = None,
                    removed: Optional[Union[set, dict]] = None,
                    key_matcher: Callable = None,
                    value_matcher: Callable = None) -> List[str]:

        """
        :return: added refs ordered as specified in 'added'
        """

        matched_refs = []

        if isinstance(refs, set):
            refs = dict.fromkeys(refs, None)
        if isinstance(updated, set):
            updated = dict.fromkeys(updated, None)
        if isinstance(added, set):
            added = dict.fromkeys(added, None)
        if isinstance(removed, set):
            removed = dict.fromkeys(removed, None)

        actual_refs = self.get_ref_map()

        if added is not None and removed is not None:
            if not added.keys().isdisjoint(removed.keys()):
                raise ValueError('added and removed elements are not disjoint')

        if updated is not None:
            if not frozenset(updated.keys()).issubset(frozenset(refs.keys())):
                raise ValueError('updated is not a subset of refs')
            for refname, objectname in updated.items():
                if objectname is None:
                    objectname = actual_refs.get(refname)
                else:
                    objectname = actual_refs.get(objectname) or objectname
                refs[refname] = objectname
        if added is not None:
            if not added.keys().isdisjoint(refs.keys()):
                raise ValueError('added and refs are not disjoint')
            for refname in list(added.keys()):
                objectname = added[refname]
                if not isinstance(refname, str):
                    matched_ref = None
                    for actual_refname, actual_objectname in actual_refs.items():
                        if key_matcher(refname, actual_refname):
                            matched_ref = actual_refname
                            del added[refname]
                            added[matched_ref] = objectname
                            break

                    if matched_ref is None:
                        raise RuntimeError('no ref matched the specified pattern')

                    matched_refs.append(matched_ref)
                else:
                    matched_refs.append(refname)
                    if objectname is None:
                        objectname = actual_refs.get(refname)
                    else:
                        objectname = actual_refs.get(objectname) or objectname
                    refs[refname] = objectname
        if removed is not None:
            if not removed.keys() <= refs.keys():
                raise ValueError('refs is not a superset of removed')

        self.assert_same_pairs(refs, actual_refs)

        return matched_refs

    def assert_first_parent(self, object: str, expected_parent: str):
        rev_entry = self.git_for_line('git', 'rev-list', '--parents', '--first-parent', '--max-count=1', object).split(
            ' ')

        expected_parent = self.git_for_line('git', 'rev-parse', expected_parent)
        actual_parent = rev_entry[1] if len(rev_entry) == 2 else None
        assert actual_parent == expected_parent

    def assert_head(self, expected: str):
        current_head = self.current_head()
        assert current_head == expected

    def load_project_properties(self):
        try:
            property_reader = PropertyIO.get_instance_by_filename(self.project_property_file)
            actual = property_reader.from_file(self.project_property_file)
        except FileNotFoundError:
            actual = dict()
        return actual

    def assert_project_properties_contain(self, expected: dict):
        actual = self.load_project_properties()

        self.assert_same_pairs(expected, actual)
