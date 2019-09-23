import os
from configparser import ConfigParser
from enum import Enum

NAME = 'gitflow'
AUTHOR = 'samuel.oggier@gmail.com'

with open(os.path.abspath(os.path.join(os.path.dirname(__file__), 'config.ini')), 'r') as __config_file:
    __config = ConfigParser()
    __config.read_file(f=__config_file)
    VERSION = __config.get(section=__config.default_section, option='version', fallback='0.0.0-dev')


class VersioningScheme(Enum):
    # SemVer tags
    SEMVER = 1,
    # SemVer with sequence in pre-release
    SEMVER_WITH_SEQ = 2,
    CANONICAL_DATETIME = 3,


VERSIONING_SCHEMES = {
    'semver': VersioningScheme.SEMVER,
    'semverWithSeq': VersioningScheme.SEMVER_WITH_SEQ,
    'semver_with_seq': VersioningScheme.SEMVER_WITH_SEQ,
    'canonical_datetime': VersioningScheme.CANONICAL_DATETIME,
}

# config keys

CONFIG_VERSIONING_SCHEME = 'versioningScheme'
CONFIG_VERSION_TYPES = 'releaseTypes'

CONFIG_PROJECT_PROPERTY_FILE = 'propertyFile'
CONFIG_VERSION_PROPERTY = 'versionProperty'
CONFIG_SEQUENCE_NUMBER_PROPERTY = 'sequenceNumberProperty'

CONFIG_BUILD = 'build'
CONFIG_ON_VERSION_CHANGE = 'onVersionChange'

CONFIG_RELEASE_BRANCH_BASE = 'releaseBranchBase'

CONFIG_RELEASE_BRANCH_PREFIX = 'releaseBranchPrefix'
CONFIG_RELEASE_BRANCH_PATTERN = 'releaseBranchPattern'

CONFIG_WORK_BRANCH_PATTERN = 'workBranchPattern'

CONFIG_VERSION_TAG_PREFIX = 'versionTagPrefix'
CONFIG_VERSION_TAG_PATTERN = 'versionTagPattern'

CONFIG_DISCONTINUATION_TAG_PREFIX = 'discontinuationTagPrefix'
CONFIG_DISCONTINUATION_TAG_PATTERN = 'discontinuationTagPattern'

CONFIG_INITIAL_VERSION = 'initialVersion'

# config defaults

DEFAULT_CONFIG_FILE_EXTENSIONS = ['yml', 'json']
DEFAULT_CONFIGURATION_FILE_NAMES = ['.gitflow.' + ext for ext in DEFAULT_CONFIG_FILE_EXTENSIONS]
DEFAULT_CONFIG_FILE = DEFAULT_CONFIGURATION_FILE_NAMES[1]

DEFAULT_RELEASE_BRANCH_BASE = "master"

DEFAULT_VERSIONING_SCHEME = 'semver'

DEFAULT_RELEASE_BRANCH_PREFIX = 'release/'

DEFAULT_RELEASE_BRANCH_PATTERN = r'(?P<major>\d+)\.(?P<minor>\d+)'

DEFAULT_WORK_BRANCH_PATTERN = r'(?P<type>feature|fix|chore|issue)/(?P<name>[^/]+)'

DEFAULT_VERSION_VAR_NAME = 'version'
DEFAULT_VERSION_TAG_PREFIX = None

DEFAULT_SEMVER_VERSION_TAG_PATTERN = r'(?P<major>\d+)\.(?P<minor>\d+)\.(?P<patch>\d+)' \
                                     r'(-(?P<prerelease_type>[a-zA-Z][a-zA-Z0-9]*)' \
                                     r'(\.(?P<prerelease_version>\d+))?)?'

DEFAULT_SEMVER_WITH_SEQ_VERSION_TAG_PATTERN = r'(?P<major>\d+)\.(?P<minor>\d+)\.(?P<patch>\d+)' \
                                              r'-((?P<prerelease_type>(0|[1-9][0-9]*))?' \
                                              r'([.-](?P<prerelease_version>\d+))?)?'

DEFAULT_CANONICAL_DATETIME_VERSION_TAG_PATTERN = r'(?P<unique_code>(?P<year>[0-9]+)(?P<month>[0-9]{2})(?P<day>[0-9]{2})(?P<hour>[0-9]{2})(?P<minute>[0-9]{2})(?P<second>[0-9]{2}))'

DEFAULT_DISCONTINUATION_TAG_PREFIX = 'discontinued/'

DEFAULT_DISCONTINUATION_TAG_PATTERN = r'(?P<major>\d+)\.(?P<minor>\d+)(?:\.(?P<patch>\d+)' \
                                      r'(-(?P<prerelease_type>[a-zA-Z][a-zA-Z0-9]*)' \
                                      r'(\.(?P<prerelease_version>\d+))?)?)?'

DEFAULT_PROPERTY_ENCODING = 'UTF-8'

TEXT_VERSION_STRING_FORMAT = "<major:uint>.<minor:uint>.<patch:uint>" \
                             "[-<prerelease_type:(a-zA-Z)(a-zA-Z0-9)*>.<prerelease_version:uint>]" \
                             "[+<build_info:(a-zA-Z0-9)+>]"

DEFAULT_PRE_RELEASE_QUALIFIERS = "alpha,beta"

DEFAULT_INITIAL_VERSION = '1.0.0-alpha.1'
DEFAULT_INITIAL_SEQ_VERSION = '1.0.0-1'

DEFAULT_CONFIG = {
    CONFIG_PROJECT_PROPERTY_FILE: 'project.properties',
    CONFIG_RELEASE_BRANCH_BASE: 'master'
}

# prefixes with a trailing slash for proper prefix matching
LOCAL_BRANCH_PREFIX = 'refs/heads/'
LOCAL_TAG_PREFIX = 'refs/tags/'
REMOTES_PREFIX = 'refs/remotes/'

BRANCH_PATTERN = '(?P<parent>refs/heads/|refs/remotes/(?P<remote>[^/]+)/)(?P<name>.+)'
LOCAL_AND_REMOTE_BRANCH_PREFIXES = [LOCAL_BRANCH_PREFIX, REMOTES_PREFIX]

BRANCH_PREFIX_DEV = 'dev'
BRANCH_PREFIX_PROD = 'prod'

BUILD_STAGE_TYPE_ASSEMBLE = 'assemble'
BUILD_STAGE_TYPE_TEST = 'test'
BUILD_STAGE_TYPE_INTEGRATION_TEST = 'integration_test'

BUILD_STAGE_TYPES = [
    BUILD_STAGE_TYPE_ASSEMBLE,
    BUILD_STAGE_TYPE_TEST,
    BUILD_STAGE_TYPE_INTEGRATION_TEST
]


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

# TODO Accounts for two actual arguments. Adjust when docopt option counting is fixed.
ERROR_VERBOSITY = 0
INFO_VERBOSITY = 1
DEBUG_VERBOSITY = 2
TRACE_VERBOSITY = 3

OS_IS_POSIX = os.name == 'posix'

EX_ABORTED = 2
EX_ABORTED_BY_USER = 3

# ['--first-parent'] to ignore merged tags
BRANCH_COMMIT_SCAN_OPTIONS = []
