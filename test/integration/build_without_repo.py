import json
import os

from gitflow import const
from test.integration.base import TestInTempDir


class TestBuildWithoutRepo(TestInTempDir):
    git_working_copy: str = None
    project_property_file: str = None

    def setup_method(self, method):
        super().setup_method(method)

        self.git_working_copy = os.path.join(self.tempdir.name, 'exported_working_copy')
        os.makedirs(self.git_working_copy, exist_ok=True)

        # create the config file
        self.project_property_file = 'project.properties'
        config_file = os.path.join(self.git_working_copy, const.DEFAULT_CONFIG_FILE)
        with open(config_file, 'w+') as property_file:
            config = {
                const.CONFIG_VERSIONING_SCHEME: 'semverWithSeq',
                const.CONFIG_PROJECT_PROPERTY_FILE: self.project_property_file,
                const.CONFIG_VERSION_PROPERTY_NAME: 'version',
                const.CONFIG_SEQUENTIAL_VERSION_PROPERTY_NAME: 'seq',
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

            os.chdir(self.git_working_copy)

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
