import itertools
import os
import subprocess
import sys
from io import StringIO
from tempfile import TemporaryDirectory
from typing import Tuple, Optional, Union, List, Callable

from gitflow import __main__, repotools, const
from gitflow.properties import PropertyIO

git_flow_executable = os.environ.get('GIT_FLOW_EXECUTABLE')

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

    def has_differences(self) -> bool:
        return bool((len(self.a) - len(self.b)) or (len(self.a) - len(self.intersect)) or len(self.added()) or len(
            self.removed()) or len(self.changed()))

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
            (key, (self.a[key], self.b[key])) for key in self.intersect if
            not self.value_matcher(self.a[key], self.b[key])
        )

    def unchanged(self) -> dict:
        return dict(
            (key, self.a[key]) for key in self.intersect if self.value_matcher(self.a[key], self.b[key])
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
    remote_name: str = 'test-origin'

    def setup_method(self, method):
        self.orig_cwd = os.getcwd()
        self.tempdir = TemporaryDirectory()

        # switch to the working copy
        os.chdir(self.tempdir.name)

    def teardown_method(self, method):
        self.tempdir.cleanup()
        os.chdir(self.orig_cwd)

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

    def git_flow(self, *args) -> Tuple[int, str, str]:
        args_ = (['--remote', self.remote_name] if self.remote_name is not None else []) + ['-B'] + [*args]
        returncode = None
        out = ''
        err = ''

        if git_flow_executable is not None:
            proc_args = ['bash', git_flow_executable] + args_

            print(' '.join(proc_args))

            proc = subprocess.Popen(args=proc_args, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                    cwd=os.getcwd())
            out, err = proc.communicate()

            returncode = proc.returncode
            out = out.decode('utf-8')
            err = err.decode('utf-8')
        else:
            prev_stdout = sys.stdout
            prev_stderr = sys.stderr

            sys.stdout = stdout_buf = StringIO()
            sys.stderr = stderr_buf = StringIO()

            returncode = __main__.main([__name__] + [*args_])
            out = stdout_buf.getvalue()
            err = stderr_buf.getvalue()

            sys.stdout = prev_stdout
            sys.stderr = prev_stderr
        if len(err):
            eprint(err)

        return returncode, out, err

    def assert_in_sync_with_remote(self, local_ref=None):
        if local_ref is None:
            local_ref = self.current_head()

        proc = subprocess.Popen(args=['git', 'for-each-ref', '--count', '1'])
        proc.wait()
        if proc.returncode == os.EX_OK:
            if local_ref.startswith(const.LOCAL_BRANCH_PREFIX):
                self.git_for_lines('git', 'fetch', self.remote_name)

                refs = self.get_ref_map()

                remote_ref = repotools.create_remote_branch_ref_name(remote=self.remote_name, name=local_ref)

                local_hash = refs.get(local_ref)
                remote_hash = refs.get(remote_ref)

                assert remote_hash is None or local_hash == remote_hash

    def git_flow_for_lines(self, *args) -> Tuple[int, List[str], List[str]]:
        exit_code, out, err = self.git_flow(*args)

        out_lines = out.splitlines()
        err_lines = err.splitlines()

        while len(out_lines) and len(out_lines[-1]) == 0:
            del out_lines[-1]
        while len(err_lines) and len(err_lines[-1]) == 0:
            del err_lines[-1]

        return exit_code, out_lines, err_lines

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
        if diff.has_differences():
            eprint("extra:")
            eprint(*["    " + key + ": " + repr(value) for key, value in diff.added().items()], sep='\n')
            eprint("missing:")
            eprint(*["    " + key + ": " + repr(value) for key, value in diff.removed().items()], sep='\n')
            eprint("changed:")
            eprint(*["    " + key + ": " + repr(values[0]) + ", was " + repr(values[1]) for key, values in
                     diff.changed().items()], sep='\n')

            assert False, "Mismatching dictionaries"


class TestFlowBase(TestInTempDir):
    git_origin: str = None
    git_working_copy: str = None
    project_property_file: str = None
    refs: dict = {}

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

        if self.remote_name is not None and self.remote_name != 'origin':
            proc = subprocess.Popen(
                args=['git', '-C', self.git_working_copy, 'remote', 'rename', 'origin', self.remote_name])
            proc.wait()
            assert proc.returncode == os.EX_OK

            proc = subprocess.Popen(
                args=['git', '-C', self.git_working_copy, 'config', 'remote.pushdefault', self.remote_name])
            proc.wait()
            assert proc.returncode == os.EX_OK

            proc = subprocess.Popen(args=['git', '-C', self.git_working_copy, 'fetch', '--all', '--prune'])
            proc.wait()
            assert proc.returncode == os.EX_OK

        # switch to the working copy
        os.chdir(self.git_working_copy)

    def teardown_method(self, method):
        try:
            exit_code, out, err = self.git_flow('status')
            assert exit_code == os.EX_OK
        finally:
            super().teardown_method(self)

    def checkout_commit_and_push(self, local_branch_name: str):
        head = None

        assert local_branch_name.startswith(const.LOCAL_BRANCH_PREFIX)

        remote_branch_name = repotools.create_remote_branch_ref_name(remote=self.remote_name, name=local_branch_name)
        short_branch_name = local_branch_name[len(const.LOCAL_BRANCH_PREFIX):]

        ref_map = self.get_ref_map()

        local_exists = local_branch_name in ref_map.keys()
        remote_exists = remote_branch_name in ref_map.keys()

        self.git('checkout', '-B', short_branch_name, local_branch_name if local_exists else remote_branch_name)

        for _ in itertools.repeat(None, 3):
            head = self.commit()

        self.push('-u', self.remote_name)

        updated = {}
        added = {}

        (updated if local_exists else added)[local_branch_name] = head
        (updated if remote_exists else added)[remote_branch_name] = head

        self.assert_refs(updated=updated, added=added)

        return head

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
                    updated: Optional[Union[dict]] = None,
                    added: Optional[Union[set, dict]] = None,
                    removed: Optional[Union[set, dict]] = None,
                    key_matcher: Callable = None,
                    value_matcher: Callable = None) -> List[str]:

        refs = self.refs

        """
        :return: added refs ordered as specified in 'added'
        """

        added_refs = []

        if not isinstance(refs, dict):
            raise RuntimeError('refs is not a dict')
        if updated is not None and not isinstance(updated, dict):
            raise RuntimeError('updated is not a dict')
        if added is not None and not isinstance(added, dict):
            added = dict.fromkeys(added, None)
        if removed is not None and not isinstance(removed, dict):
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

                    added_refs.append(matched_ref)
                    refs[matched_ref] = objectname
                else:
                    added_refs.append(refname)
                    if objectname is None:
                        objectname = actual_refs.get(refname)
                    else:
                        objectname = actual_refs.get(objectname) or objectname
                    refs[refname] = objectname
        if removed is not None:
            if not removed.keys() <= refs.keys():
                raise ValueError('refs is not a superset of removed')

        self.assert_same_pairs(refs, actual_refs)

        return added_refs

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
