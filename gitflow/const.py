import os
from enum import Enum

VERSION = '1.0.0-alpha.1'
MIN_GIT_VERSION = "2.9.0"

CONFIG_PROJECT_PROPERTY_FILE = 'propertyFile'
CONFIG_VERSION_PROPERTY_NAME = 'versionPropertyName'
CONFIG_SEQUENTIAL_VERSION_PROPERTY_NAME = 'sequentialVersionPropertyName'

CONFIG_RELEASE_BRANCH_BASE = 'releaseBranchBase'
CONFIG_RELEASE_BRANCH_PATTERN = 'releaseBranchPattern'
CONFIG_WORK_BRANCH_PATTERN = 'workBranchPattern'
CONFIG_VERSION_TAG_PATTERN = 'versionTagPattern'
CONFIG_DISCONTINUATION_TAG_PATTERN = 'discontinuationTagPattern'
CONFIG_SEQUENTIAL_VERSION_TAG_PATTERN = 'sequentialVersionTagPattern'
CONFIG_PRE_RELEASE_VERSION_QUALIFIERS = 'preReleaseVersionQualifiers'
CONFIG_INITIAL_VERSION = 'initialVersion'

DEFAULT_CONFIG_FILE = 'gitflow.properties'
DEFAULT_PROJECT_PROPERTY_FILE = 'project.properties'

DEFAULT_RELEASE_BRANCH_BASE = "master"

DEFAULT_RELEASE_BRANCH_PATTERN = r'(?P<major>\d+)\.(?P<minor>\d+)'

DEFAULT_WORK_BRANCH_PATTERN = r'(?P<type>feature|fix|chore|issue)/(?P<name>[^/]+)'

DEFAULT_VERSION_TAG_PATTERN = r'(?P<major>\d+)\.(?P<minor>\d+)\.(?P<patch>\d+)' \
                              r'(-(?P<prerelease_type>[a-zA-Z][a-zA-Z0-9]*)' \
                              r'(\.(?P<prerelease_version>\d+))?)?'

DEFAULT_DISCONTINUATION_TAG_PATTERN = r'(?P<major>\d+)\.(?P<minor>\d+)(?:\.(?P<patch>\d+)' \
                                      r'(-(?P<prerelease_type>[a-zA-Z][a-zA-Z0-9]*)' \
                                      r'(\.(?P<prerelease_version>\d+))?)?)?'

DEFAULT_SEQUENTIAL_VERSION_TAG_PATTERN = r'(?P<unique_code>\d+)'

TEXT_VERSION_STRING_FORMAT = "<major:uint>.<minor:uint>.<patch:uint>" \
                             "[-<prerelease_type:(a-zA-Z)(a-zA-Z0-9)*>.<prerelease_version:uint>]" \
                             "[+<build_info:(a-zA-Z0-9)+>]"

DEFAULT_PRE_RELEASE_QUALIFIERS = "alpha,beta,rc"

DEFAULT_INITIAL_VERSION = '1.0.0-alpha.1'

LOCAL_BRANCH_PREFIX = 'refs/heads/'
LOCAL_TAG_PREFIX = 'refs/tags/'
REMOTES_PREFIX = 'refs/remotes/'

BRANCH_PATTERN = '(?P<parent>refs/heads/|refs/remotes/(?P<remote>[^/]+)/)(?P<name>.+)'
LOCAL_AND_REMOTE_BRANCH_PREFIXES = [LOCAL_BRANCH_PREFIX, REMOTES_PREFIX]

BRANCH_PREFIX_DEV = 'dev'
BRANCH_PREFIX_PROD = 'prod'

# TODO Accounts for two actual arguments. Adjust when docopt option counting is fixed or clarified.
ERROR_VERBOSITY = 1
INFO_VERBOSITY = 2
TRACE_VERBOSITY = 3

OS_IS_POSIX = os.name == 'posix'


def __setattr__(self, name, value):
    if hasattr(self, name):
        raise AttributeError('Can\'t reassign const attribute "' + name + '"')
    else:
        super(self.__class__, self).__setattr__(name, value)


class BranchClass(Enum):
    DEVELOPMENT_BASE = 1,
    RELEASE = 2,
    WORK_DEV = 3,
    WORK_PROD = 4,


BRANCH_CLASS_BY_SUPERTYPE = {
    BRANCH_PREFIX_PROD: BranchClass.WORK_PROD,
    BRANCH_PREFIX_DEV: BranchClass.WORK_DEV,
}

BRANCHING = {
    BranchClass.WORK_DEV: BranchClass.DEVELOPMENT_BASE,
    BranchClass.WORK_PROD: BranchClass.RELEASE,
    BranchClass.RELEASE: BranchClass.DEVELOPMENT_BASE,
}
