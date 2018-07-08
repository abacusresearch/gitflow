import os
from typing import Optional

import semver

from gitflow import _, version
from gitflow.common import Result
from gitflow.const import VersioningScheme
from gitflow.version import VersionConfig


def version_bump_major(version_config: VersionConfig, version: Optional[str], global_seq: Optional[int]):
    result = Result()
    version_info = semver.parse_version_info(semver.bump_major(version))
    pre_release = True

    result.value = semver.format_version(
        version_info.major,
        version_info.minor,
        version_info.patch,
        (version_config.qualifiers[0] + ".1" if pre_release else None)
        if version_config.versioning_scheme != VersioningScheme.SEMVER_WITH_SEQ
        else (global_seq or 0) + 1,
        None)
    return result


def version_bump_minor(version_config: VersionConfig, version: Optional[str], global_seq: Optional[int]):
    result = Result()
    version_info = semver.parse_version_info(semver.bump_minor(version))
    pre_release = True

    result.value = semver.format_version(
        version_info.major,
        version_info.minor,
        version_info.patch,
        (version_config.qualifiers[0] + ".1" if pre_release else None)
        if version_config.versioning_scheme != VersioningScheme.SEMVER_WITH_SEQ
        else (global_seq or 0) + 1,
        None)
    return result


def version_bump_patch(version_config: VersionConfig, version: Optional[str], global_seq: Optional[int]):
    result = Result()
    version_info = semver.parse_version_info(semver.bump_patch(version))
    pre_release = True

    result.value = semver.format_version(
        version_info.major,
        version_info.minor,
        version_info.patch,
        (version_config.qualifiers[0] + ".1" if pre_release else None)
        if version_config.versioning_scheme != VersioningScheme.SEMVER_WITH_SEQ
        else (global_seq or 0) + 1,
        None)
    return result


def version_bump_qualifier(version_config: VersionConfig, version: Optional[str], global_seq: Optional[int]):
    result = Result()
    version_info = semver.parse_version_info(version)

    new_qualifier = None

    if not version_config.qualifiers:
        result.error(os.EX_USAGE,
                     _("Failed to increment the pre-release qualifier of version {version}.")
                     .format(version=repr(version)),
                     _("The version scheme does not contain qualifiers")
                     )
        return result

    if version_info.prerelease:
        prerelease_version_elements = version_info.prerelease.split(".")
        qualifier = prerelease_version_elements[0]
        qualifier_index = version_config.qualifiers.index(qualifier) if qualifier in version_config.qualifiers else -1
        if qualifier_index < 0:
            result.error(os.EX_DATAERR,
                         _("Failed to increment the pre-release qualifier of version {version}.")
                         .format(version=repr(version)),
                         _("The current qualifier is invalid: {qualifier}")
                         .format(qualifier=repr(qualifier)))
        else:
            qualifier_index += 1
            if qualifier_index < len(version_config.qualifiers):
                new_qualifier = version_config.qualifiers[qualifier_index]
            else:
                result.error(os.EX_DATAERR,
                             _("Failed to increment the pre-release qualifier {qualifier} of version {version}.")
                             .format(qualifier=qualifier, version=repr(version)),
                             _("There are no further qualifiers with higher precedence, configured qualifiers are:\n"
                               "{listing}\n"
                               "The sub command 'bump-to-release' may be used for a final bump.")
                             .format(
                                 listing='\n'.join(' - ' + repr(qualifier) for qualifier in version_config.qualifiers))
                             )
    else:
        result.error(os.EX_DATAERR,
                     _("Failed to increment the pre-release qualifier of version {version}.")
                     .format(version=version),
                     _("Pre-release increments cannot be performed on release versions."))

    if not result.has_errors() and new_qualifier is not None:
        result.value = semver.format_version(
            version_info.major,
            version_info.minor,
            version_info.patch,
            new_qualifier + ".1",
            None)
    return result


def version_bump_prerelease(version_config: VersionConfig, version: Optional[str], global_seq: Optional[int]):
    result = Result()
    version_info = semver.parse_version_info(version)

    if version_info.prerelease:
        prerelease_version_elements = version_info.prerelease.split(".")
        if len(prerelease_version_elements) > 0 and prerelease_version_elements[0].upper() == "SNAPSHOT":
            if len(prerelease_version_elements) == 1:
                result.error(os.EX_DATAERR,
                             _("The pre-release increment has been skipped."),
                             _("In order to retain Maven compatibility, "
                               "the pre-release component of snapshot versions must not be versioned."))
            else:
                result.error(os.EX_DATAERR,
                             _("Failed to increment the pre-release component of version {version}.")
                             .format(version=repr(version)),
                             _("Snapshot versions must not have a pre-release version."))
            result.value = version
        elif len(prerelease_version_elements) == 1:
            if version_config.versioning_scheme != VersioningScheme.SEMVER_WITH_SEQ:
                result.error(os.EX_DATAERR,
                             _("Failed to increment the pre-release component of version {version}.")
                             .format(version=repr(version)),
                             _("The qualifier {qualifier} must already be versioned.")
                             .format(qualifier=repr(prerelease_version_elements[0]))
                             )
        result.value = semver.bump_prerelease(version)
    else:
        result.error(os.EX_DATAERR,
                     _("Failed to increment the pre-release component of version {version}.")
                     .format(version=repr(version)),
                     _("Pre-release increments cannot be performed on release versions.")
                     )

    if result.has_errors():
        result.value = None
    elif result.value is not None and not semver.compare(result.value, version) > 0:
        result.value = None

    if not result.value:
        result.error(os.EX_SOFTWARE,
                     _("Failed to increment the pre-release of version {version} for unknown reasons.")
                     .format(version=repr(version)),
                     None)
    return result


def version_bump_to_release(version_config: VersionConfig, version: Optional[str], global_seq: Optional[int]):
    result = Result()
    version_info = semver.parse_version_info(version)

    if version_config.versioning_scheme == VersioningScheme.SEMVER_WITH_SEQ:
        result.error(os.EX_USAGE,
                     _("Failed to increment version to release: {version}.")
                     .format(version=repr(version)),
                     _("Sequential versions cannot be release versions."))
        return result

    if not version_info.prerelease:
        result.error(os.EX_DATAERR,
                     _("Failed to increment version to release: {version}.")
                     .format(version=repr(version)),
                     _("Only pre-release versions can be incremented to a release version."))

    if not result.has_errors():
        result.value = semver.format_version(
            version_info.major,
            version_info.minor,
            version_info.patch,
            None,
            None)
    return result


class version_set(object):
    __new_version = None

    def __init__(self, new_version):
        self.__new_version = new_version

    def __call__(self, version_config: VersionConfig, old_version: Optional[str], global_seq: Optional[int]):
        return version.validate_version(version_config, old_version)


def get_sequence_number(version_config: VersionConfig, new_version_info: semver.VersionInfo):
    if version_config.versioning_scheme == VersioningScheme.SEMVER_WITH_SEQ:
        return int(new_version_info.prerelease)
    else:
        return None
