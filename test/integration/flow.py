import os
import subprocess
from tempfile import TemporaryDirectory

import pytest

from gitflow import __main__


@pytest.mark.slow
class TestFlow:
    tempdir: TemporaryDirectory
    orig_cwd: str
    git_origin: str
    git_working_copy: str

    def git_flow(self, *args) -> int:
        return __main__.main([__name__, '-Bvv'] + [*args])

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

    def push(self):
        exit_code = self.git('push', 'origin')
        assert exit_code == os.EX_OK

    def checkout(self, branch: str):
        exit_code = self.git('checkout', branch)
        assert exit_code == os.EX_OK

    def assert_same_elements(self, expected: list, actual: list):
        expected = sorted(expected)
        actual = sorted(actual)
        if expected != actual:
            pytest.fail("Comparison assertion failed")

    def assert_refs(self, expected: list, actual: list = None):
        if actual is None:
            actual = self.list_refs()
        self.assert_same_elements(expected, actual)

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

        # create the config file
        config_file = os.path.join(self.git_working_copy, 'gitflow.properties')
        with open(config_file, 'w+') as property_file:
            property_file.write('')
            property_file.close()

        # create & push the initial commit
        self.add(config_file)
        self.commit('initial commit: gitflow config file')
        self.push()

        self.assert_refs([
            'refs/heads/master',
            'refs/remotes/origin/master'
        ])

    def teardown_method(self, method):
        self.tempdir.cleanup()
        os.chdir(self.orig_cwd)

    def test_status(self):
        exit_code = self.git_flow('status')
        assert exit_code == os.EX_OK

    def test_log(self):
        exit_code = self.git_flow('log')
        assert exit_code == os.EX_OK

    def test_bump_major(self):
        exit_code = self.git_flow('bump-major', '--assume-yes')
        assert exit_code == os.EX_OK
        self.assert_refs([
            'refs/heads/master',
            'refs/remotes/origin/master',
            # 'refs/heads/release/1.0', # local branch
            'refs/remotes/origin/release/1.0',
            'refs/tags/sequential_version/1',
            'refs/tags/version/1.0.0-alpha.1'
        ])
        # the head commit is the base of a release branch, further bumps shall not be possible
        exit_code = self.git_flow('bump-major', '--assume-yes')
        assert exit_code == os.EX_USAGE
        self.assert_refs([
            'refs/heads/master',
            'refs/remotes/origin/master',
            # 'refs/heads/release/1.0', # local branch
            'refs/remotes/origin/release/1.0',
            'refs/tags/sequential_version/1',
            'refs/tags/version/1.0.0-alpha.1'
        ])

    def test_bump_minor(self):
        exit_code = self.git_flow('bump-minor', '--assume-yes')
        assert exit_code == os.EX_OK
        self.assert_refs([
            'refs/heads/master',
            'refs/remotes/origin/master',
            # 'refs/heads/release/1.0', # local branch
            'refs/remotes/origin/release/1.0',
            'refs/tags/sequential_version/1',
            'refs/tags/version/1.0.0-alpha.1'
        ])
        # the head commit is the base of a release branch, further bumps shall not be possible
        exit_code = self.git_flow('bump-minor', '--assume-yes')
        assert exit_code == os.EX_USAGE
        self.assert_refs([
            'refs/heads/master',
            'refs/remotes/origin/master',
            # 'refs/heads/release/1.0', # local branch
            'refs/remotes/origin/release/1.0',
            'refs/tags/sequential_version/1',
            'refs/tags/version/1.0.0-alpha.1'
        ])

    def test_bump_patch(self):
        exit_code = self.git_flow('bump-major', '--assume-yes')
        assert exit_code == os.EX_OK
        self.assert_refs([
            'refs/heads/master',
            'refs/remotes/origin/master',
            # 'refs/heads/release/1.0', # local branch
            'refs/remotes/origin/release/1.0',
            'refs/tags/sequential_version/1',
            'refs/tags/version/1.0.0-alpha.1'
        ])
        self.checkout('release/1.0')
        exit_code = self.git_flow('bump-major', '--assume-yes')
        assert exit_code == os.EX_USAGE
        self.assert_refs([
            'refs/heads/master',
            'refs/remotes/origin/master',
            'refs/heads/release/1.0',  # local branch
            'refs/remotes/origin/release/1.0',
            'refs/tags/sequential_version/1',
            'refs/tags/version/1.0.0-alpha.1'
        ])

        self.commit()
        exit_code = self.git_flow('bump-patch', '--assume-yes')
        assert exit_code == os.EX_USAGE
        self.push()
        exit_code = self.git_flow('bump-patch', '--assume-yes')
        assert exit_code == os.EX_OK
        self.assert_refs([
            'refs/heads/master',
            'refs/remotes/origin/master',
            'refs/heads/release/1.0',  # local branch
            'refs/remotes/origin/release/1.0',

            'refs/tags/sequential_version/1',
            'refs/tags/version/1.0.0-alpha.1',

            'refs/tags/sequential_version/2',
            'refs/tags/version/1.0.1-alpha.1'
        ])

    def test_bump_prerelease_type(self):
        exit_code = self.git_flow('bump-major', '--assume-yes')
        assert exit_code == os.EX_OK
        self.checkout('release/1.0')
        exit_code = self.git_flow('bump-major', '--assume-yes')
        assert exit_code == os.EX_USAGE

        exit_code = self.git_flow('bump-prerelease-type', '--assume-yes')
        assert exit_code == os.EX_OK
        self.assert_refs([
            'refs/heads/master',
            'refs/remotes/origin/master',
            'refs/heads/release/1.0',  # local branch
            'refs/remotes/origin/release/1.0',

            'refs/tags/sequential_version/1',
            'refs/tags/version/1.0.0-alpha.1',
            'refs/tags/version/1.0.0-beta.1'
        ])
        exit_code = self.git_flow('bump-prerelease-type', '--assume-yes')
        assert exit_code == os.EX_OK
        self.assert_refs([
            'refs/heads/master',
            'refs/remotes/origin/master',
            'refs/heads/release/1.0',  # local branch
            'refs/remotes/origin/release/1.0',

            'refs/tags/sequential_version/1',
            'refs/tags/version/1.0.0-alpha.1',
            'refs/tags/version/1.0.0-beta.1',
            'refs/tags/version/1.0.0-rc.1'
        ])

    def test_bump_to_release(self):
        exit_code = self.git_flow('bump-major', '--assume-yes')
        assert exit_code == os.EX_OK
        self.checkout('release/1.0')
        exit_code = self.git_flow('bump-major', '--assume-yes')
        assert exit_code == os.EX_USAGE

        exit_code = self.git_flow('bump-prerelease-type', '--assume-yes')
        assert exit_code == os.EX_OK
        self.assert_refs([
            'refs/heads/master',
            'refs/remotes/origin/master',
            'refs/heads/release/1.0',  # local branch
            'refs/remotes/origin/release/1.0',

            'refs/tags/sequential_version/1',
            'refs/tags/version/1.0.0-alpha.1',
            'refs/tags/version/1.0.0-beta.1'
        ])
        exit_code = self.git_flow('bump-to-release', '--assume-yes')
        assert exit_code == os.EX_OK
        self.assert_refs([
            'refs/heads/master',
            'refs/remotes/origin/master',
            'refs/heads/release/1.0',  # local branch
            'refs/remotes/origin/release/1.0',

            'refs/tags/sequential_version/1',
            'refs/tags/version/1.0.0-alpha.1',
            'refs/tags/version/1.0.0-beta.1',
            'refs/tags/version/1.0.0'
        ])

    def test_bump_prerelease(self):
        exit_code = self.git_flow('bump-major', '--assume-yes')
        assert exit_code == os.EX_OK
        self.checkout('release/1.0')
        exit_code = self.git_flow('bump-major', '--assume-yes')
        assert exit_code == os.EX_USAGE
        self.assert_refs([
            'refs/heads/master',
            'refs/remotes/origin/master',
            'refs/heads/release/1.0',  # local branch
            'refs/remotes/origin/release/1.0',
            'refs/tags/sequential_version/1',
            'refs/tags/version/1.0.0-alpha.1'
        ])

        self.commit()
        exit_code = self.git_flow('bump-prerelease', '--assume-yes')
        assert exit_code == os.EX_USAGE
        self.push()
        exit_code = self.git_flow('bump-prerelease', '--assume-yes')
        assert exit_code == os.EX_OK
        self.assert_refs([
            'refs/heads/master',
            'refs/remotes/origin/master',
            'refs/heads/release/1.0',  # local branch
            'refs/remotes/origin/release/1.0',

            'refs/tags/sequential_version/1',
            'refs/tags/version/1.0.0-alpha.1',

            'refs/tags/sequential_version/2',
            'refs/tags/version/1.0.0-alpha.2'
        ])
