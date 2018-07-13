from gitflow.const import VersioningScheme
from gitflow.procedures.scheme import scheme_procedures
from gitflow.version import VersionConfig

config = VersionConfig()
config.versioning_scheme = VersioningScheme.SEMVER_WITH_SEQ


def test_major_increment():
    assert scheme_procedures.version_bump_major(config, None, None).value == "0.0.0-1"
    assert scheme_procedures.version_bump_major(config, "0.0.0-1", None).value is None
    assert scheme_procedures.version_bump_major(config, "0.0.0-1", 1).value == "1.0.0-2"
    assert scheme_procedures.version_bump_major(config, "0.0.0-1", 5).value == "1.0.0-6"


def test_minor_increment():
    assert scheme_procedures.version_bump_minor(config, None, None).value == "0.0.0-1"
    assert scheme_procedures.version_bump_minor(config, "0.0.0-1", None).value is None
    assert scheme_procedures.version_bump_minor(config, "0.0.0-1", 1).value == "0.1.0-2"


def test_patch_increment():
    assert scheme_procedures.version_bump_patch(config, None, None).value == "0.0.0-1"
    assert scheme_procedures.version_bump_patch(config, "1.0.5-2", None).value is None
    assert scheme_procedures.version_bump_patch(config, "1.0.5-2", 1).value is None
    assert scheme_procedures.version_bump_patch(config, "1.0.5-2", 2).value == "1.0.6-3"


def test_qualifier_increment():
    assert scheme_procedures.version_bump_qualifier(config, "1.0.0", None).value is None
    assert scheme_procedures.version_bump_qualifier(config, "1.0.0-4", None).value is None
    assert scheme_procedures.version_bump_qualifier(config, "1.0.0-4", 4).value is None


def test_pre_release_increment():
    assert scheme_procedures.version_bump_prerelease(config, "1.0.0", None).value is None
    assert scheme_procedures.version_bump_prerelease(config, "1.0.0-alpha", None).value is None
    assert scheme_procedures.version_bump_prerelease(config, "1.0.0-alpha.0", None).value == "1.0.0-alpha.1"
    assert scheme_procedures.version_bump_prerelease(config, "1.0.0-alpha.4", None).value == "1.0.0-alpha.5"


def test_increment_to_release():
    assert scheme_procedures.version_bump_to_release(config, "1.0.0-4", None).value is None
    assert scheme_procedures.version_bump_to_release(config, "1.0.0-4", 4).value is None
    assert scheme_procedures.version_bump_to_release(config, "1.0.0", None).value is None
