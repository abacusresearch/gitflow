import itertools
import os

from gitflow import const
from gitflow.properties import PropertyIO
from test.integration.base import TestFlowBase


class TestFlow(TestFlowBase):
    version_tag_prefix: str = None

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
            const.CONFIG_RELEASE_BRANCH_PREFIX: None,
            const.CONFIG_RELEASE_BRANCH_PATTERN: 'master'
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
            'refs/remotes/origin/master'
        })

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
            'refs/remotes/origin/master'
        })

        exit_code = self.git_flow('bump-major', '--assume-yes')
        assert exit_code == os.EX_OK
        self.assert_refs(refs, added={
            'refs/tags/' + self.version_tag_prefix + '1': 'refs/heads/master'
        })

        self.assert_project_properties_contain({
            'version': '1',
        })

        # the head commit is already tagged, further bumps shall not be possible
        exit_code = self.git_flow('bump-major', '--assume-yes')
        assert exit_code == os.EX_USAGE
        self.assert_refs(refs)

        self.assert_project_properties_contain({
            'version': '1',
        })

    def test_bump_minor(self):
        refs = {
            'refs/heads/master',
            'refs/remotes/origin/master',
        }

        exit_code = self.git_flow('bump-minor', '--assume-yes')
        assert exit_code == os.EX_USAGE
        self.assert_refs(refs)

    def test_bump_patch(self):
        refs = {
            'refs/heads/master',
            'refs/remotes/origin/master',
        }

        exit_code = self.git_flow('bump-patch', '--assume-yes')
        assert exit_code == os.EX_USAGE
        self.assert_refs(refs)

    def test_bump_patch_on_untagged_branch(self):
        refs = {
            'refs/heads/master',
            'refs/remotes/origin/master'
        }

        exit_code = self.git_flow('bump-major', '--assume-yes')
        assert exit_code == os.EX_OK
        self.assert_refs(refs, added={
            'refs/remotes/origin/release/1.0',
            'refs/tags/' + self.version_tag_prefix + '1.0.0-1'
        })

        self.commit('dummy')
        self.push()

        self.git('checkout', '-b', 'release/1.1', 'master')
        self.assert_refs(refs, added={
            'refs/heads/release/1.1'  # local branch
        })

        self.push('-u')
        self.assert_refs(refs, added={
            'refs/remotes/origin/release/1.1'  # remote branch
        })

        exit_code = self.git_flow('bump-major', '--assume-yes')
        assert exit_code == os.EX_USAGE
        self.assert_refs(refs)

        self.commit()
        exit_code = self.git_flow('bump-patch', '--assume-yes')
        assert exit_code == os.EX_USAGE

        self.push()
        self.assert_refs(refs)

        exit_code = self.git_flow('bump-patch', '--assume-yes')
        assert exit_code == os.EX_OK
        self.assert_refs(refs, added={
            'refs/tags/' + self.version_tag_prefix + '1.1.0-2'
        })

        self.assert_project_properties_contain({
            'seq': '2',
            'version': '1.1.0-2'
        })

    def test_bump_prerelease_type(self):
        refs = {
            'refs/heads/master',
            'refs/remotes/origin/master',
        }

        exit_code = self.git_flow('bump-major', '--assume-yes')
        assert exit_code == os.EX_OK
        self.assert_refs(refs, added={
            'refs/remotes/origin/release/1.0',
            'refs/tags/' + self.version_tag_prefix + '1.0.0-1'
        })

        self.checkout('release/1.0')
        self.assert_refs(refs, added={
            'refs/heads/release/1.0',  # local branch
        })

        exit_code = self.git_flow('bump-major', '--assume-yes')
        assert exit_code == os.EX_USAGE

        exit_code = self.git_flow('bump-prerelease-type', '--assume-yes')
        assert exit_code != os.EX_OK
        exit_code = self.git_flow('bump-prerelease-type', '--assume-yes')
        assert exit_code != os.EX_OK
        self.assert_refs(refs)

        self.checkout("release/1.0")
        self.assert_project_properties_contain({
            'seq': '1',
            'version': '1.0.0-1'
        })

        self.assert_refs(refs)

    def test_bump_to_release(self):
        refs = {
            'refs/heads/master',
            'refs/remotes/origin/master',
        }

        exit_code = self.git_flow('bump-major', '--assume-yes')
        assert exit_code == os.EX_OK
        self.assert_refs(refs, added={
            'refs/remotes/origin/release/1.0',
            'refs/tags/' + self.version_tag_prefix + '1.0.0-1'
        })

        self.checkout('release/1.0')
        self.assert_refs(refs, added={
            'refs/heads/release/1.0',  # local branch
        })

        exit_code = self.git_flow('bump-major', '--assume-yes')
        assert exit_code == os.EX_USAGE
        self.assert_refs(refs)

        exit_code = self.git_flow('bump-prerelease-type', '--assume-yes')
        assert exit_code == os.EX_USAGE
        self.assert_refs(refs)

        self.checkout("release/1.0")
        self.assert_project_properties_contain({
            'seq': '1',
            'version': '1.0.0-1'
        })

        self.assert_refs(refs)

    def test_bump_prerelease(self):
        refs = {
            'refs/heads/master',
            'refs/remotes/origin/master',
        }

        exit_code = self.git_flow('bump-major', '--assume-yes')
        assert exit_code == os.EX_OK
        self.assert_refs(refs, added={
            'refs/remotes/origin/release/1.0',
            'refs/tags/' + self.version_tag_prefix + '1.0.0-1'
        })
        self.checkout("release/1.0")
        self.assert_refs(refs, added={
            'refs/heads/release/1.0'  # local branch
        })
        self.assert_project_properties_contain({
            'seq': '1',
            'version': '1.0.0-1'
        })

        self.commit()

        exit_code = self.git_flow('bump-prerelease', '--assume-yes')
        assert exit_code == os.EX_USAGE

        self.push()

        exit_code = self.git_flow('bump-prerelease', '--assume-yes')
        assert exit_code == os.EX_OK
        self.assert_refs(refs, added={
            'refs/tags/' + self.version_tag_prefix + '1.0.0-2'
        })

        self.checkout("release/1.0")
        self.assert_project_properties_contain({
            'seq': '2',
            'version': '1.0.0-2'
        })

        self.assert_refs(refs)

    def test_bump_prerelease_type_behind_branch_tip(self):
        refs = {
            'refs/heads/master',
            'refs/remotes/origin/master',
        }

        exit_code = self.git_flow('bump-major', '--assume-yes')
        assert exit_code == os.EX_OK
        self.assert_refs(refs, added={
            'refs/remotes/origin/release/1.0',
            'refs/tags/' + self.version_tag_prefix + '1.0.0-1'
        })

        self.checkout("release/1.0")
        self.assert_refs(refs, added={
            'refs/heads/release/1.0'  # local branch
        })
        self.assert_project_properties_contain({
            'seq': '1',
            'version': '1.0.0-1'
        })

        tagged_commit = self.current_head_commit()

        self.commit()
        self.push()

        exit_code = self.git_flow('bump-prerelease-type', '--assume-yes', tagged_commit)
        assert exit_code != os.EX_OK
        self.assert_refs(refs)

        self.checkout("release/1.0")

        self.commit()
        self.push()

        self.assert_project_properties_contain({
            'seq': '1',
            'version': '1.0.0-1'
        })

        self.assert_refs(refs)

    def test_bump_prerelease_type_on_superseded_version_tag(self):
        refs = {
            'refs/heads/master',
            'refs/remotes/origin/master',
        }

        exit_code = self.git_flow('bump-major', '--assume-yes')
        assert exit_code == os.EX_OK
        self.assert_refs(refs, added={
            'refs/remotes/origin/release/1.0',
            'refs/tags/' + self.version_tag_prefix + '1.0.0-1'
        })

        self.checkout("release/1.0")
        self.assert_refs(refs, added={
            'refs/heads/release/1.0'  # local branch
        })
        self.assert_project_properties_contain({
            'seq': '1',
            'version': '1.0.0-1'
        })

        tagged_commit = self.current_head_commit()

        self.commit()
        self.push()

        exit_code = self.git_flow('bump-patch', '--assume-yes')
        assert exit_code == os.EX_OK
        self.assert_refs(refs, added={
            'refs/tags/' + self.version_tag_prefix + '1.0.1-2'
        })

        self.commit()
        self.push()

        exit_code = self.git_flow('bump-prerelease-type', '--assume-yes', tagged_commit)
        assert exit_code != os.EX_OK
        self.assert_refs(refs)

        self.checkout("release/1.0")

        self.assert_project_properties_contain({
            'seq': '2',
            'version': '1.0.1-2'
        })

        self.assert_refs(refs)

    def test_discontinue_implicitly(self):
        refs = {
            'refs/heads/master',
            'refs/remotes/origin/master',
        }

        exit_code = self.git_flow('bump-major', '--assume-yes')
        assert exit_code == os.EX_OK
        self.assert_refs(refs, added={
            'refs/remotes/origin/release/1.0',
            'refs/tags/' + self.version_tag_prefix + '1.0.0-1'
        })

        self.checkout("release/1.0")
        self.assert_refs(refs, added={
            'refs/heads/release/1.0'  # local branch
        })

        exit_code = self.git_flow('discontinue', '--assume-yes')
        assert exit_code == os.EX_OK
        self.assert_refs(refs, added={
            'refs/tags/discontinued/1.0'
        })

        exit_code = self.git_flow('discontinue', '--assume-yes')
        assert exit_code == os.EX_USAGE
        self.assert_refs(refs)

        self.checkout("release/1.0")
        self.assert_project_properties_contain({
            'seq': '1',
            'version': '1.0.0-1'
        })

        self.assert_refs(refs)

    def test_discontinue_explicitly(self):
        refs = {
            'refs/heads/master',
            'refs/remotes/origin/master',
        }

        exit_code = self.git_flow('bump-major', '--assume-yes')
        assert exit_code == os.EX_OK
        self.assert_refs(refs, added={
            'refs/remotes/origin/release/1.0',
            'refs/tags/' + self.version_tag_prefix + '1.0.0-1'
        })

        exit_code = self.git_flow('discontinue', '--assume-yes', '1.0')
        assert exit_code == os.EX_OK
        self.assert_refs(refs, added={
            'refs/tags/discontinued/1.0'
        })

        exit_code = self.git_flow('discontinue', '--assume-yes', '1.0')
        assert exit_code == os.EX_USAGE
        self.assert_refs(refs)

        self.checkout("release/1.0")
        self.assert_refs(refs, added={
            'refs/heads/release/1.0'
        })
        self.assert_project_properties_contain({
            'seq': '1',
            'version': '1.0.0-1'
        })

    def test_begin_end_dev_feature(self):
        refs = {
            'refs/heads/master',
            'refs/remotes/origin/master',
        }

        self.assert_head('refs/heads/master')

        exit_code = self.git_flow('start', 'dev', 'feature', 'test-feature')
        assert exit_code == os.EX_OK
        self.assert_head('refs/heads/dev/feature/test-feature')
        self.assert_refs(refs, added={
            'refs/heads/dev/feature/test-feature'
        })

        for _ in itertools.repeat(None, 3):
            self.commit()

        self.push('-u', 'origin', 'dev/feature/test-feature')
        self.assert_refs(refs, added={
            'refs/remotes/origin/dev/feature/test-feature'
        })

        exit_code = self.git_flow('finish', 'dev', 'feature', 'test-feature')
        assert exit_code == os.EX_OK

        self.assert_head('refs/heads/master')

        self.assert_refs(refs)

    def test_begin_end_dev_feature_from_another_branch(self):
        refs = {
            'refs/heads/master',
            'refs/remotes/origin/master',
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
        self.push('-u', 'origin', 'dev/feature/test-feature')
        self.assert_refs(refs, added={
            'refs/remotes/origin/dev/feature/test-feature',
        })

        self.checkout("master")
        self.assert_head('refs/heads/master')

        exit_code = self.git_flow('finish', 'dev', 'feature', 'test-feature')
        assert exit_code == os.EX_OK

        self.assert_head('refs/heads/master')

        self.assert_refs(refs)

    def test_error_begin_dev_feature_off_a_release_branch(self):
        refs = {
            'refs/heads/master',
            'refs/remotes/origin/master',
        }

        self.assert_head('refs/heads/master')

        exit_code = self.git_flow('bump-major', '--assume-yes')
        assert exit_code == os.EX_OK
        self.assert_refs(refs, added={
            'refs/remotes/origin/release/1.0',
            'refs/tags/' + self.version_tag_prefix + '1.0.0-1'
        })

        self.assert_head('refs/heads/master')

        self.checkout('release/1.0')
        self.assert_head('refs/heads/release/1.0')
        self.assert_refs(refs, added={
            'refs/heads/release/1.0'  # local branch
        })

        exit_code = self.git_flow('start', 'dev', 'feature', 'test-feature', 'release/1.0')
        assert exit_code == os.EX_USAGE

        self.assert_head('refs/heads/release/1.0')

        self.assert_refs(refs)

    def test_begin_end_prod_fix(self):
        refs = {
            'refs/heads/master',
            'refs/remotes/origin/master',
        }

        self.assert_head('refs/heads/master')

        exit_code = self.git_flow('bump-major', '--assume-yes')
        assert exit_code == os.EX_OK
        self.assert_refs(refs, added={
            'refs/remotes/origin/release/1.0',
            'refs/tags/' + self.version_tag_prefix + '1.0.0-1'
        })

        self.assert_head('refs/heads/master')

        self.checkout('release/1.0')
        self.assert_head('refs/heads/release/1.0')
        self.assert_refs(refs, added={
            'refs/heads/release/1.0'  # local branch
        })

        exit_code = self.git_flow('start', 'prod', 'fix', 'test-fix')
        assert exit_code == os.EX_OK
        self.assert_refs(refs, added={
            'refs/heads/prod/fix/test-fix'
        })

        self.assert_head('refs/heads/prod/fix/test-fix')

        for _ in itertools.repeat(None, 3):
            self.commit()
        self.push('-u')
        self.assert_refs(refs, added={
            'refs/remotes/origin/prod/fix/test-fix'
        })

        exit_code = self.git_flow('finish', 'prod', 'fix', 'test-fix', '1.0')
        assert exit_code == os.EX_OK

        self.assert_head('refs/heads/release/1.0')
        self.assert_refs(refs)

    def test_misc(self):
        refs = {
            'refs/heads/master',
            'refs/remotes/origin/master',
        }

        self.assert_head('refs/heads/master')

        exit_code = self.git_flow('bump-major', '--assume-yes')
        assert exit_code == os.EX_OK
        self.assert_refs(refs, added={
            'refs/remotes/origin/release/1.0',
            'refs/tags/' + self.version_tag_prefix + '1.0.0-1'
        })

        self.assert_head('refs/heads/master')

        self.checkout('release/1.0')
        self.assert_head('refs/heads/release/1.0')
        self.assert_refs(refs, added={
            'refs/heads/release/1.0'  # local branch
        })
        self.assert_project_properties_contain({
            'seq': '1',
            'version': '1.0.0-1'
        })

        # hotfix
        exit_code = self.git_flow('start', 'prod', 'fix', 'test-fix')
        assert exit_code == os.EX_OK
        self.assert_refs(refs, added={
            'refs/heads/prod/fix/test-fix'
        })

        self.assert_head('refs/heads/prod/fix/test-fix')

        for _ in itertools.repeat(None, 3):
            self.commit()
        self.push('-u')
        self.assert_refs(refs, added={
            'refs/remotes/origin/prod/fix/test-fix'
        })

        exit_code = self.git_flow('finish', 'prod', 'fix', 'test-fix', '1.0')
        assert exit_code == os.EX_OK

        self.assert_head('refs/heads/release/1.0')
        self.assert_refs(refs)

        # hotfix 2 with implicit finish on work branch
        exit_code = self.git_flow('start', 'prod', 'fix', 'test-fix2')
        assert exit_code == os.EX_OK
        self.assert_refs(refs, added={
            'refs/heads/prod/fix/test-fix2'
        })

        self.assert_head('refs/heads/prod/fix/test-fix2')

        for _ in itertools.repeat(None, 3):
            self.commit()
        self.push('-u')
        self.assert_refs(refs, added={
            'refs/remotes/origin/prod/fix/test-fix2',
        })

        exit_code = self.git_flow('finish')
        assert exit_code == os.EX_OK

        self.assert_head('refs/heads/release/1.0')

        # GA release

        exit_code = self.git_flow('bump-patch', '--assume-yes', '1.0')
        assert exit_code == os.EX_OK
        self.assert_refs(refs, added={
            'refs/tags/' + self.version_tag_prefix + '1.0.1-2',
        })

        exit_code = self.git_flow('bump-prerelease-type', '--assume-yes', '1.0')
        assert exit_code == os.EX_USAGE
        exit_code = self.git_flow('bump-to-release', '--assume-yes', '1.0')
        assert exit_code == os.EX_USAGE

        self.checkout('release/1.0')
        self.assert_project_properties_contain({
            'seq': '2',
            'version': '1.0.1-2'
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
            self.commit()
        self.push('-u')
        self.assert_refs(refs, added={
            'refs/remotes/origin/dev/feature/test-feature'
        })

        exit_code = self.git_flow('finish', 'dev', 'feature', 'test-feature')
        assert exit_code == os.EX_OK

        self.assert_refs(refs)

        # new major version
        exit_code = self.git_flow('bump-major', '--assume-yes')
        assert exit_code == os.EX_OK
        self.assert_refs(refs, added={
            'refs/remotes/origin/release/2.0',
            'refs/tags/' + self.version_tag_prefix + '2.0.0-3',
        })

        self.checkout('release/2.0')
        self.assert_refs(refs, added={
            'refs/heads/release/2.0'  # local branch
        })
        self.assert_project_properties_contain({
            'seq': '3',
            'version': '2.0.0-3'
        })
