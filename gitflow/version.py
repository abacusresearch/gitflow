import itertools
import os
import re
import string
from typing import Union, List

import semver

from gitflow import const, utils, _
from gitflow.common import Result
from gitflow.const import VersioningScheme


class VersionConfig(object):
    versioning_scheme: VersioningScheme = None
    qualifiers: list = None
    initial_version: str = None


class Version(object):
    major = None
    minor = None
    patch = None
    prerelease = None
    build = None

    def __repr__(self):
        return format_version(self)

    def __str__(self):
        return format_version(self)


class VersionDelta(object):
    version_a = None
    version_b = None
    difference = None
    resets = None
    prerelase_keywords_list = None

    @property
    def differs(self):
        if self.difference is not None:
            for d in self.difference:
                if d != 0:
                    return True
        return False

    @property
    def differs_at_branch_level(self):
        if self.difference is not None:
            for index, d in enumerate(self.difference):
                if d != 0:
                    return True
                if index == 2:
                    break
        return False

    def prerelease_field_only(self, prerelease_field_index, include_resets: bool = False):
        return self.field_only(prerelease_field_index + 3, include_resets)

    def field_only(self, field_index, include_resets: bool = False):
        result = False
        if self.difference is not None:
            for index, d in enumerate(self.difference):
                if index > field_index:
                    break
                if index != field_index:
                    if (include_resets or not self.resets[index]) and d != 0:
                        result = False
                        break
                else:
                    if d != 0:
                        result = True
        return result


class VersionMatcher(object):
    pattern = None
    group_major = None
    group_minor = None
    group_patch = None
    group_prerelease_type = None
    group_prerelease_version = None
    group_prefix = None
    group_unique_code = None

    ref_name_infixes: List[str] = None
    ref_name_infix: str = None
    __format = None

    comparator = None
    key_func = None

    def __init__(self, ref_roots: list, ref_name_infixes: Union[List[str], str, None], pattern: str,
                 format: str = None):
        """
        :param pattern:
        :param ref_name_infixes: the name prefixes of branches and tags following the conventional parents
        'refs/heads/', 'refs/remotes/<remote>/' and 'refs/tags/'
        :param format: format that combines version elements to a SemVer version
        """

        if ref_name_infixes is not None:
            if not isinstance(ref_name_infixes, list):
                ref_name_infixes = [ref_name_infixes]
            for index, ref_name_infix in enumerate(ref_name_infixes):
                ref_name_infixes[index] = utils.split_join('/', False, True, ref_name_infix)
            ref_name_infixes = [infix for infix in ref_name_infixes if infix is not None and infix != '/']
        self.ref_name_infixes = ref_name_infixes
        self.ref_name_infix = self.ref_name_infixes[0] if self.ref_name_infixes and len(self.ref_name_infixes) else None

        full_pattern = ''
        full_pattern += '(?:'
        full_pattern += '|'.join(re.escape(utils.split_join('/', False, True, ref_root)) for ref_root in ref_roots)
        full_pattern += ')'
        if ref_name_infixes is not None and len(ref_name_infixes):
            full_pattern += '(?P<prefix>'
            full_pattern += '|'.join(re.escape(utils.split_join('/', False, False, ref_name_infix))
                                     for ref_name_infix in ref_name_infixes)
            full_pattern += ')\\/'
        full_pattern += pattern

        self.pattern = re.compile(full_pattern)
        self.group_major = self.pattern.groupindex.get('major')
        self.group_minor = self.pattern.groupindex.get('minor')
        self.group_patch = self.pattern.groupindex.get('patch')
        self.group_prerelease_type = self.pattern.groupindex.get('prerelease_type')
        self.group_prerelease_version = self.pattern.groupindex.get('prerelease_version')
        self.group_prefix = self.pattern.groupindex.get('prefix')
        self.group_unique_code = self.pattern.groupindex.get('unique_code')

        self.__format = format

        self.comparator = lambda tag_ref_a, tag_ref_b: semver.compare(
            self.format(tag_ref_a.name),
            self.format(tag_ref_b.name)
        )
        self.key_func = utils.cmp_to_key(self.comparator)

    def to_version(self, string: str) -> Version:
        version_str = self.format(string)
        return parse_version(version_str) if version_str is not None else None

    def fullmatch(self, string: str):
        return self.pattern.fullmatch(string)

    def to_dict(self, string: str) -> dict:
        """
        :param string: input string
        :return: dictionary containing version fields extracted from the input string
        """
        match = self.pattern.fullmatch(string)
        if match is None:
            return None
        return match.groupdict()

    def format(self, string: str) -> str:
        """
        :param string: input string
        :return string representation of version fields extracted from the input string
        """
        match = self.pattern.fullmatch(string)
        if match is None:
            return None
        fields = match.groupdict()

        if self.__format is not None:
            return self.__format.format(**fields)
        else:
            major = fields.get('major')
            if major is not None:
                major = int(major)
            minor = fields.get('minor')
            if minor is not None:
                minor = int(minor)
            patch = fields.get('patch')
            if patch is not None:
                patch = int(patch)
            else:
                patch = 0

            prerelease_type = fields.get('prerelease_type')
            prerelease_version = fields.get('prerelease_version')
            prerelease = None
            if prerelease_type is not None:
                prerelease = prerelease_type
            if prerelease_version is not None:
                prerelease = '.' if prerelease is None else prerelease + '.'
                prerelease += prerelease_version

            build = fields.get('build')

            return semver.format_version(
                major=major,
                minor=minor,
                patch=patch,
                prerelease=prerelease,
                build=build,
            )

    def to_version_info(self, string: str):
        version = self.format(string)
        if version is not None:
            return semver.parse_version_info(version)


