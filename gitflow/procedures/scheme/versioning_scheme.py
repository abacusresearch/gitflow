from abc import abstractmethod

import semver


class VersioningSchemeImpl(object):
    @abstractmethod
    def get_initial_version(self):
        pass

    @abstractmethod
    def parse_version_info(self, version: str) -> semver.VersionInfo:
        pass

    @abstractmethod
    def format_version_info(self, version_info: semver.VersionInfo):
        pass

    @abstractmethod
    def compare_version_info(self, a: semver.VersionInfo, b: semver.VersionInfo):
        pass
