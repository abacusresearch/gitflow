import atexit
import os
import re
import shutil
from enum import Enum

import semver

from gitflow import cli, const, filesystem, repotools, _
from gitflow.common import Result
from gitflow.repotools import RepoContext
from gitflow.version import VersionMatcher, VersionConfig


class VersioningScheme(Enum):
    # SemVer tags
    SEMVER = 1,
    # SemVer tags, sequence number tags
    SEMVER_WITH_SEQ = 2,
    # SemVer tags tied to sequence number tags in strictly ascending order
    SEMVER_WITH_TIED_SEQ = 3,


class Config(object):
    # versioning scheme
    versioning_scheme: VersioningScheme = VersioningScheme.SEMVER_WITH_TIED_SEQ
    commit_version_property = False
    commit_sequential_version_property = True

    # project properties
    property_file: str = None
    version_property_name: str = None
    sequential_version_property_name: str = None

    # validation mode
    strict_mode = True

    # version
    version_config: VersionConfig = None

    # repo
    remote_name = "origin"

    release_branch_base = None
    dev_branch_types = ['feature', 'integration',
                        'fix', 'chore', 'doc', 'issue']

    prod_branch_types = ['fix', 'chore', 'doc', 'issue']

    # hard config

    # TODO checks on merge base
    allow_shared_release_branch_base = False
    # TODO distinction of commit-based and purely tag based increments
    allow_qualifier_increments_within_commit = True

    # TODO config var & CLI option
    # requires clean workspace and temporary detachment from branches to be pushed
    push_to_local = False
    pull_after_bump = True

    # properties
    @property
    def sequential_versioning(self):
        return self.versioning_scheme in (VersioningScheme.SEMVER_WITH_SEQ,
                                          VersioningScheme.SEMVER_WITH_TIED_SEQ)

    @property
    def tie_sequential_version_to_semantic_version(self):
        return self.versioning_scheme == VersioningScheme.SEMVER_WITH_TIED_SEQ