def validate_version(config: VersionConfig, version_string):
    result = Result()

    try:
        version_info = semver.parse_version_info(version_string)
        if version_info.prerelease is not None:
            if version_info.prerelease is not None and not re.match(r'[a-zA-Z][a-zA-Z0-9]*\.\d',
                                                                    version_info.prerelease):
                result.error(os.EX_DATAERR,
                             "Invalid version format.",
                             "The pre-release component must contain a type name with a version number.\n"
                             "The required version format is:\n"
                             + const.TEXT_VERSION_STRING_FORMAT)
            prerelease_version_elements = version_info.prerelease.split(".")
            prerelease_type = prerelease_version_elements[0]
            prerelease_version = prerelease_version_elements[1]

            if config.qualifiers is not None and not prerelease_type in config.qualifiers:
                result.error(os.EX_DATAERR,
                             "Invalid version.",
                             "The pre-release type \"" + prerelease_type + "\" is invalid, must be one of: "
                             + ','.join(config.qualifiers) + ".\n"
                             + "Configuration property: " + const.CONFIG_VERSION_TYPES)
        result.value = version_string
    except ValueError:
        result.error(os.EX_DATAERR,
                     "Failed to parse the version.",
                     "The required version format is:\n"
                     + const.TEXT_VERSION_STRING_FORMAT)

    return result


def is_valid_semver_version(version_string):
    version_string = version_string[0:version_string.find('-')]
    version_string = version_string.replace('-', '.0+')

    print("trying: " + version_string)

    try:
        semver.parse(version_string)
        return True
    except ValueError:
        return False


def create_initial_branch_version(config: VersionConfig, branch_base_version):
    branch_base_version_info = semver.parse_version_info(branch_base_version)
    template_version_info = semver.parse_version_info(config.initial_version)
    new_version = semver.format_version(
        major=branch_base_version_info.major,
        minor=branch_base_version_info.minor,

        patch=template_version_info.patch,
        prerelease=template_version_info.prerelease,
        build=template_version_info.build,
    )
    return new_version


def format_version_info(version_info: semver.VersionInfo):
    return semver.format_version(
        version_info.major,
        version_info.minor,
        version_info.patch,
        version_info.prerelease,
        version_info.build)


def _nat_cmp(a, b):
    def convert(text):
        return int(text) if re.match('^[0-9]+$', text) else text

    def split_key(key):
        return [convert(c) for c in key.split('.')]

    def cmp_prerelease_tag(a, b):
        if isinstance(a, int) and isinstance(b, int):
            return cmp(a, b)
        elif isinstance(a, int):
            return -1
        elif isinstance(b, int):
            return 1
        else:
            return cmp(a, b)

    a, b = a or '', b or ''
    a_parts, b_parts = split_key(a), split_key(b)
    for sub_a, sub_b in zip(a_parts, b_parts):
        cmp_result = cmp_prerelease_tag(sub_a, sub_b)
        if cmp_result != 0:
            return cmp_result
    else:
        return cmp(len(a), len(b))


