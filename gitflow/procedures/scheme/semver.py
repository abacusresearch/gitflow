import semver

from gitflow.procedures.scheme.versioning_scheme import VersioningSchemeImpl


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