class Context(object):
    config: Config = None
    __repo = None

    # args
    args = None

    root = None
    batch = False
    assume_yes = False
    dry_run = False
    verbose = False
    pretty = False

    # matchers
    release_base_branch_matcher: VersionMatcher = None
    release_branch_matcher: VersionMatcher = None
    work_branch_matcher: VersionMatcher = None

    version_tag_matcher: VersionMatcher = None
    discontinuation_tag_matcher: VersionMatcher = None
    sequential_version_tag_matcher: VersionMatcher = None

    # resources
    temp_dirs: list = None
    clones: list = None

    def __init__(self):
        atexit.register(self.cleanup)

    @staticmethod
    def create(args: dict, result_out: Result) -> 'Context':
        context = Context()
        context.config: Config = Config()

        if args is not None:
            context.args = args

            context.batch = context.args['--batch']
            context.assume_yes = context.args.get('--assume-yes')
            context.dry_run = context.args.get('--dry-run')
            context.verbose = context.args['--verbose']
            context.pretty = context.args['--pretty']
        else:
            context.args = dict()

        # configure CLI
        cli.set_allow_color(not context.batch)

        # initialize repo context and attempt to load the config file
        if '--root' in context.args and context.args['--root'] is not None:
            context.root = context.args['--root']

            context.__repo = RepoContext()
            context.__repo.dir = context.root
            context.__repo.verbose = context.verbose

            git_version = repotools.git_version(context.__repo)
            if semver.compare(git_version, const.MIN_GIT_VERSION) < 0:
                result_out.fail(os.EX_UNAVAILABLE,
                                _("git {required_version} or newer required, got {actual_version}.")
                                .format(required_version=repr(const.MIN_GIT_VERSION), actual_version=repr(git_version)),
                                None
                                )

            root = repotools.git_rev_parse(context.__repo, '--show-toplevel')
            # None when invalid or bare
            if root is not None:
                context.__repo.dir = root

                if context.verbose >= const.TRACE_VERBOSITY:
                    cli.print("--------------------------------------------------------------------------------")
                    cli.print("refs in {repo}:".format(repo=context.__repo.dir))
                    cli.print("--------------------------------------------------------------------------------")
                    for ref in repotools.git_list_refs(context.__repo):
                        cli.print(repr(ref))
                    cli.print("--------------------------------------------------------------------------------")

            gitflow_config_file = os.path.join(context.__repo.dir, context.args['--config'])
            if context.verbose >= const.TRACE_VERBOSITY:
                cli.print("gitflow_config_file: " + gitflow_config_file)

            if not os.path.isfile(gitflow_config_file):
                result_out.fail(os.EX_DATAERR,
                                _("gitflow_config_file does not exist or is not a regular file: {path}.")
                                .format(path=repr(gitflow_config_file)),
                                None
                                )

            config = filesystem.JavaPropertyFile(gitflow_config_file).load()
        else:
            config = dict()

        # project properties config

        context.config.property_file = config.get(const.CONFIG_PROJECT_PROPERTY_FILE)
        if context.config.property_file is not None:
            context.config.property_file = os.path.join(context.root, context.config.property_file)

        context.config.version_property_name = config.get(const.CONFIG_VERSION_PROPERTY_NAME)
        context.config.sequential_version_property_name = config.get(
            const.CONFIG_SEQUENTIAL_VERSION_PROPERTY_NAME)

        # version config

        qualifiers = config.get(const.CONFIG_PRE_RELEASE_VERSION_QUALIFIERS)
        if qualifiers is None:
            qualifiers = const.DEFAULT_PRE_RELEASE_QUALIFIERS
        qualifiers = [qualifier.strip() for qualifier in qualifiers.split(",")]
        if qualifiers != sorted(qualifiers):
            result_out.fail(
                os.EX_DATAERR,
                _("Configuration failed."),
                _("Pre-release qualifiers are not specified in ascending order.")
            )
        context.config.version_config = VersionConfig()
        context.config.version_config.qualifiers = qualifiers

        # branch config

        context.config.release_branch_base = config.get(const.CONFIG_RELEASE_BRANCH_BASE,
                                                        const.DEFAULT_RELEASE_BRANCH_BASE)

        remote_prefix = repotools.create_ref_name(const.REMOTES_PREFIX, context.config.remote_name)

        context.release_base_branch_matcher = VersionMatcher(
            [const.LOCAL_BRANCH_PREFIX, remote_prefix],
            None,
            re.escape(context.config.release_branch_base),
        )

        context.release_branch_matcher = VersionMatcher(
            [const.LOCAL_BRANCH_PREFIX, remote_prefix],
            'release/',
            config.get(
                const.CONFIG_RELEASE_BRANCH_PATTERN,
                const.DEFAULT_RELEASE_BRANCH_PATTERN),
        )

        context.work_branch_matcher = VersionMatcher(
            [const.LOCAL_BRANCH_PREFIX, remote_prefix],
            [const.BRANCH_PREFIX_DEV, const.BRANCH_PREFIX_PROD],
            config.get(
                const.CONFIG_WORK_BRANCH_PATTERN,
                const.DEFAULT_WORK_BRANCH_PATTERN),
        )

        context.version_tag_matcher = VersionMatcher(
            [const.LOCAL_TAG_PREFIX],
            'version/',
            config.get(
                const.CONFIG_VERSION_TAG_PATTERN,
                const.DEFAULT_VERSION_TAG_PATTERN),
        )

        context.discontinuation_tag_matcher = VersionMatcher(
            [const.LOCAL_TAG_PREFIX],
            'discontinued/',
            config.get(
                const.CONFIG_DISCONTINUATION_TAG_PATTERN,
                const.DEFAULT_DISCONTINUATION_TAG_PATTERN),
        )

        context.sequential_version_tag_matcher = VersionMatcher(
            [const.LOCAL_TAG_PREFIX],
            'sequential_version/',
            config.get(
                const.CONFIG_SEQUENTIAL_VERSION_TAG_PATTERN,
                const.DEFAULT_SEQUENTIAL_VERSION_TAG_PATTERN),
            '{unique_code}')

        return context

    def add_temp_dir(self, dir):
        if self.temp_dirs is None:
            self.temp_dirs = list()
        self.temp_dirs.append(dir)
        pass

    @property
    def repo(self):
        return self.__repo

    def get_release_branches(self):
        release_branches = list(filter(
            lambda branch_ref: self.release_branch_matcher.format(
                branch_ref.name) is not None,
            repotools.git_list_refs(self.repo,
                                    repotools.create_ref_name(const.REMOTES_PREFIX, self.config.remote_name),
                                    const.LOCAL_BRANCH_PREFIX)
        ))
        release_branches.sort(
            reverse=True,
            key=self.release_branch_matcher.key_func
        )
        return release_branches

    def cleanup(self):
        atexit.unregister(self.cleanup)
        if self.temp_dirs is not None:
            for temp_dir in self.temp_dirs:
                shutil.rmtree(temp_dir)
            self.temp_dirs = None
        if self.clones is not None:
            for clone in self.clones:
                clone.cleanup()
            self.clones = None

    def __del__(self):
        self.cleanup()
