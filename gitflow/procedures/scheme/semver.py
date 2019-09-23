import re

import semver

from gitflow import const, repotools
from gitflow.const import VersioningScheme
from gitflow.context import Context
from gitflow.procedures.scheme import scheme_procedures
from gitflow.procedures.scheme.versioning_scheme import VersioningSchemeImpl
import gitflow.procedures.create_version
import gitflow.procedures.discontinue_version
import gitflow.procedures.begin
import gitflow.procedures.end
from gitflow.version import VersionMatcher


class SemVer(VersioningSchemeImpl):
    __initial_version: str = None

    def __init__(self, context: Context):
        self.__initial_version = context.config.version_config.initial_version

        remote_prefix = repotools.create_ref_name(const.REMOTES_PREFIX, context.config.remote_name)

        self.release_base_branch_matcher = VersionMatcher(
            [const.LOCAL_BRANCH_PREFIX, remote_prefix],
            None,
            re.escape(context.config.release_branch_base),
        )

        self.release_branch_matcher = VersionMatcher(
            [const.LOCAL_BRANCH_PREFIX, remote_prefix],
            context.config_properties.get(
                const.CONFIG_RELEASE_BRANCH_PREFIX,
                const.DEFAULT_RELEASE_BRANCH_PREFIX),
            context.config_properties.get(
                const.CONFIG_RELEASE_BRANCH_PATTERN,
                const.DEFAULT_RELEASE_BRANCH_PATTERN),
        )

        self.work_branch_matcher = VersionMatcher(
            [const.LOCAL_BRANCH_PREFIX, remote_prefix],
            [const.BRANCH_PREFIX_DEV, const.BRANCH_PREFIX_PROD],
            context.config_properties.get(
                const.CONFIG_WORK_BRANCH_PATTERN,
                const.DEFAULT_WORK_BRANCH_PATTERN),
        )

        self.version_tag_matcher = VersionMatcher(
            [const.LOCAL_TAG_PREFIX],
            context.config_properties.get(
                const.CONFIG_VERSION_TAG_PREFIX,
                const.DEFAULT_VERSION_TAG_PREFIX),
            context.config_properties.get(
                const.CONFIG_VERSION_TAG_PATTERN,
                const.DEFAULT_SEMVER_VERSION_TAG_PATTERN
                if context.config.version_config.versioning_scheme == VersioningScheme.SEMVER
                else const.DEFAULT_SEMVER_WITH_SEQ_VERSION_TAG_PATTERN)
        )
        self.version_tag_matcher.group_unique_code = None \
            if context.config.version_config.versioning_scheme == VersioningScheme.SEMVER \
            else 'prerelease_type'

        self.discontinuation_tag_matcher = VersionMatcher(
            [const.LOCAL_TAG_PREFIX],
            context.config_properties.get(
                const.CONFIG_DISCONTINUATION_TAG_PREFIX,
                const.DEFAULT_DISCONTINUATION_TAG_PREFIX),
            context.config_properties.get(
                const.CONFIG_DISCONTINUATION_TAG_PATTERN,
                const.DEFAULT_DISCONTINUATION_TAG_PATTERN),
            None
        )

    def get_initial_version(self):
        return self.__initial_version

    def parse_version_info(self, version: str) -> semver.VersionInfo:
        return semver.parse_version_info(version)

    def format_version_info(self, version_info: semver.VersionInfo) -> str:
        return semver.format_version(
            version_info.major,
            version_info.minor,
            version_info.patch,
            version_info.prerelease,
            version_info.build)

    def compare_version_info(self, a: semver.VersionInfo, b: semver.VersionInfo):
        # TODO avoid superfluous conversions
        return semver.compare(self.format_version_info(a), self.format_version_info(b))

    def cmd_bump_major(self, context: Context):
        return gitflow.procedures.create_version.call(context, scheme_procedures.version_bump_major)

    def cmd_bump_minor(self, context: Context):
        return gitflow.procedures.create_version.call(context, scheme_procedures.version_bump_minor)

    def cmd_bump_patch(self, context: Context):
        return gitflow.procedures.create_version.call(context, scheme_procedures.version_bump_patch)

    def cmd_bump_prerelease_type(self, context: Context):
        return gitflow.procedures.create_version.call(context, scheme_procedures.version_bump_qualifier)

    def cmd_bump_prerelease(self, context: Context):
        return gitflow.procedures.create_version.call(context, scheme_procedures.version_bump_prerelease)

    def cmd_bump_to_release(self, context: Context):
        return gitflow.procedures.create_version.call(context, scheme_procedures.version_bump_to_release)

    def cmd_bump_to(self, context: Context):
        return gitflow.procedures.create_version.call(context, scheme_procedures.VersionSet(context.args['<version>']))

    def cmd_discontinue(self, context: Context):
        return gitflow.procedures.discontinue_version.call(context)

    def cmd_start(self, context: Context):
        return gitflow.procedures.begin.call(context)

    def cmd_finish(self, context: Context):
        return gitflow.procedures.end.call(context)
