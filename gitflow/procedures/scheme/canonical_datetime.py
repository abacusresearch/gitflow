import datetime

import pytz as pytz
import semver

from gitflow.procedures.scheme.versioning_scheme import VersioningSchemeImpl


class CanonicalDateTime(VersioningSchemeImpl):
    __initial_version: str = None

    def __init__(self):
        pass

    def get_initial_version(self):
        now = datetime.datetime.now(tz=pytz.timezone('UTC'))
        return "%d%d%d%d%d%d" % now.year, now.month, now.day, now.hour, now.minute, now.second

    def parse_version_info(self, version: str) -> semver.VersionInfo:
        return semver.VersionInfo(major=int(version), minor=0, patch=0)

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
