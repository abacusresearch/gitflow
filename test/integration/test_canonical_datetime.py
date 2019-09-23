import itertools
import os
import re

from gitflow import const
from gitflow.procedures.scheme.canonical_datetime import CanonicalDateTime
from gitflow.properties import PropertyIO
from test.integration.base import TestFlowBase


class TestFlow(TestFlowBase):
    version_tag_prefix: str = None

    def version_from_tag_ref(self, ref: str) -> str:
        match = re.match('^refs/tags/([0-9]+)$', ref)
        if match is None:
            return None
        return match.group(1)

    def match_tag_range(self, value: str, expected_earliest, expected_latest) -> bool:
        version = self.version_from_tag_ref(value)

        if version is None:
            return False

        return int(expected_earliest) <= int(version) <= int(expected_latest)

    def version_tag(self, expected_version_range: list):
        return lambda value: self.match_tag_range(value, expected_version_range[0], expected_version_range[1])

    def setup_method(self, method):
        TestFlowBase.setup_method(self, method)

        # create the config file
        self.project_property_file = 'project.properties'
        config_file = os.path.join(self.git_working_copy, const.DEFAULT_CONFIG_FILE)
        config = {
            const.CONFIG_VERSIONING_SCHEME: 'canonical_datetime',
            const.CONFIG_PROJECT_PROPERTY_FILE: self.project_property_file,
            const.CONFIG_VERSION_PROPERTY: 'version',
            const.CONFIG_SEQUENCE_NUMBER_PROPERTY: 'seq',
            const.CONFIG_VERSION_TAG_PREFIX: None,
            # const.CONFIG_VERSION_TAG_PATTERN: ...
            const.CONFIG_RELEASE_BRANCH_PREFIX: None,
            # const.CONFIG_RELEASE_BRANCH_PATTERN: ...
        }

        PropertyIO.write_file(config_file, config)

        self.version_tag_prefix = config.get(const.CONFIG_VERSION_TAG_PREFIX,
                                             const.DEFAULT_VERSION_TAG_PREFIX) or ''

        # create & push the initial commit
        self.add(config_file)
        self.commit('initial commit: gitflow config file')
        self.push()

        self.assert_refs({
            'refs/heads/master',
            'refs/remotes/' + self.remote_name + '/master'
        })

    def create_first_version(self):
        head = self.git_get_hash('master')
        refs = {
            'refs/heads/master': head,
            'refs/remotes/' + self.remote_name + '/master': head,
        }
        exit_code = self.git_flow('bump-major', '--assume-yes')
        assert exit_code == os.EX_OK
        head = self.git_get_hash('master')
        self.assert_refs(refs, updated={
            'refs/heads/master': head,
            'refs/remotes/' + self.remote_name + '/master': head,
        }, added={
            'refs/tags/' + self.version_tag_prefix + '1': head
        })

        properties = self.load_project_properties()

        return refs, properties

    def test_status(self):
        exit_code = self.git_flow('status')
        assert exit_code == os.EX_OK

    def test_log(self):
        exit_code = self.git_flow('log')
        assert exit_code == os.EX_OK

    def test_bump_major(self):
        refs = dict()
        self.assert_refs(refs, added={
            'refs/heads/master',
            'refs/remotes/' + self.remote_name + '/master'
        })

        expected_version_range = []
        expected_version_range.append(CanonicalDateTime.generate_version())

        exit_code = self.git_flow('bump-major', '--assume-yes')
        assert exit_code == os.EX_OK

        expected_version_range.append(CanonicalDateTime.generate_version())

        head = self.git_get_hash('master')
        new_tag = 'refs/tags/' + self.version_tag_prefix + '1'
        added_refs = self.assert_refs(refs, added={
            self.version_tag(expected_version_range): head
        }, updated={
            'refs/heads/master': head,
            'refs/remotes/' + self.remote_name + '/master': head
        }, key_matcher=TestFlowBase.match_pattern)

        self.assert_project_properties_contain({
            'version': self.version_from_tag_ref(added_refs[0]),
        })

        # the head commit is the base of a release branch, further bumps shall not be possible
        exit_code = self.git_flow('bump-major', '--assume-yes')
        assert exit_code == os.EX_USAGE
        self.assert_refs(refs)

        self.assert_project_properties_contain({
            'version': self.version_from_tag_ref(added_refs[0]),
        })

    def test_bump_minor(self):
        refs = {
            'refs/heads/master',
            'refs/remotes/' + self.remote_name + '/master',
        }

        exit_code = self.git_flow('bump-minor', '--assume-yes')
        assert exit_code == os.EX_USAGE
        self.assert_refs(refs)

    def test_bump_patch(self):
        refs = {
            'refs/heads/master',
            'refs/remotes/' + self.remote_name + '/master',
        }

        exit_code = self.git_flow('bump-patch', '--assume-yes')
        assert exit_code == os.EX_USAGE
        self.assert_refs(refs)

    def test_discontinue_implicitly(self):
        refs, properties = self.create_first_version()

        exit_code = self.git_flow('discontinue', '--assume-yes')
        assert exit_code == os.EX_USAGE
        self.assert_refs(refs, added={})

        self.assert_refs(refs)
        self.assert_project_properties_contain(properties)

    def test_discontinue_explicitly(self):
        refs, properties = self.create_first_version()

        exit_code = self.git_flow('discontinue', '--assume-yes', '1')
        assert exit_code == os.EX_USAGE

        self.assert_refs(refs)
        self.assert_project_properties_contain(properties)

    def test_begin_end_dev_feature(self):
        refs, properties = self.create_first_version()

        exit_code = self.git_flow('start', 'dev', 'feature', 'test-feature')
        assert exit_code == os.EX_OK
        self.assert_head('refs/heads/dev/feature/test-feature')
        self.assert_refs(refs, added={
            'refs/heads/dev/feature/test-feature'
        })

        for _ in itertools.repeat(None, 3):
            self.commit()

        self.push('-u', self.remote_name, 'dev/feature/test-feature')
        self.assert_refs(refs, updated={
            'refs/heads/dev/feature/test-feature'
        }, added={
            'refs/remotes/' + self.remote_name + '/dev/feature/test-feature'
        })

        exit_code = self.git_flow('finish', 'dev', 'feature', 'test-feature')
        assert exit_code == os.EX_OK
        head = self.git_get_hash('master')

        self.assert_refs(refs, updated={
            'refs/heads/master': head,
            'refs/remotes/' + self.remote_name + '/master': head,
        })

        self.assert_refs(refs)
        
        self.assert_project_properties_contain(properties)

    def test_begin_end_dev_feature_from_another_branch(self):
        refs = {
            'refs/heads/master',
            'refs/remotes/' + self.remote_name + '/master',
        }

        self.assert_head('refs/heads/master')

        exit_code = self.git_flow('start', 'dev', 'feature', 'test-feature')
        assert exit_code == os.EX_OK

        self.assert_head('refs/heads/dev/feature/test-feature')

        self.assert_refs(refs, added={
            'refs/heads/dev/feature/test-feature',
        })

        for _ in itertools.repeat(None, 3):
            self.commit()
        self.push('-u', self.remote_name, 'dev/feature/test-feature')
        self.assert_refs(refs, added={
            'refs/remotes/' + self.remote_name + '/dev/feature/test-feature',
        })

        self.checkout("master")
        self.assert_head('refs/heads/master')

        exit_code = self.git_flow('finish', 'dev', 'feature', 'test-feature')
        assert exit_code == os.EX_OK

        self.assert_head('refs/heads/master')

        self.assert_refs(refs)

    def test_begin_end_prod_fix(self):
        refs, properties = self.create_first_version()

        exit_code = self.git_flow('start', 'prod', 'fix', 'test-fix')
        assert exit_code == os.EX_OK
        self.assert_refs(refs, added={
            'refs/heads/prod/fix/test-fix'
        })

        self.assert_head('refs/heads/prod/fix/test-fix')

        for _ in itertools.repeat(None, 3):
            self.commit()
        self.push('-u')
        self.assert_refs(refs, updated={
            'refs/heads/prod/fix/test-fix'
        }, added={
            'refs/remotes/' + self.remote_name + '/prod/fix/test-fix'
        })

        exit_code = self.git_flow('finish', 'prod', 'fix', 'test-fix', 'master')
        assert exit_code == os.EX_OK

        head = self.git_get_hash('master')
        self.assert_refs(refs, updated={
            'refs/heads/master': head,
            'refs/remotes/' + self.remote_name + '/master': head,
        })

    def test_misc(self):
        refs, properties = self.create_first_version()

        self.assert_head('refs/heads/master')

        # hotfix
        exit_code = self.git_flow('start', 'prod', 'fix', 'test-fix')
        assert exit_code == os.EX_OK
        self.assert_refs(refs, added={
            'refs/heads/prod/fix/test-fix'
        })

        self.assert_head('refs/heads/prod/fix/test-fix')

        for _ in itertools.repeat(None, 3):
            head = self.commit()
        self.push('-u')
        self.assert_refs(refs, updated={
            'refs/heads/prod/fix/test-fix': head
        }, added={
            'refs/remotes/' + self.remote_name + '/prod/fix/test-fix': head
        })

        exit_code = self.git_flow('finish', 'prod', 'fix', 'test-fix', '1.0')
        assert exit_code == os.EX_OK
        head = self.git_get_hash('master')
        self.assert_refs(refs, updated={
            'refs/heads/master': head,
            'refs/remotes/' + self.remote_name + '/master': head
        })

        # hotfix 2 with implicit finish on work branch
        exit_code = self.git_flow('start', 'prod', 'fix', 'test-fix2')
        assert exit_code == os.EX_OK
        self.assert_refs(refs, added={
            'refs/heads/prod/fix/test-fix2'
        })

        self.assert_head('refs/heads/prod/fix/test-fix2')

        for _ in itertools.repeat(None, 3):
            head = self.commit()
        self.push('-u')
        self.assert_refs(refs, updated={
            'refs/heads/prod/fix/test-fix2': head
        }, added={
            'refs/remotes/' + self.remote_name + '/prod/fix/test-fix2': head,
        })

        exit_code = self.git_flow('finish')
        assert exit_code == os.EX_OK
        head = self.git_get_hash('master')
        self.assert_refs(refs, updated={
            'refs/heads/master': head,
            'refs/remotes/' + self.remote_name + '/master': head
        })

        # new feature

        self.checkout('master')
        self.assert_head('refs/heads/master')

        exit_code = self.git_flow('start', 'dev', 'feature', 'test-feature')
        assert exit_code == os.EX_OK
        self.assert_refs(refs, added={
            'refs/heads/dev/feature/test-feature'
        })

        self.assert_head('refs/heads/dev/feature/test-feature')

        for _ in itertools.repeat(None, 3):
            head = self.commit()
        self.push('-u')
        self.assert_refs(refs, updated={
            'refs/heads/dev/feature/test-feature': head
        }, added={
            'refs/remotes/' + self.remote_name + '/dev/feature/test-feature': head
        })

        exit_code = self.git_flow('finish', 'dev', 'feature', 'test-feature')
        assert exit_code == os.EX_OK
        head = self.git_get_hash('master')
        self.assert_refs(refs, updated={
            'refs/heads/master': head,
            'refs/remotes/' + self.remote_name + '/master': head
        })

        self.assert_head('refs/heads/master')

        # new major version

        expected_version_range = []
        expected_version_range.append(CanonicalDateTime.generate_version())

        exit_code = self.git_flow('bump-major', '--assume-yes')
        assert exit_code == os.EX_OK

        expected_version_range.append(CanonicalDateTime.generate_version())

        head = self.git_get_hash('master')
        added_refs = self.assert_refs(refs, updated={
            'refs/heads/master': head,
            'refs/remotes/' + self.remote_name + '/master': head
        }, added={
            self.version_tag(expected_version_range): head,
        }, key_matcher=TestFlowBase.match_pattern)

        self.assert_project_properties_contain({
            'version': self.version_from_tag_ref(added_refs[0])
        })
