import datetime
import re

import pytz as pytz
import semver

from gitflow import _, const, repotools
from gitflow.const import BranchClass
from gitflow.context import Context
from gitflow.procedures import create_version
from gitflow.procedures.common import get_command_context, check_in_repo, check_requirements, fetch_all_and_ff
from gitflow.procedures.scheme import scheme_procedures
from gitflow.procedures.scheme.versioning_scheme import VersioningSchemeImpl
from gitflow.version import IncrementalVersionMatcher, VersionDelta


class CanonicalDateTime(VersioningSchemeImpl):
    __initial_version: str = None

    def __init__(self, context: Context):
        self.__initial_version = context.config.version_config.initial_version

        remote_prefix = repotools.create_ref_name(const.REMOTES_PREFIX, context.config.remote_name)

        self.release_base_branch_matcher = IncrementalVersionMatcher(
            [const.LOCAL_BRANCH_PREFIX, remote_prefix],
            None,
            re.escape(context.config.release_branch_base),
        )

        self.release_branch_matcher = IncrementalVersionMatcher(
            [const.LOCAL_BRANCH_PREFIX, remote_prefix],
            None,
            context.config_properties.get(
                const.CONFIG_RELEASE_BRANCH_PATTERN,
                const.DEFAULT_RELEASE_BRANCH_PATTERN),
        )

        self.work_branch_matcher = IncrementalVersionMatcher(
            [const.LOCAL_BRANCH_PREFIX, remote_prefix],
            [const.BRANCH_PREFIX_DEV, const.BRANCH_PREFIX_PROD],
            context.config_properties.get(
                const.CONFIG_WORK_BRANCH_PATTERN,
                const.DEFAULT_WORK_BRANCH_PATTERN),
        )

        self.version_tag_matcher = IncrementalVersionMatcher(
            [const.LOCAL_TAG_PREFIX],
            context.config_properties.get(
                const.CONFIG_VERSION_TAG_PREFIX,
                const.DEFAULT_VERSION_TAG_PREFIX),
            context.config_properties.get(
                const.CONFIG_VERSION_TAG_PATTERN,
                const.DEFAULT_CANONICAL_DATETIME_VERSION_TAG_PATTERN)
        )
        self.version_tag_matcher.group_unique_code = 'unique_code'

        self.discontinuation_tag_matcher = IncrementalVersionMatcher(
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
        now = datetime.datetime.now(tz=pytz.timezone('UTC'))
        return "%d%d%d%d%d%d" % now.year, now.month, now.day, now.hour, now.minute, now.second

    def parse_version_info(self, version: str) -> semver.VersionInfo:
        return semver.VersionInfo(major=int(version.split('.')[0]), minor=0, patch=0)

    def format_version_info(self, version_info: semver.VersionInfo) -> str:
        return str(version_info.major)

    def compare_version(self, a: str, b: str) -> VersionDelta:
        delta = VersionDelta()

        delta.difference = int(a) - int(b)

        return delta

    def compare_version_info(self, a: semver.VersionInfo, b: semver.VersionInfo):
        # TODO avoid superfluous conversions
        return semver.compare(self.format_version_info(a), self.format_version_info(b))

    def get_tag_name_for_version(self, context: Context, version: str):
        return (context.version_tag_matcher.ref_name_infix or '') \
               + str(version)

    def cmd_bump_major(self, context: Context):
        command_context = get_command_context(
            context=context,
            object_arg=context.args['<object>']
        )

        check_in_repo(command_context)

        check_requirements(command_context=command_context,
                           ref=command_context.selected_ref,
                           branch_classes=[BranchClass.DEVELOPMENT_BASE],
                           modifiable=True,
                           with_upstream=True,  # not context.config.push_to_local
                           in_sync_with_upstream=True,
                           fail_message=_("Version creation failed.")
                           )

        tag_result = create_version.create_branchless_version_tag(command_context, scheme_procedures.version_bump_integer)
        command_context.add_subresult(tag_result)

        if not command_context.has_errors() \
                and context.config.pull_after_bump \
                and not context.config.push_to_local:
            fetch_all_and_ff(context.repo, command_context.result, context.config.remote_name)

        return context.result
