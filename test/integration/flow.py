import os
import subprocess
from tempfile import TemporaryDirectory

from gitflow import __main__


class TestFlow:
    tempdir: TemporaryDirectory

    def setup_method(self, method):
        self.tempdir = TemporaryDirectory()

        os.chdir(self.tempdir.name)

        proc = subprocess.Popen(args=['git', 'init'])
        proc.wait()
        assert proc.returncode == os.EX_OK

        with open(os.path.join(self.tempdir.name, 'gitflow.properties'), 'w') as property_file:
            property_file.write('')

        pass

    def teardown_method(self, method):
        self.tempdir.cleanup()
        pass

    def test_status(self):
        exit_code = __main__.main([__name__, 'status'])
        assert exit_code == os.EX_OK
        pass