def _nat_cmp_v(a, b, keywords: list = None):
    def convert(text):
        return int(text) if re.match('^[0-9]+$', text) else text

    def split_key(key):
        return [convert(c) for c in key.split('.')]

    def cmp_prerelease_tag(index, a, b):
        if a == b:
            return 0
        if a is None or b is None:
            return -1 if a is None else 1

        if isinstance(a, int) and isinstance(b, int):
            return b - a
        elif isinstance(a, int):
            return -1
        elif isinstance(b, int):
            return 1
        else:
            if keywords is not None:
                index_a = keywords.index(a)
                index_b = keywords.index(b)
                if index_a is not None and index_b is not None:
                    return index_b - index_a
            return string

    delta = list()

    a, b = a or '', b or ''
    a_parts, b_parts = split_key(a), split_key(b)
    index = 0
    for sub_a, sub_b in itertools.zip_longest(a_parts, b_parts):
        cmp_result = cmp_prerelease_tag(index, sub_a, sub_b)
        delta.append(cmp_result)
        index += 1
    return delta


_SEMVER_REGEX = re.compile(
    r"""
    ^
    (?P<major>(?:0|[1-9][0-9]*))
    \.
    (?P<minor>(?:0|[1-9][0-9]*))
    \.
    (?P<patch>(?:0|[1-9][0-9]*))
    (-(?P<prerelease>
        (?:0|[1-9A-Za-z-][0-9A-Za-z-]*)
        (\.(?:0|[1-9A-Za-z-][0-9A-Za-z-]*))*
    ))?
    (\+(?P<build>
        [0-9A-Za-z-]+
        (\.[0-9A-Za-z-]+)*
    ))?
    $
    """, re.VERBOSE)


def split_prerel(key):
    return [int(token) if re.match('^[0-9]+$', token) else token for token in
            key.split('.')] if key is not None else None


def cmp_alnum_token(a, b, keywords: list = None):
    if a == b:
        return 0
    if a is None or b is None:
        return -1 if a is None else 1

    if isinstance(a, int) and isinstance(b, int):
        return a - b
    elif isinstance(a, int):
        return 1
    elif isinstance(b, int):
        return -1
    else:
        if isinstance(keywords, list):
            index_a = keywords.index(a)
            index_b = keywords.index(b)
            if index_a is not None and index_b is not None:
                return index_a - index_b
        return (a > b) - (a < b)


def parse_version(version_str: str) -> Version:
    match = _SEMVER_REGEX.match(version_str)
    if match is None:
        return None

    version = Version()

    version_parts = match.groupdict()

    version.major = int(version_parts['major'])
    version.minor = int(version_parts['minor'])
    version.patch = int(version_parts['patch'])
    version.prerelease = split_prerel(version_parts['prerelease'])
    version.build = version_parts['build']

    return version


def format_version(version: Version) -> str:
    version_str = "%d.%d.%d" % (version.major, version.minor, version.patch)
    if version.prerelease is not None:
        version_str += "-%s" % '.'.join(str(token) for token in version.prerelease)

    if version.build is not None:
        version_str += "+%s" % version.build

    return version_str


def determine_version_delta(a: Version, b: Version, prerelase_keywords_list: list = None):
    """
    :param b:
    :param a:
    :param prerelase_keywords_list: a list of keyword lists
    used to normalize dot separated pre-release version tokens at the corresponding position.
    Note: Keywords must be in a strictly ascending order.
    :return: difference
    :rtype: VersionDelta
    """

    delta = VersionDelta()
    delta.version_a = a
    delta.version_b = b
    delta.difference = list()
    delta.resets = list()
    delta.prerelase_keywords_list = prerelase_keywords_list

    delta.difference.append(delta.version_b.major - delta.version_a.major)
    delta.difference.append(delta.version_b.minor - delta.version_a.minor)
    delta.difference.append(delta.version_b.patch - delta.version_a.patch)

    delta.resets.append(delta.version_b.major == 1)
    delta.resets.append(delta.version_b.minor == 0)
    delta.resets.append(delta.version_b.patch == 0)

    index = 0
    for sub_a, sub_b in itertools.zip_longest(delta.version_a.prerelease or [], delta.version_b.prerelease or []):
        cmp_result = cmp_alnum_token(sub_a, sub_b, None)
        delta.difference.append(cmp_result)
        if prerelase_keywords_list is not None \
                and index < len(prerelase_keywords_list) \
                and prerelase_keywords_list[index] is not None:
            token_config = prerelase_keywords_list[index]
            if isinstance(token_config, list) and len(token_config):
                delta.resets.append(sub_b == token_config[0])
            elif isinstance(token_config, int):
                delta.resets.append(sub_b == token_config)
            else:
                raise ValueError()
        else:
            delta.resets.append(sub_b == 0)
        index += 1

    return delta


