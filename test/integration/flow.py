import itertools
import json
import os
import subprocess
from tempfile import TemporaryDirectory

import pytest

from gitflow import __main__, const
from gitflow.filesystem import JavaPropertyFile


@pytest.mark.slow
class TestFlow:
    tempdir: TemporaryDirectory
    orig_cwd: str
    git_origin: str
    git_working_copy: str
    project_property_file: str

    def git_flow(self, *args) -> int:
        return __main__.main([__name__, '-Bv'] + [*args])

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
        self.project_property_file = const.DEFAULT_PROJECT_PROPERTY_FILE
        config_file = os.path.join(self.git_working_copy, const.DEFAULT_CONFIG_FILE)
        with open(config_file, 'w+') as property_file:
            config = {
                const.CONFIG_PROJECT_PROPERTY_FILE: self.project_property_file,
                const.CONFIG_VERSION_PROPERTY_NAME: 'version',
                const.CONFIG_SEQUENTIAL_VERSION_PROPERTY_NAME: 'seq',
                const.CONFIG_BUILD: {
                    'stages': {
                        'assemble': [['echo', 'assemble#1']],
                        'test': {
                            'steps': {
                                'app': [['echo', 'test#1']]
                            }
                        },
                        'google_testing_lab': {
                            'type': 'integration_test',
                            'steps': {
                                'monkey_test': [['echo', 'monkey_test']],
                                'instrumentation_test': [['echo', 'instrumentation_test']]
                            }
                        }
                    }
                }
            }
            json.dump(obj=config, fp=property_file)

        # create & push the initial commit
        self.add(config_file)
        self.commit('initial commit: gitflow config file')
        self.push()

        self.assert_refs([
            'refs/heads/master',
            'refs/remotes/origin/master'
        ])

    def teardown_method(self, method):
        exit_code = self.git_flow('status')
        assert exit_code == os.EX_OK

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
        self.assert_project_properties_contain({
        })

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

        self.checkout("release/1.0")
        self.assert_project_properties_contain({
            # 'version': '1.0.0-alpha.1',
            'seq': '1',
        })

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

        self.checkout("release/1.0")
        self.assert_project_properties_contain({
            # 'version': '1.0.0-alpha.1',
            'seq': '1',
        })

        self.checkout("master")
        self.commit()
        self.push()

        exit_code = self.git_flow('bump-minor', '--assume-yes')
        assert exit_code == os.EX_OK
        self.assert_refs([
            'refs/heads/master',
            'refs/remotes/origin/master',

            'refs/heads/release/1.0',  # local branch
            'refs/remotes/origin/release/1.0',
            'refs/tags/sequential_version/1',
            'refs/tags/version/1.0.0-alpha.1',

            # 'refs/heads/release/1.1', # local branch
            'refs/remotes/origin/release/1.1',
            'refs/tags/sequential_version/2',
            'refs/tags/version/1.1.0-alpha.1'
        ])

        self.checkout("release/1.1")
        self.assert_project_properties_contain({
            # 'version': '1.1.0-alpha.1',
            'seq': '2',
        })

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

        self.checkout("release/1.0")
        self.assert_project_properties_contain({
            # 'version': '1.0.1-alpha.1',
            'seq': '2',
        })

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

        self.checkout("release/1.0")
        self.assert_project_properties_contain({
            # 'version': '1.0.0-beta.1',
            'seq': '1',
        })

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

        self.checkout("release/1.0")
        self.assert_project_properties_contain({
            # 'version': '1.0.0',
            'seq': '1',
        })

    def test_bump_prerelease(self):
        exit_code = self.git_flow('bump-major', '--assume-yes')
        assert exit_code == os.EX_OK
        self.assert_refs([
            'refs/heads/master',
            'refs/remotes/origin/master',
            # 'refs/heads/release/1.0',  # local branch
            'refs/remotes/origin/release/1.0',
            'refs/tags/sequential_version/1',
            'refs/tags/version/1.0.0-alpha.1'
        ])
        self.checkout("release/1.0")
        self.assert_project_properties_contain({
            # 'version': '1.0.0-alpha.1',
            'seq': '1',
        })

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

        self.checkout("release/1.0")
        self.assert_project_properties_contain({
            # 'version': '1.0.0-alpha.2',
            'seq': '2',
        })

    def test_discontinue_implicitly(self):
        exit_code = self.git_flow('bump-major', '--assume-yes')
        assert exit_code == os.EX_OK
        self.assert_refs([
            'refs/heads/master',
            'refs/remotes/origin/master',

            # 'refs/heads/release/1.0',  # local branch
            'refs/remotes/origin/release/1.0',

            'refs/tags/sequential_version/1',
            'refs/tags/version/1.0.0-alpha.1'
        ])

        self.checkout("release/1.0")

        exit_code = self.git_flow('discontinue', '--assume-yes')
        assert exit_code == os.EX_OK
        exit_code = self.git_flow('discontinue', '--assume-yes')
        assert exit_code == os.EX_USAGE
        self.assert_refs([
            'refs/heads/master',
            'refs/remotes/origin/master',

            'refs/heads/release/1.0',  # local branch
            'refs/remotes/origin/release/1.0',

            'refs/tags/discontinued/1.0',
            'refs/tags/sequential_version/1',
            'refs/tags/version/1.0.0-alpha.1'
        ])
        self.checkout("release/1.0")
        self.assert_project_properties_contain({
            # 'version': '1.0.0-alpha.1',
            'seq': '1',
        })

    def test_discontinue_explicitly(self):
        exit_code = self.git_flow('bump-major', '--assume-yes')
        assert exit_code == os.EX_OK
        self.assert_refs([
            'refs/heads/master',
            'refs/remotes/origin/master',

            # 'refs/heads/release/1.0',  # local branch
            'refs/remotes/origin/release/1.0',

            'refs/tags/sequential_version/1',
            'refs/tags/version/1.0.0-alpha.1'
        ])

        exit_code = self.git_flow('discontinue', '--assume-yes', '1.0')
        assert exit_code == os.EX_OK
        exit_code = self.git_flow('discontinue', '--assume-yes', '1.0')
        assert exit_code == os.EX_USAGE
        self.assert_refs([
            'refs/heads/master',
            'refs/remotes/origin/master',

            # 'refs/heads/release/1.0',  # local branch
            'refs/remotes/origin/release/1.0',

            'refs/tags/discontinued/1.0',
            'refs/tags/sequential_version/1',
            'refs/tags/version/1.0.0-alpha.1'
        ])
        self.checkout("release/1.0")
        self.assert_project_properties_contain({
            # 'version': '1.0.0-alpha.1',
            'seq': '1',
        })

    def test_begin_end_dev_feature(self):
        self.assert_head('refs/heads/master')

        exit_code = self.git_flow('start', 'dev', 'feature', 'test-feature')
        assert exit_code == os.EX_OK

        self.assert_head('refs/heads/dev/feature/test-feature')

        for _ in itertools.repeat(None, 3):
            self.commit()
        self.push('-u', 'origin', 'dev/feature/test-feature')
        exit_code = self.git_flow('finish', 'dev', 'feature', 'test-feature')
        assert exit_code == os.EX_OK

        self.assert_head('refs/heads/master')

    def test_begin_end_prod_fix(self):
        self.assert_head('refs/heads/master')

        exit_code = self.git_flow('bump-major', '--assume-yes')
        assert exit_code == os.EX_OK
        self.assert_refs([
            'refs/heads/master',
            'refs/remotes/origin/master',
            # 'refs/heads/release/1.0',  # local branch
            'refs/remotes/origin/release/1.0',
            'refs/tags/sequential_version/1',
            'refs/tags/version/1.0.0-alpha.1'
        ])

        self.assert_head('refs/heads/master')

        self.checkout('release/1.0')
        self.assert_head('refs/heads/release/1.0')

        exit_code = self.git_flow('start', 'prod', 'fix', 'test-fix')
        assert exit_code == os.EX_OK
        self.assert_refs([
            'refs/heads/master',
            'refs/remotes/origin/master',

            'refs/heads/release/1.0',  # local branch
            'refs/remotes/origin/release/1.0',
            'refs/tags/sequential_version/1',
            'refs/tags/version/1.0.0-alpha.1',

            'refs/heads/prod/fix/test-fix'
        ])

        self.assert_head('refs/heads/prod/fix/test-fix')

        for _ in itertools.repeat(None, 3):
            self.commit()
        self.push('-u')
        exit_code = self.git_flow('finish', 'prod', 'fix', 'test-fix', '1.0')
        assert exit_code == os.EX_OK

        self.assert_head('refs/heads/release/1.0')

    def test_misc(self):
        self.assert_head('refs/heads/master')

        exit_code = self.git_flow('bump-major', '--assume-yes')
        assert exit_code == os.EX_OK
        self.assert_refs([
            'refs/heads/master',
            'refs/remotes/origin/master',
            # 'refs/heads/release/1.0',  # local branch
            'refs/remotes/origin/release/1.0',
            'refs/tags/sequential_version/1',
            'refs/tags/version/1.0.0-alpha.1'
        ])

        self.assert_head('refs/heads/master')

        self.checkout('release/1.0')
        self.assert_head('refs/heads/release/1.0')
        self.assert_project_properties_contain({
            # 'version': '1.0.0-alpha.1',
            'seq': '1',
        })

        # hotfix
        exit_code = self.git_flow('start', 'prod', 'fix', 'test-fix')
        assert exit_code == os.EX_OK
        self.assert_refs([
            'refs/heads/master',
            'refs/remotes/origin/master',

            'refs/heads/release/1.0',  # local branch
            'refs/remotes/origin/release/1.0',
            'refs/tags/sequential_version/1',
            'refs/tags/version/1.0.0-alpha.1',

            'refs/heads/prod/fix/test-fix'
        ])

        self.assert_head('refs/heads/prod/fix/test-fix')

        for _ in itertools.repeat(None, 3):
            self.commit()
        self.push('-u')
        exit_code = self.git_flow('finish', 'prod', 'fix', 'test-fix', '1.0')
        assert exit_code == os.EX_OK

        self.assert_head('refs/heads/release/1.0')
        self.assert_refs([
            'refs/heads/master',
            'refs/remotes/origin/master',

            'refs/heads/release/1.0',  # local branch
            'refs/remotes/origin/release/1.0',
            'refs/tags/sequential_version/1',
            'refs/tags/version/1.0.0-alpha.1',

            'refs/heads/prod/fix/test-fix',
            'refs/remotes/origin/prod/fix/test-fix'
        ])

        # hotfix 2 with implicit finish on work branch
        exit_code = self.git_flow('start', 'prod', 'fix', 'test-fix2')
        assert exit_code == os.EX_OK
        self.assert_refs([
            'refs/heads/master',
            'refs/remotes/origin/master',

            'refs/heads/release/1.0',  # local branch
            'refs/remotes/origin/release/1.0',
            'refs/tags/sequential_version/1',
            'refs/tags/version/1.0.0-alpha.1',

            'refs/heads/prod/fix/test-fix',
            'refs/remotes/origin/prod/fix/test-fix',

            'refs/heads/prod/fix/test-fix2'
        ])

        self.assert_head('refs/heads/prod/fix/test-fix2')

        for _ in itertools.repeat(None, 3):
            self.commit()
        self.push('-u')
        exit_code = self.git_flow('finish')
        assert exit_code == os.EX_OK

        self.assert_head('refs/heads/release/1.0')

        # GA release

        exit_code = self.git_flow('bump-patch', '--assume-yes', '1.0')
        assert exit_code == os.EX_OK
        exit_code = self.git_flow('bump-prerelease-type', '--assume-yes', '1.0')
        assert exit_code == os.EX_OK
        exit_code = self.git_flow('bump-to-release', '--assume-yes', '1.0')
        assert exit_code == os.EX_OK

        self.checkout('release/1.0')
        self.assert_project_properties_contain({
            # 'version': '1.0.1-alpha.1',
            'seq': '2',
        })

        # new feature

        self.checkout('master')
        self.assert_head('refs/heads/master')

        exit_code = self.git_flow('start', 'dev', 'feature', 'test-feature')
        assert exit_code == os.EX_OK

        self.assert_head('refs/heads/dev/feature/test-feature')

        for _ in itertools.repeat(None, 3):
            self.commit()
        self.push('-u')
        exit_code = self.git_flow('finish', 'dev', 'feature', 'test-feature')
        assert exit_code == os.EX_OK

        self.assert_refs([
            'refs/heads/master',
            'refs/remotes/origin/master',

            'refs/heads/release/1.0',  # local branch
            'refs/remotes/origin/release/1.0',

            'refs/tags/sequential_version/1',
            'refs/tags/version/1.0.0-alpha.1',

            'refs/tags/sequential_version/2',
            'refs/tags/version/1.0.1-alpha.1',
            'refs/tags/version/1.0.1-beta.1',
            'refs/tags/version/1.0.1',

            'refs/heads/prod/fix/test-fix',
            'refs/remotes/origin/prod/fix/test-fix',

            'refs/heads/prod/fix/test-fix2',
            'refs/remotes/origin/prod/fix/test-fix2',

            'refs/heads/dev/feature/test-feature',
            'refs/remotes/origin/dev/feature/test-feature',
        ])

        # new major version
        exit_code = self.git_flow('bump-major', '--assume-yes')
        assert exit_code == os.EX_OK
        self.assert_refs([
            'refs/heads/master',
            'refs/remotes/origin/master',

            'refs/heads/release/1.0',  # local branch
            'refs/remotes/origin/release/1.0',
            'refs/tags/sequential_version/1',
            'refs/tags/version/1.0.0-alpha.1',

            'refs/tags/sequential_version/2',
            'refs/tags/version/1.0.1-alpha.1',
            'refs/tags/version/1.0.1-beta.1',
            'refs/tags/version/1.0.1',

            # 'refs/heads/release/2.0',  # local branch
            'refs/remotes/origin/release/2.0',
            'refs/tags/sequential_version/3',
            'refs/tags/version/2.0.0-alpha.1',

            'refs/heads/prod/fix/test-fix',
            'refs/remotes/origin/prod/fix/test-fix',

            'refs/heads/prod/fix/test-fix2',
            'refs/remotes/origin/prod/fix/test-fix2',

            'refs/heads/dev/feature/test-feature',
            'refs/remotes/origin/dev/feature/test-feature',
        ])
        self.checkout('release/2.0')
        self.assert_project_properties_contain({
            # 'version': '2.0.0-alpha.1',
            'seq': '3',
        })

    def test_build(self):
        exit_code = self.git_flow('build')
        assert exit_code == os.EX_OK
