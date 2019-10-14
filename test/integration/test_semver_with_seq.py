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

            const.CONFIG_VERSIONING_SCHEME: 'semverWithSeq',
            const.CONFIG_PROJECT_PROPERTY_FILE: self.project_property_file,
            const.CONFIG_VERSION_PROPERTY: 'version',
            const.CONFIG_SEQUENCE_NUMBER_PROPERTY: 'seq',
            const.CONFIG_VERSION_TAG_PREFIX: ''
        }

        PropertyIO.write_file(config_file, config)

        self.version_tag_prefix = config.get(const.CONFIG_VERSION_TAG_PREFIX,
                                             const.DEFAULT_VERSION_TAG_PREFIX) or ''

        # create & push the initial commit
        self.add(config_file)
        self.commit('initial commit: gitflow config file')
        self.push()

        self.assert_refs({
            'refs/heads/master': None,
            'refs/remotes/' + self.remote_name + '/master': None
        })

    def test_status(self):
        exit_code, out, err = self.git_flow('status')
        assert exit_code == os.EX_OK

    def test_log(self):
        exit_code, out, err = self.git_flow('log')
        assert exit_code == os.EX_OK

    def test_bump_major(self):
        refs = dict()
        self.assert_refs(refs, added={
            'refs/heads/master',
            'refs/remotes/' + self.remote_name + '/master'
        })

        exit_code, out, err = self.git_flow('bump-major', '--assume-yes')
        assert exit_code == os.EX_OK
        self.assert_refs(refs, added={
            'refs/remotes/' + self.remote_name + '/release/1.0': None,
            'refs/tags/' + self.version_tag_prefix + '1.0.0-1': 'refs/remotes/' + self.remote_name + '/release/1.0'
        })

        self.assert_first_parent('refs/remotes/' + self.remote_name + '/release/1.0', 'refs/heads/master')
        self.assert_project_properties_contain({
        })

        # the head commit is the base of a release branch, further bumps shall not be possible
        exit_code, out, err = self.git_flow('bump-major', '--assume-yes')
        assert exit_code == os.EX_USAGE
        self.assert_refs(refs)

        self.checkout("release/1.0")
        self.assert_refs(refs, added={
            'refs/heads/release/1.0': 'refs/remotes/' + self.remote_name + '/release/1.0'
        })
        self.assert_project_properties_contain({
            'seq': '1',
            'version': '1.0.0-1',
        })

    def test_bump_minor(self):
        refs = {
            'refs/heads/master': None,
            'refs/remotes/' + self.remote_name + '/master': None,
        }

        exit_code, out, err = self.git_flow('bump-minor', '--assume-yes')
        assert exit_code == os.EX_OK
        self.assert_refs(refs, added={
            'refs/remotes/' + self.remote_name + '/release/1.0',
            'refs/tags/' + self.version_tag_prefix + '1.0.0-1'
        })

        # the head commit is the base of a release branch, further bumps shall not be possible
        exit_code, out, err = self.git_flow('bump-minor', '--assume-yes')
        assert exit_code == os.EX_USAGE
        self.assert_refs(refs)

        self.checkout("release/1.0")
        self.assert_project_properties_contain({
            'seq': '1',
            'version': '1.0.0-1'
        })

        self.checkout("master")
        self.commit()
        self.push()

        exit_code, out, err = self.git_flow('bump-minor', '--assume-yes')
        assert exit_code == os.EX_OK
        self.assert_refs(refs, added={
            'refs/heads/release/1.0',  # local branch

            'refs/remotes/' + self.remote_name + '/release/1.1',
            'refs/tags/' + self.version_tag_prefix + '1.1.0-2'
        })

        self.checkout("release/1.1")
        self.assert_refs(refs, added={
            'refs/heads/release/1.1'  # local branch
        })
        self.assert_project_properties_contain({
            'seq': '2',
            'version': '1.1.0-2'
        })

    def test_bump_patch(self):
        refs = {
            'refs/heads/master': None,
            'refs/remotes/' + self.remote_name + '/master': None,
        }

        exit_code, out, err = self.git_flow('bump-major', '--assume-yes')
        assert exit_code == os.EX_OK
        self.assert_refs(refs, added={
            'refs/remotes/' + self.remote_name + '/release/1.0',
            'refs/tags/' + self.version_tag_prefix + '1.0.0-1'
        })

        self.checkout('release/1.0')
        self.assert_refs(refs, added={
            'refs/heads/release/1.0'  # local branch
        })

        exit_code, out, err = self.git_flow('bump-major', '--assume-yes')
        assert exit_code == os.EX_USAGE
        self.assert_refs(refs)

        self.commit()
        exit_code, out, err = self.git_flow('bump-patch', '--assume-yes')
        assert exit_code == os.EX_USAGE
        head = self.current_head()
        self.assert_refs(refs, updated={
            'refs/heads/release/1.0': head
        })

        self.push()
        exit_code, out, err = self.git_flow('bump-patch', '--assume-yes')
        assert exit_code == os.EX_OK
        head = self.current_head()
        self.assert_refs(refs, added={
            'refs/tags/' + self.version_tag_prefix + '1.0.1-2'
        }, updated={
            'refs/heads/release/1.0': head,
            'refs/remotes/' + self.remote_name + '/release/1.0': head
        })

        self.checkout("release/1.0")
        self.assert_project_properties_contain({
            'seq': '2',
            'version': '1.0.1-2'
        })

        self.assert_refs(refs)

    def test_bump_patch_on_untagged_branch(self):
        refs = {
            'refs/heads/master': None,
            'refs/remotes/' + self.remote_name + '/master': None
        }

        exit_code, out, err = self.git_flow('bump-major', '--assume-yes')
        assert exit_code == os.EX_OK
        self.assert_refs(refs, added={
            'refs/remotes/' + self.remote_name + '/release/1.0',
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
            'refs/remotes/' + self.remote_name + '/release/1.1'  # remote branch
        })

        exit_code, out, err = self.git_flow('bump-major', '--assume-yes')
        assert exit_code == os.EX_USAGE
        self.assert_refs(refs)

        self.commit()
        exit_code, out, err = self.git_flow('bump-patch', '--assume-yes')
        assert exit_code == os.EX_USAGE
        head = self.current_head()

        self.push()
        self.assert_refs(refs, updated={
            'refs/remotes/' + self.remote_name + '/release/1.1': head,
            'refs/heads/release/1.1': head,
        })

        exit_code, out, err = self.git_flow('bump-patch', '--assume-yes')
        assert exit_code == os.EX_OK
        head = self.current_head()
        self.assert_refs(refs, added={
            'refs/tags/' + self.version_tag_prefix + '1.1.0-2'
        }, updated={
            'refs/heads/release/1.1': head,
            'refs/remotes/' + self.remote_name + '/release/1.1': head
        })

        self.assert_project_properties_contain({
            'seq': '2',
            'version': '1.1.0-2'
        })

    def test_bump_prerelease_type(self):
        refs = {
            'refs/heads/master': None,
            'refs/remotes/' + self.remote_name + '/master': None,
        }

        exit_code, out, err = self.git_flow('bump-major', '--assume-yes')
        assert exit_code == os.EX_OK
        self.assert_refs(refs, added={
            'refs/remotes/' + self.remote_name + '/release/1.0',
            'refs/tags/' + self.version_tag_prefix + '1.0.0-1'
        })

        self.checkout('release/1.0')
        self.assert_refs(refs, added={
            'refs/heads/release/1.0',  # local branch
        })

        exit_code, out, err = self.git_flow('bump-major', '--assume-yes')
        assert exit_code == os.EX_USAGE

        exit_code, out, err = self.git_flow('bump-prerelease-type', '--assume-yes')
        assert exit_code != os.EX_OK
        exit_code, out, err = self.git_flow('bump-prerelease-type', '--assume-yes')
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
            'refs/heads/master': None,
            'refs/remotes/' + self.remote_name + '/master': None,
        }

        exit_code, out, err = self.git_flow('bump-major', '--assume-yes')
        assert exit_code == os.EX_OK
        self.assert_refs(refs, added={
            'refs/remotes/' + self.remote_name + '/release/1.0',
            'refs/tags/' + self.version_tag_prefix + '1.0.0-1'
        })

        self.checkout('release/1.0')
        self.assert_refs(refs, added={
            'refs/heads/release/1.0',  # local branch
        })

        exit_code, out, err = self.git_flow('bump-major', '--assume-yes')
        assert exit_code == os.EX_USAGE
        self.assert_refs(refs)

        exit_code, out, err = self.git_flow('bump-prerelease-type', '--assume-yes')
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
            'refs/heads/master': None,
            'refs/remotes/' + self.remote_name + '/master': None,
        }

        exit_code, out, err = self.git_flow('bump-major', '--assume-yes')
        assert exit_code == os.EX_OK
        self.assert_refs(refs, added={
            'refs/remotes/' + self.remote_name + '/release/1.0',
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

        exit_code, out, err = self.git_flow('bump-prerelease', '--assume-yes')
        assert exit_code == os.EX_USAGE

        self.push()

        exit_code, out, err = self.git_flow('bump-prerelease', '--assume-yes')
        assert exit_code == os.EX_OK
        head = self.current_head()
        self.assert_refs(refs, added={
            'refs/tags/' + self.version_tag_prefix + '1.0.0-2'
        }, updated={
            'refs/heads/release/1.0': head,
            'refs/remotes/' + self.remote_name + '/release/1.0': head
        })

        self.checkout("release/1.0")
        self.assert_project_properties_contain({
            'seq': '2',
            'version': '1.0.0-2'
        })

        self.assert_refs(refs)

    def test_bump_prerelease_type_behind_branch_tip(self):
        refs = {
            'refs/heads/master': None,
            'refs/remotes/' + self.remote_name + '/master': None,
        }

        exit_code, out, err = self.git_flow('bump-major', '--assume-yes')
        assert exit_code == os.EX_OK
        self.assert_refs(refs, added={
            'refs/remotes/' + self.remote_name + '/release/1.0',
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

        head = self.commit()
        self.push()

        exit_code, out, err = self.git_flow('bump-prerelease-type', '--assume-yes', tagged_commit)
        assert exit_code != os.EX_OK
        self.assert_refs(refs, updated={
            'refs/heads/release/1.0': head,
            'refs/remotes/' + self.remote_name + '/release/1.0': head
        })

        self.checkout("release/1.0")

        head = self.commit()
        self.push()

        self.assert_project_properties_contain({
            'seq': '1',
            'version': '1.0.0-1'
        })

        self.assert_refs(refs, updated={
            'refs/heads/release/1.0': head,
            'refs/remotes/' + self.remote_name + '/release/1.0': head
        })

    def test_bump_prerelease_type_on_superseded_version_tag(self):
        refs = {
            'refs/heads/master': None,
            'refs/remotes/' + self.remote_name + '/master': None,
        }

        exit_code, out, err = self.git_flow('bump-major', '--assume-yes')
        assert exit_code == os.EX_OK
        self.assert_refs(refs, added={
            'refs/remotes/' + self.remote_name + '/release/1.0',
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

        exit_code, out, err = self.git_flow('bump-patch', '--assume-yes')
        assert exit_code == os.EX_OK
        head = self.current_head()
        self.assert_refs(refs, added={
            'refs/tags/' + self.version_tag_prefix + '1.0.1-2'
        }, updated={
            'refs/heads/release/1.0': head,
            'refs/remotes/' + self.remote_name + '/release/1.0': head
        })

        head = self.commit()
        self.push()

        exit_code, out, err = self.git_flow('bump-prerelease-type', '--assume-yes', tagged_commit)
        assert exit_code != os.EX_OK
        self.assert_refs(refs, updated={
            'refs/heads/release/1.0': head,
            'refs/remotes/' + self.remote_name + '/release/1.0': head
        })

        self.checkout("release/1.0")

        self.assert_project_properties_contain({
            'seq': '2',
            'version': '1.0.1-2'
        })

        self.assert_refs(refs)

    def test_discontinue_implicitly(self):
        refs = {
            'refs/heads/master': None,
            'refs/remotes/' + self.remote_name + '/master': None,
        }

        exit_code, out, err = self.git_flow('bump-major', '--assume-yes')
        assert exit_code == os.EX_OK
        self.assert_refs(refs, added={
            'refs/remotes/' + self.remote_name + '/release/1.0',
            'refs/tags/' + self.version_tag_prefix + '1.0.0-1'
        })

        self.checkout("release/1.0")
        self.assert_refs(refs, added={
            'refs/heads/release/1.0'  # local branch
        })

        exit_code, out, err = self.git_flow('discontinue', '--assume-yes')
        assert exit_code == os.EX_OK
        self.assert_refs(refs, added={
            'refs/tags/discontinued/1.0'
        })

        exit_code, out, err = self.git_flow('discontinue', '--assume-yes')
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
            'refs/heads/master': None,
            'refs/remotes/' + self.remote_name + '/master': None,
        }

        exit_code, out, err = self.git_flow('bump-major', '--assume-yes')
        assert exit_code == os.EX_OK
        self.assert_refs(refs, added={
            'refs/remotes/' + self.remote_name + '/release/1.0',
            'refs/tags/' + self.version_tag_prefix + '1.0.0-1'
        })

        exit_code, out, err = self.git_flow('discontinue', '--assume-yes', '1.0')
        assert exit_code == os.EX_OK
        self.assert_refs(refs, added={
            'refs/tags/discontinued/1.0'
        })

        exit_code, out, err = self.git_flow('discontinue', '--assume-yes', '1.0')
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
            'refs/heads/master': None,
            'refs/remotes/' + self.remote_name + '/master': None,
        }

        self.assert_head('refs/heads/master')

        exit_code, out, err = self.git_flow('start', 'dev', 'feature', 'test-feature')
        assert exit_code == os.EX_OK
        self.assert_head('refs/heads/dev/feature/test-feature')
        self.assert_refs(refs, added={
            'refs/heads/dev/feature/test-feature'
        })

        head = self.checkout_commit_and_push(refs=refs, local_branch_name='refs/heads/dev/feature/test-feature')

        exit_code, out, err = self.git_flow('finish', 'dev', 'feature', 'test-feature')
        assert exit_code == os.EX_OK

        self.assert_head('refs/heads/master')

        self.assert_refs(refs)

    def test_begin_end_dev_feature_from_another_branch(self):
        refs = {
            'refs/heads/master': None,
            'refs/remotes/' + self.remote_name + '/master': None,
        }

        self.assert_head('refs/heads/master')

        exit_code, out, err = self.git_flow('start', 'dev', 'feature', 'test-feature')
        assert exit_code == os.EX_OK

        self.assert_head('refs/heads/dev/feature/test-feature')

        self.assert_refs(refs, added={
            'refs/heads/dev/feature/test-feature',
        })

        head = self.checkout_commit_and_push(refs=refs, local_branch_name='refs/heads/dev/feature/test-feature')

        self.checkout("master")
        self.assert_head('refs/heads/master')

        exit_code, out, err = self.git_flow('finish', 'dev', 'feature', 'test-feature')
        assert exit_code == os.EX_OK

        self.assert_head('refs/heads/master')

        self.assert_refs(refs)

    def test_error_begin_dev_feature_off_a_release_branch(self):
        refs = {
            'refs/heads/master': None,
            'refs/remotes/' + self.remote_name + '/master': None,
        }

        self.assert_head('refs/heads/master')

        exit_code, out, err = self.git_flow('bump-major', '--assume-yes')
        assert exit_code == os.EX_OK
        self.assert_refs(refs, added={
            'refs/remotes/' + self.remote_name + '/release/1.0',
            'refs/tags/' + self.version_tag_prefix + '1.0.0-1'
        })

        self.assert_head('refs/heads/master')

        self.checkout('release/1.0')
        self.assert_head('refs/heads/release/1.0')
        self.assert_refs(refs, added={
            'refs/heads/release/1.0'  # local branch
        })

        exit_code, out, err = self.git_flow('start', 'dev', 'feature', 'test-feature', 'release/1.0')
        assert exit_code == os.EX_USAGE

        self.assert_head('refs/heads/release/1.0')

        self.assert_refs(refs)

    def test_begin_end_prod_fix(self):
        refs = {
            'refs/heads/master': None,
            'refs/remotes/' + self.remote_name + '/master': None,
        }

        self.assert_head('refs/heads/master')

        exit_code, out, err = self.git_flow('bump-major', '--assume-yes')
        assert exit_code == os.EX_OK
        self.assert_refs(refs, added={
            'refs/remotes/' + self.remote_name + '/release/1.0',
            'refs/tags/' + self.version_tag_prefix + '1.0.0-1'
        })

        self.assert_head('refs/heads/master')

        self.checkout('release/1.0')
        self.assert_head('refs/heads/release/1.0')
        self.assert_refs(refs, added={
            'refs/heads/release/1.0'  # local branch
        })

        exit_code, out, err = self.git_flow('start', 'prod', 'fix', 'test-fix')
        assert exit_code == os.EX_OK
        self.assert_refs(refs, added={
            'refs/heads/prod/fix/test-fix'
        })

        self.assert_head('refs/heads/prod/fix/test-fix')

        head = self.checkout_commit_and_push(refs=refs, local_branch_name='refs/heads/prod/fix/test-fix')

        exit_code, out, err = self.git_flow('finish', 'prod', 'fix', 'test-fix', '1.0')
        assert exit_code == os.EX_OK

        head = self.current_head()

        self.assert_head('refs/heads/release/1.0')
        self.assert_refs(refs, updated={
            'refs/heads/release/1.0': head,
            'refs/remotes/' + self.remote_name + '/release/1.0': head
        })

    def test_misc(self):
        refs = {
            'refs/heads/master': None,
            'refs/remotes/' + self.remote_name + '/master': None,
        }

        self.assert_head('refs/heads/master')

        exit_code, out, err = self.git_flow('bump-major', '--assume-yes')
        assert exit_code == os.EX_OK
        self.assert_refs(refs, added={
            'refs/remotes/' + self.remote_name + '/release/1.0',
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
        exit_code, out, err = self.git_flow('start', 'prod', 'fix', 'test-fix')
        assert exit_code == os.EX_OK
        self.assert_refs(refs, added={
            'refs/heads/prod/fix/test-fix'
        })

        self.assert_head('refs/heads/prod/fix/test-fix')

        head = self.checkout_commit_and_push(refs=refs, local_branch_name='refs/heads/prod/fix/test-fix')

        exit_code, out, err = self.git_flow('finish', 'prod', 'fix', 'test-fix', '1.0')
        assert exit_code == os.EX_OK

        head = self.current_head()

        self.assert_head('refs/heads/release/1.0')
        self.assert_refs(refs, updated={
            'refs/heads/release/1.0': head,
            'refs/remotes/' + self.remote_name + '/release/1.0': head
        })

        # hotfix 2 with implicit finish on work branch
        exit_code, out, err = self.git_flow('start', 'prod', 'fix', 'test-fix2')
        assert exit_code == os.EX_OK
        self.assert_refs(refs, added={
            'refs/heads/prod/fix/test-fix2'
        })

        self.assert_head('refs/heads/prod/fix/test-fix2')

        head = self.checkout_commit_and_push(refs=refs, local_branch_name='refs/heads/prod/fix/test-fix2')

        exit_code, out, err = self.git_flow('finish')
        assert exit_code == os.EX_OK
        head = self.current_head()
        self.assert_refs(refs, updated={
            'refs/heads/release/1.0': head,
            'refs/remotes/' + self.remote_name + '/release/1.0': head
        })

        self.assert_head('refs/heads/release/1.0')

        # GA release

        exit_code, out, err = self.git_flow('bump-patch', '--assume-yes', '1.0')
        assert exit_code == os.EX_OK
        head = self.current_head()
        self.assert_refs(refs, updated={
            'refs/heads/release/1.0': head,
            'refs/remotes/' + self.remote_name + '/release/1.0': head
        }, added={
            'refs/tags/' + self.version_tag_prefix + '1.0.1-2': head,
        })

        exit_code, out, err = self.git_flow('bump-prerelease-type', '--assume-yes', '1.0')
        assert exit_code == os.EX_USAGE
        exit_code, out, err = self.git_flow('bump-to-release', '--assume-yes', '1.0')
        assert exit_code == os.EX_USAGE

        self.checkout('release/1.0')
        self.assert_project_properties_contain({
            'seq': '2',
            'version': '1.0.1-2'
        })

        # new feature

        self.checkout('master')
        self.assert_head('refs/heads/master')

        exit_code, out, err = self.git_flow('start', 'dev', 'feature', 'test-feature')
        assert exit_code == os.EX_OK
        self.assert_refs(refs, added={
            'refs/heads/dev/feature/test-feature'
        })

        self.assert_head('refs/heads/dev/feature/test-feature')

        head = self.checkout_commit_and_push(refs=refs, local_branch_name='refs/heads/dev/feature/test-feature')

        exit_code, out, err = self.git_flow('finish', 'dev', 'feature', 'test-feature')
        assert exit_code == os.EX_OK

        self.assert_refs(refs)

        # new major version
        exit_code, out, err = self.git_flow('bump-major', '--assume-yes')
        assert exit_code == os.EX_OK
        self.assert_refs(refs, added={
            'refs/remotes/' + self.remote_name + '/release/2.0',
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