def compare_version_info(a: semver.VersionInfo, b: semver.VersionInfo):
    # TODO avoid superfluous conversions
    return semver.compare(format_version_info(a), format_version_info(b))


def evaluate_numeric_increment(result: Result, field_name: str, reset: bool, reset_val: int, strict: bool, a: int,
                               b: int):
    """
    :rtype: bool
    """

    delta = b - a

    if reset:
        if b != reset_val:
            result.error(os.EX_USAGE,
                         _("Version change leaves a gap without a semantic meaning."),
                         _("The field {field_name} must be reset to {reset_val}.")
                         .format(field_name=repr(field_name)
                                 , reset_val=reset_val)
                         )
    else:
        if delta > 1:
            result.error(os.EX_USAGE if strict else os.EX_OK,
                         _("Version change leaves a gap without a semantic meaning."),
                         _("The field {field_name} must not be incremented by more than one.")
                         .format(field_name=repr(field_name))
                         )

    return reset or b > a


def evaluate_prerelease_increment(result: Result, field_name: str, index: int, reset: bool, reset_val: int or str,
                                  strict: bool,
                                  a: int or str, b: int or str,
                                  keywords: list):
    """
    :rtype: bool
    """

    delta = cmp_alnum_token(b, a, keywords)
    requires_reset = False

    if delta > 0:
        requires_reset = True

    if reset:
        if b != reset_val:
            result.error(os.EX_USAGE if strict else os.EX_OK,
                         _("Version change leaves a gap without a semantic meaning."),
                         _("The field {field_name} must be reset to {reset_val}.")
                         .format(field_name=repr(field_name + '[' + str(index) + ']'),
                                 reset_val=reset_val)
                         )
    else:
        if delta > 1:
            result.error(os.EX_USAGE if strict else os.EX_OK,
                         _("Version change leaves a gap without a semantic meaning."),
                         _("The field {field_name} must not be incremented by more than one.")
                         .format(field_name=repr(field_name + '[' + str(index) + ']'))
                         )

    return reset or requires_reset


def evaluate_version_increment(a: Version, b: Version, strict: bool, prerelase_keywords_list: list = None):
    result = Result()

    initial_version = Version()
    initial_version.major = 1
    initial_version.minor = 0
    initial_version.patch = 0
    if prerelase_keywords_list is not None and len(prerelase_keywords_list):
        initial_version.prerelease = list()
        for index, token_config in enumerate(prerelase_keywords_list):
            if token_config is not None:
                if isinstance(token_config, list) and len(token_config):
                    initial_version.prerelease.append(token_config[0])
                elif isinstance(token_config, int):
                    initial_version.prerelease.append(token_config)
                else:
                    raise ValueError()
            else:
                initial_version.prerelease.append(0)

    reset = False
    reset = evaluate_numeric_increment(result, 'major', reset, initial_version.major, strict, a.major, b.major)
    reset = evaluate_numeric_increment(result, 'minor', reset, initial_version.minor, strict, a.minor, b.minor)
    reset = evaluate_numeric_increment(result, 'patch', reset, initial_version.patch, strict, a.patch, b.patch)

    # check pre-release convention
    index = 0
    for sub_a, sub_b in itertools.zip_longest(a.prerelease or [],
                                              b.prerelease or []):
        keywords = prerelase_keywords_list[index] \
            if prerelase_keywords_list is not None \
               and index < len(prerelase_keywords_list) \
            else None
        reset = evaluate_prerelease_increment(result, "prerelease", index,
                                              reset, initial_version.prerelease[index]
                                              if initial_version.prerelease is not None
                                                 and index < len(initial_version.prerelease)
                                              else 0,
                                              strict, sub_a, sub_b, keywords)
        index += 1

    if result.has_errors():
        result.error(os.EX_USAGE if strict else os.EX_OK,
                     _("Version increment is flawed."),
                     _("A version increment from {version_a} to {version_b} is inconsistent.")
                     .format(version_a=repr(format_version(a)), version_b=repr(format_version(b)))
                     )

    return result
