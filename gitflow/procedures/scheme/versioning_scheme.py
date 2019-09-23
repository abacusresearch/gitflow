from abc import abstractmethod
from typing import Callable, Optional

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

    def get_cmd_method(self, name: str) -> Optional[Callable]:
        try:
            return self.__getattribute__('cmd_' + name)
        except AttributeError:
            return None
