import itertools
import os

from gitflow import const
from gitflow.properties import PropertyIO
from test.integration.base import TestFlowBase


class TestFlow(TestFlowBase):
    version_tag_prefix: str = const.DEFAULT_VERSION_TAG_PREFIX

    def setup_method(self, method):
        TestFlowBase.setup_method(self, method)

        # create the config file
        self.project_property_file = 'project.properties'
        config_file = os.path.join(self.git_working_copy, const.DEFAULT_CONFIG_FILE)
        config = {
            const.CONFIG_VERSIONING_SCHEME: 'semver',
            const.CONFIG_PROJECT_PROPERTY_FILE: self.project_property_file,
            const.CONFIG_VERSION_PROPERTY: 'version',
            const.CONFIG_VERSION_TYPES: ['alpha', 'beta', 'rc'],
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
        exit_code = self.git_flow('status')
        assert exit_code == os.EX_OK

    def test_log(self):
        exit_code = self.git_flow('log')
        assert exit_code == os.EX_OK

    def test_bump_major(self):
        refs = {
            'refs/heads/master': None,
            'refs/remotes/' + self.remote_name + '/master': None
        }

        exit_code = self.git_flow('bump-major', '--assume-yes')
        assert exit_code == os.EX_OK
        self.assert_refs(refs, added={
            'refs/remotes/' + self.remote_name + '/release/1.0',
            'refs/tags/' + self.version_tag_prefix + '1.0.0-alpha.1'
        })

        self.assert_project_properties_contain({
        })

        # the head commit is the base of a release branch, further bumps shall not be possible
        exit_code = self.git_flow('bump-major', '--assume-yes')
        assert exit_code == os.EX_USAGE
        self.assert_refs(refs)

        self.checkout("release/1.0")
        self.assert_refs(refs, added={
            'refs/heads/release/1.0'  # local branch
        })
        self.assert_project_properties_contain({
            'version': '1.0.0-alpha.1'
        })

    def test_bump_minor(self):
        refs = {
            'refs/heads/master': None,
            'refs/remotes/' + self.remote_name + '/master': None
        }

        exit_code = self.git_flow('bump-minor', '--assume-yes')
        assert exit_code == os.EX_OK
        self.assert_refs(refs, added={
            'refs/remotes/' + self.remote_name + '/release/1.0',
            'refs/tags/' + self.version_tag_prefix + '1.0.0-alpha.1'
        })

        # the head commit is the base of a release branch, further bumps shall not be possible
        exit_code = self.git_flow('bump-minor', '--assume-yes')
        assert exit_code == os.EX_USAGE
        self.assert_refs(refs)

        self.checkout("release/1.0")
        self.assert_refs(refs, added={
            'refs/heads/release/1.0'  # local branch
        })
        self.assert_project_properties_contain({
            'version': '1.0.0-alpha.1'
        })

        self.checkout("master")
        self.commit()
        self.push()

        exit_code = self.git_flow('bump-minor', '--assume-yes')
        assert exit_code == os.EX_OK
        self.assert_refs(refs, added={
            'refs/remotes/' + self.remote_name + '/release/1.1',
            'refs/tags/' + self.version_tag_prefix + '1.1.0-alpha.1'
        })

        self.checkout("release/1.1")
        self.assert_refs(refs, added={
            'refs/heads/release/1.1'  # local branch
        })
        self.assert_project_properties_contain({
            'version': '1.1.0-alpha.1'
        })

    def test_bump_patch(self):
        refs = {
            'refs/heads/master': None,
            'refs/remotes/' + self.remote_name + '/master': None
        }

        exit_code = self.git_flow('bump-major', '--assume-yes')
        assert exit_code == os.EX_OK
        self.assert_refs(refs, added={
            'refs/remotes/' + self.remote_name + '/release/1.0',
            'refs/tags/' + self.version_tag_prefix + '1.0.0-alpha.1'
        })

        self.checkout('release/1.0')
        self.assert_refs(refs, added={
            'refs/heads/release/1.0'  # local branch
        })

        exit_code = self.git_flow('bump-major', '--assume-yes')
        assert exit_code == os.EX_USAGE
        self.assert_refs(refs)

        head = self.commit()
        exit_code = self.git_flow('bump-patch', '--assume-yes')
        assert exit_code == os.EX_USAGE

        self.push()
        self.assert_refs(refs, updated={
            'refs/heads/release/1.0': head,
            'refs/remotes/' + self.remote_name + '/release/1.0': head
        })

        exit_code = self.git_flow('bump-patch', '--assume-yes')
        assert exit_code == os.EX_OK
        head = self.current_head()

        self.assert_refs(refs, added={
            'refs/tags/' + self.version_tag_prefix + '1.0.1-alpha.1'
        }, updated={
            'refs/heads/release/1.0': head,
            'refs/remotes/' + self.remote_name + '/release/1.0': head
        })

        self.checkout("release/1.0")
        self.assert_project_properties_contain({
            'version': '1.0.1-alpha.1'
        })

    def test_bump_patch_on_untagged_branch(self):
        refs = {
            'refs/heads/master': None,
            'refs/remotes/' + self.remote_name + '/master': None
        }

        exit_code = self.git_flow('bump-major', '--assume-yes')
        assert exit_code == os.EX_OK
        self.assert_refs(refs, added={
            'refs/remotes/' + self.remote_name + '/release/1.0',
            'refs/tags/' + self.version_tag_prefix + '1.0.0-alpha.1'
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

        exit_code = self.git_flow('bump-major', '--assume-yes')
        assert exit_code == os.EX_USAGE
        self.assert_refs(refs)

        head = self.commit()
        exit_code = self.git_flow('bump-patch', '--assume-yes')
        assert exit_code == os.EX_USAGE

        self.push()
        self.assert_refs(refs, updated={
            'refs/heads/release/1.1': head,
            'refs/remotes/' + self.remote_name + '/release/1.1': head
        })

        exit_code = self.git_flow('bump-patch', '--assume-yes')
        assert exit_code == os.EX_OK
        head = self.current_head()
        self.assert_refs(refs, added={
            'refs/tags/' + self.version_tag_prefix + '1.1.0-alpha.1'
        }, updated={
            'refs/heads/release/1.1': head,
            'refs/remotes/' + self.remote_name + '/release/1.1': head
        })

        self.assert_project_properties_contain({
            'version': '1.1.0-alpha.1'
        })

    def test_bump_prerelease_type(self):
        refs = {
            'refs/heads/master': None,
            'refs/remotes/' + self.remote_name + '/master': None
        }

        exit_code = self.git_flow('bump-major', '--assume-yes')
        assert exit_code == os.EX_OK
        self.assert_refs(refs, added={
            'refs/remotes/' + self.remote_name + '/release/1.0',
            'refs/tags/' + self.version_tag_prefix + '1.0.0-alpha.1'
        })

        self.checkout('release/1.0')
        self.assert_refs(refs, added={
            'refs/heads/release/1.0'
        })

        exit_code = self.git_flow('bump-major', '--assume-yes')
        assert exit_code == os.EX_USAGE
        self.assert_refs(refs)

        exit_code = self.git_flow('bump-prerelease-type', '--assume-yes')
        assert exit_code == os.EX_OK
        head = self.git_get_hash('release/1.0')
        self.assert_refs(refs, added={
            'refs/tags/' + self.version_tag_prefix + '1.0.0-beta.1'
        }, updated={
            'refs/heads/release/1.0': head,
            'refs/remotes/' + self.remote_name + '/release/1.0': head,
        })

        exit_code = self.git_flow('bump-prerelease-type', '--assume-yes')
        assert exit_code == os.EX_OK
        head = self.git_get_hash('release/1.0')
        self.assert_refs(refs, added={
            'refs/tags/' + self.version_tag_prefix + '1.0.0-rc.1'
        }, updated={
            'refs/heads/release/1.0': head,
            'refs/remotes/' + self.remote_name + '/release/1.0': head,
        })

        self.checkout("release/1.0")
        self.assert_project_properties_contain({
            'version': '1.0.0-rc.1'
        })

    def test_bump_to_release(self):
        refs = {
            'refs/heads/master': None,
            'refs/remotes/' + self.remote_name + '/master': None
        }

        exit_code = self.git_flow('bump-major', '--assume-yes')
        assert exit_code == os.EX_OK
        self.assert_refs(refs, added={
            'refs/remotes/' + self.remote_name + '/release/1.0',
            'refs/tags/' + self.version_tag_prefix + '1.0.0-alpha.1'
        })

        self.checkout('release/1.0')
        self.assert_refs(refs, added={
            'refs/heads/release/1.0'  # local branch
        })

        exit_code = self.git_flow('bump-major', '--assume-yes')
        assert exit_code == os.EX_USAGE
        self.assert_refs(refs)

        exit_code = self.git_flow('bump-prerelease-type', '--assume-yes')
        assert exit_code == os.EX_OK
        head = self.git_get_hash('release/1.0')
        self.assert_refs(refs, added={
            'refs/tags/' + self.version_tag_prefix + '1.0.0-beta.1'
        }, updated={
            'refs/heads/release/1.0': head,
            'refs/remotes/' + self.remote_name + '/release/1.0': head,
        })

        exit_code = self.git_flow('bump-to-release', '--assume-yes')
        assert exit_code == os.EX_OK
        head = self.git_get_hash('release/1.0')
        self.assert_refs(refs, added={
            'refs/tags/' + self.version_tag_prefix + '1.0.0'
        }, updated={
            'refs/heads/release/1.0': head,
            'refs/remotes/' + self.remote_name + '/release/1.0': head,
        })

        self.checkout("release/1.0")
        self.assert_project_properties_contain({
            'version': '1.0.0'
        })

    def test_bump_prerelease(self):
        refs = {
            'refs/heads/master': None,
            'refs/remotes/' + self.remote_name + '/master': None
        }

        exit_code = self.git_flow('bump-major', '--assume-yes')
        assert exit_code == os.EX_OK
        self.assert_refs(refs, added={
            'refs/remotes/' + self.remote_name + '/release/1.0',
            'refs/tags/' + self.version_tag_prefix + '1.0.0-alpha.1'
        })

        self.checkout("release/1.0")
        self.assert_refs(refs, added={
            'refs/heads/release/1.0'
        })
        self.assert_project_properties_contain({
            'version': '1.0.0-alpha.1'
        })

        head = self.commit()
        exit_code = self.git_flow('bump-prerelease', '--assume-yes')
        assert exit_code == os.EX_USAGE
        self.assert_refs(refs, updated={
            'refs/heads/release/1.0': head
        })

        self.push()

        exit_code = self.git_flow('bump-prerelease', '--assume-yes')
        assert exit_code == os.EX_OK
        head = self.current_head()
        self.assert_refs(refs, added={
            'refs/tags/' + self.version_tag_prefix + '1.0.0-alpha.2'
        }, updated={
            'refs/heads/release/1.0': head,
            'refs/remotes/' + self.remote_name + '/release/1.0': head
        })

        self.checkout("release/1.0")
        self.assert_project_properties_contain({
            'version': '1.0.0-alpha.2'
        })

    def test_bump_prerelease_type_on_superseded_version_tag(self):
        refs = {
            'refs/heads/master': None,
            'refs/remotes/' + self.remote_name + '/master': None
        }

        exit_code = self.git_flow('bump-major', '--assume-yes')
        assert exit_code == os.EX_OK
        self.assert_refs(refs, added={
            'refs/remotes/' + self.remote_name + '/release/1.0',
            'refs/tags/' + self.version_tag_prefix + '1.0.0-alpha.1'
        })

        self.checkout("release/1.0")
        self.assert_refs(refs, added={
            'refs/heads/release/1.0'  # local branch
        })

        self.assert_project_properties_contain({
            'version': '1.0.0-alpha.1'
        })

        tagged_commit = self.current_head_commit()

        self.commit()
        self.push()

        exit_code = self.git_flow('bump-patch', '--assume-yes')
        assert exit_code == os.EX_OK
        head = self.current_head()
        self.assert_refs(refs, added={
            'refs/tags/' + self.version_tag_prefix + '1.0.1-alpha.1',
        }, updated={
            'refs/heads/release/1.0': head,
            'refs/remotes/' + self.remote_name + '/release/1.0': head
        })

        self.commit()
        self.push()

        exit_code = self.git_flow('bump-prerelease-type', '--assume-yes', tagged_commit)
        assert exit_code == os.EX_USAGE
        head = self.current_head()
        self.assert_refs(refs, updated={
            'refs/heads/release/1.0': head,
            'refs/remotes/' + self.remote_name + '/release/1.0': head
        })

        self.checkout("release/1.0")

        self.assert_project_properties_contain({
            'version': '1.0.1-alpha.1'
        })

    def test_discontinue_implicitly(self):
        refs = {
            'refs/heads/master': None,
            'refs/remotes/' + self.remote_name + '/master': None
        }

        exit_code = self.git_flow('bump-major', '--assume-yes')
        assert exit_code == os.EX_OK
        self.assert_refs(refs, added={
            'refs/remotes/' + self.remote_name + '/release/1.0',
            'refs/tags/' + self.version_tag_prefix + '1.0.0-alpha.1'
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
            'version': '1.0.0-alpha.1'
        })

    def test_discontinue_explicitly(self):
        refs = {
            'refs/heads/master': None,
            'refs/remotes/' + self.remote_name + '/master': None
        }

        exit_code = self.git_flow('bump-major', '--assume-yes')
        assert exit_code == os.EX_OK
        self.assert_refs(refs, added={
            'refs/remotes/' + self.remote_name + '/release/1.0',
            'refs/tags/' + self.version_tag_prefix + '1.0.0-alpha.1'
        })

        exit_code = self.git_flow('discontinue', '--assume-yes', '1.0')
        assert exit_code == os.EX_OK
        self.assert_refs(refs, added={
            'refs/tags/discontinued/1.0',
        })

        exit_code = self.git_flow('discontinue', '--assume-yes', '1.0')
        assert exit_code == os.EX_USAGE
        self.assert_refs(refs)

        self.checkout("release/1.0")
        self.assert_refs(refs, added={
            'refs/heads/release/1.0',
        })
        self.assert_project_properties_contain({
            'version': '1.0.0-alpha.1'
        })

    def test_begin_end_dev_feature(self):
        refs = {
            'refs/heads/master': None,
            'refs/remotes/' + self.remote_name + '/master': None
        }

        self.assert_head('refs/heads/master')

        exit_code = self.git_flow('start', 'dev', 'feature', 'test-feature')
        assert exit_code == os.EX_OK

        self.assert_head('refs/heads/dev/feature/test-feature')

        for _ in itertools.repeat(None, 3):
            self.commit()
        self.push('-u', self.remote_name, 'dev/feature/test-feature')
        exit_code = self.git_flow('finish', 'dev', 'feature', 'test-feature')
        assert exit_code == os.EX_OK

        self.assert_head('refs/heads/master')

    def test_begin_end_prod_fix(self):
        refs = {
            'refs/heads/master': None,
            'refs/remotes/' + self.remote_name + '/master': None
        }

        self.assert_head('refs/heads/master')

        exit_code = self.git_flow('bump-major', '--assume-yes')
        assert exit_code == os.EX_OK
        self.assert_refs(refs, added={
            'refs/remotes/' + self.remote_name + '/release/1.0',
            'refs/tags/' + self.version_tag_prefix + '1.0.0-alpha.1'
        })

        self.assert_head('refs/heads/master')

        self.checkout('release/1.0')
        self.assert_refs(refs, added={
            'refs/heads/release/1.0'  # local branch
        })
        self.assert_head('refs/heads/release/1.0')

        exit_code = self.git_flow('start', 'prod', 'fix', 'test-fix')
        assert exit_code == os.EX_OK
        self.assert_refs(refs, added={
            'refs/heads/prod/fix/test-fix'
        })

        self.assert_head('refs/heads/prod/fix/test-fix')

        for _ in itertools.repeat(None, 3):
            head = self.commit()
        self.push('-u')
        self.assert_refs(refs, added={
            'refs/remotes/' + self.remote_name + '/prod/fix/test-fix': head
        }, updated={
            'refs/heads/prod/fix/test-fix': head
        })

        exit_code = self.git_flow('finish', 'prod', 'fix', 'test-fix', '1.0')
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
            'refs/remotes/' + self.remote_name + '/master': None
        }

        self.assert_head('refs/heads/master')

        exit_code = self.git_flow('bump-major', '--assume-yes')
        assert exit_code == os.EX_OK
        self.assert_refs(refs, added={
            'refs/remotes/' + self.remote_name + '/release/1.0',
            'refs/tags/' + self.version_tag_prefix + '1.0.0-alpha.1'
        })

        self.assert_head('refs/heads/master')

        self.checkout('release/1.0')
        self.assert_refs(refs, added={
            'refs/heads/release/1.0'  # local branch
        })

        self.assert_head('refs/heads/release/1.0')
        self.assert_project_properties_contain({
            'version': '1.0.0-alpha.1'
        })

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

        self.assert_head('refs/heads/release/1.0')
        head = self.current_head()
        self.assert_refs(refs, updated={
            'refs/heads/release/1.0': head,
            'refs/remotes/' + self.remote_name + '/release/1.0': head
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
        self.assert_refs(refs, added={
            'refs/remotes/' + self.remote_name + '/prod/fix/test-fix2': head
        }, updated={
            'refs/heads/prod/fix/test-fix2': head,
        })

        exit_code = self.git_flow('finish')
        assert exit_code == os.EX_OK

        self.assert_head('refs/heads/release/1.0')

        # GA release

        exit_code = self.git_flow('bump-patch', '--assume-yes', '1.0')
        assert exit_code == os.EX_OK
        head = self.current_head()
        self.assert_refs(refs, added={
            'refs/tags/' + self.version_tag_prefix + '1.0.1-alpha.1',
        }, updated={
            'refs/heads/release/1.0': head,
            'refs/remotes/' + self.remote_name + '/release/1.0': head
        })

        exit_code = self.git_flow('bump-prerelease-type', '--assume-yes', '1.0')
        assert exit_code == os.EX_OK
        head = self.current_head()
        self.assert_refs(refs, added={
            'refs/tags/' + self.version_tag_prefix + '1.0.1-beta.1',
        }, updated={
            'refs/heads/release/1.0': head,
            'refs/remotes/' + self.remote_name + '/release/1.0': head
        })

        exit_code = self.git_flow('bump-to-release', '--assume-yes', '1.0')
        assert exit_code == os.EX_OK
        head = self.current_head()
        self.assert_refs(refs, added={
            'refs/tags/' + self.version_tag_prefix + '1.0.1',
        }, updated={
            'refs/heads/release/1.0': head,
            'refs/remotes/' + self.remote_name + '/release/1.0': head
        })

        self.checkout('release/1.0')
        self.assert_project_properties_contain({
            'version': '1.0.1'
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
        self.assert_refs(refs, added={
            'refs/remotes/' + self.remote_name + '/dev/feature/test-feature',
        }, updated={
            'refs/heads/dev/feature/test-feature': head
        })

        exit_code = self.git_flow('finish', 'dev', 'feature', 'test-feature')
        assert exit_code == os.EX_OK

        self.assert_refs(refs)

        # new major version
        exit_code = self.git_flow('bump-major', '--assume-yes')
        assert exit_code == os.EX_OK
        self.assert_refs(refs, added={
            'refs/remotes/' + self.remote_name + '/release/2.0',
            'refs/tags/' + self.version_tag_prefix + '2.0.0-alpha.1',
        })

        self.checkout('release/2.0')
        self.assert_project_properties_contain({
            'version': '2.0.0-alpha.1'
        })
        self.assert_refs(refs, added={
            'refs/heads/release/2.0'
        })
