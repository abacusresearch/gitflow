from gitflow import version
from gitflow.version import VersionConfig

config = VersionConfig()
config.qualifiers = ['alpha', 'beta']


def test_major_increment():
    assert version.version_bump_major(config, "0.0.0").value == "1.0.0-alpha.1"
    assert version.version_bump_major(config, "1.0.0-beta.4").value == "2.0.0-alpha.1"


def test_minor_increment():
    assert version.version_bump_minor(config, "0.0.0").value == "0.1.0-alpha.1"
    assert version.version_bump_minor(config, "1.0.0-beta.4").value == "1.1.0-alpha.1"


def test_patch_increment():
    assert version.version_bump_patch(config, "0.0.0").value == "0.0.1-alpha.1"
    assert version.version_bump_patch(config, "1.0.0-beta.4").value == "1.0.1-alpha.1"


def test_qualifier_increment():
    assert version.version_bump_qualifier(config, "1.0.0").value is None
    assert version.version_bump_qualifier(config, "1.0.0-alpha.4").value == "1.0.0-beta.1"


def test_pre_release_increment():
    assert version.version_bump_prerelease(config, "1.0.0").value is None
    assert version.version_bump_prerelease(config, "1.0.0-alpha.4").value == "1.0.0-alpha.5"


def test_increment_to_release():
    assert version.version_bump_to_release(config, "1.0.0-alpha.4").value == "1.0.0"
