import semver

from gitflow.context import Context
from gitflow.procedures.scheme import scheme_procedures
from gitflow.procedures.scheme.versioning_scheme import VersioningSchemeImpl
import gitflow.procedures.create_version
import gitflow.procedures.discontinue_version
import gitflow.procedures.begin
import gitflow.procedures.end


class SemVer(VersioningSchemeImpl):
    __initial_version: str = None

    def __init__(self, initial_version: str):
        self.__initial_version = initial_version

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
