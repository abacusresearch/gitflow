import os
from configparser import ConfigParser
from enum import Enum

NAME = 'gitflow'
AUTHOR = 'samuel.oggier@gmail.com'

with open(os.path.abspath(os.path.join(os.path.dirname(__file__), 'config.ini')), 'r') as __config_file:
    __config = ConfigParser()
    __config.read_file(f=__config_file)
    VERSION = __config.get(section=__config.default_section, option='version', fallback='0.0.0-dev')

CONFIG_PROJECT_PROPERTY_FILE = 'propertyFile'
CONFIG_VERSIONING_SCHEME = 'versioningScheme'
CONFIG_VERSION_PROPERTY_NAME = 'versionPropertyName'
CONFIG_SEQUENTIAL_VERSION_PROPERTY_NAME = 'sequentialVersionPropertyName'
CONFIG_OPAQUE_VERSION_PROPERTY_NAME = 'opaqueVersionPropertyName'
CONFIG_BUILD = 'build'

CONFIG_RELEASE_BRANCH_BASE = 'releaseBranchBase'

CONFIG_RELEASE_BRANCH_PREFIX = 'releaseBranchPrefix'
CONFIG_RELEASE_BRANCH_PATTERN = 'releaseBranchPattern'

CONFIG_WORK_BRANCH_PATTERN = 'workBranchPattern'

CONFIG_VERSION_TAG_PREFIX = 'versionTagPrefix'
CONFIG_VERSION_TAG_PATTERN = 'versionTagPattern'

CONFIG_SEQUENTIAL_VERSION_TAG_PREFIX = 'sequentialVersionTagPrefix'
CONFIG_SEQUENTIAL_VERSION_TAG_PATTERN = 'sequentialVersionTagPattern'

CONFIG_DISCONTINUATION_TAG_PREFIX = 'discontinuationTagPrefix'
CONFIG_DISCONTINUATION_TAG_PATTERN = 'discontinuationTagPattern'

CONFIG_PRE_RELEASE_QUALIFIERS = 'versionTypes'
CONFIG_INITIAL_VERSION = 'initialVersion'

DEFAULT_CONFIG_FILE = 'gitflow.json'
DEFAULT_PROJECT_PROPERTY_FILE = 'project.properties'

DEFAULT_RELEASE_BRANCH_BASE = "master"

DEFAULT_RELEASE_BRANCH_PREFIX = 'release/'
DEFAULT_RELEASE_BRANCH_PATTERN = r'(?P<major>\d+)\.(?P<minor>\d+)'

DEFAULT_WORK_BRANCH_PATTERN = r'(?P<type>feature|fix|chore|issue)/(?P<name>[^/]+)'

DEFAULT_VERSION_VAR_NAME = 'version'
DEFAULT_VERSION_TAG_PREFIX = 'version/'
DEFAULT_VERSION_TAG_PATTERN = r'(?P<major>\d+)\.(?P<minor>\d+)\.(?P<patch>\d+)' \
                              r'(-(?P<prerelease_type>[a-zA-Z][a-zA-Z0-9]*)' \
                              r'(\.(?P<prerelease_version>\d+))?)?'

DEFAULT_SEQUENTIAL_VERSION_VAR_NAME = 'version_code'
DEFAULT_SEQUENTIAL_VERSION_TAG_PREFIX = 'version_code/'
DEFAULT_SEQUENTIAL_VERSION_TAG_PATTERN = r'(?P<unique_code>\d+)'

DEFAULT_DISCONTINUATION_TAG_PREFIX = 'discontinued/'
DEFAULT_DISCONTINUATION_TAG_PATTERN = r'(?P<major>\d+)\.(?P<minor>\d+)(?:\.(?P<patch>\d+)' \
                                      r'(-(?P<prerelease_type>[a-zA-Z][a-zA-Z0-9]*)' \
                                      r'(\.(?P<prerelease_version>\d+))?)?)?'

TEXT_VERSION_STRING_FORMAT = "<major:uint>.<minor:uint>.<patch:uint>" \
                             "[-<prerelease_type:(a-zA-Z)(a-zA-Z0-9)*>.<prerelease_version:uint>]" \
                             "[+<build_info:(a-zA-Z0-9)+>]"

DEFAULT_PRE_RELEASE_QUALIFIERS = "alpha,beta,rc"

DEFAULT_INITIAL_VERSION = '1.0.0-alpha.1'

DEFAULT_OPAQUE_VERSION_FORMAT = "{major}.{minor}.{patch}-{version_code}"

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
NO_VERBOSITY = 0
ERROR_VERBOSITY = 1
INFO_VERBOSITY = 2
TRACE_VERBOSITY = 3

OS_IS_POSIX = os.name == 'posix'

EX_ABORTED = 2
EX_ABORTED_BY_USER = 3
