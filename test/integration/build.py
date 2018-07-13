import json
import os

import pytest

from gitflow import const
from test.integration.base import TestFlowBase


@pytest.mark.slow
class TestBuild(TestFlowBase):
    def setup_method(self, method):
        TestFlowBase.setup_method(self, method)

        # create the config file
        self.project_property_file = 'project.properties'
        config_file = os.path.join(self.git_working_copy, const.DEFAULT_CONFIG_FILE)
        with open(config_file, 'w+') as property_file:
            config = {
                const.CONFIG_VERSIONING_SCHEME: 'semverWithSeq',
                const.CONFIG_PROJECT_PROPERTY_FILE: self.project_property_file,
                const.CONFIG_VERSION_PROPERTY: 'version',
                const.CONFIG_SEQUENCE_NUMBER_PROPERTY: 'seq',
                const.CONFIG_BUILD: {
                    'stages': {
                        'assemble': [['echo', 'assemble#1']],
                        'test': {
                            'steps': {
                                'app': [
                                    ['echo', 'test#1'],
                                    ['echo', '\\$HOME: $HOME'],
                                    ['echo', '\\\\\\$HOME: \\$HOME'],
                                    ['echo', '\\\\\\\\\\$HOME: \\\\$HOME'],
                                    ['echo', '\\${HOME}: ${HOME}'],
                                    ['echo', '\\\\\\${HOME}: \\${HOME}'],
                                    ['echo', '\\\\\\\\\\${HOME}: \\\\${HOME}']
                                ]
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

        self.assert_refs({
            'refs/heads/master',
            'refs/remotes/origin/master'
        })

    def test_assemble(self):
        exit_code, out_lines = self.git_flow_for_lines('assemble')

        assert exit_code == os.EX_OK
        assert out_lines == [
            "assemble:#: OK"
        ]

    def test_assemble_inplace(self):
        exit_code, out_lines = self.git_flow_for_lines('assemble', '--inplace')

        assert exit_code == os.EX_OK
        assert out_lines == [
            "assemble:#: OK"
        ]

    def test_test(self):
        exit_code, out_lines = self.git_flow_for_lines('test')

        assert exit_code == os.EX_OK
        assert out_lines == [
            "test:app: OK"
        ]

    def test_integration_test(self):
        exit_code, out_lines = self.git_flow_for_lines('integration-test')

        assert exit_code == os.EX_OK
        assert out_lines == [
            "google_testing_lab:monkey_test: OK",
            "google_testing_lab:instrumentation_test: OK"
        ]
