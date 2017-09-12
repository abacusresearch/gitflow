import atexit
import os
import re
import shutil

import semver

from gitflow import cli, const, filesystem, repotools, _
from gitflow.common import Result
from gitflow.repotools import RepoContext
from gitflow.version import VersionMatcher, VersionConfig


class Config(object):
    property_file: str = None

    strict_mode = True

    remote_name = "origin"

    release_branch_base = None
    dev_branch_types = ['feature', 'integration',
                        'fix', 'chore', 'doc', 'issue']

    prod_branch_types = ['fix', 'chore', 'doc', 'issue']

    release_base_branch_matcher: VersionMatcher = None
    release_branch_matcher: VersionMatcher = None
    work_branch_matcher: VersionMatcher = None

    version_tag_matcher: VersionMatcher = None
    discontinuation_tag_matcher: VersionMatcher = None
    sequential_version_tag_matcher: VersionMatcher = None

    version_config: VersionConfig = None

    # Enables a sequential version counter across all release branches, effectively serializing the deployment order.
    # When enabled, any newly created release branch will cause discontinuation of its predecessors.
    # This feature is recommended in case one of these cases apply:
    # 1. The projects target platform only supports integer versions (such as the Android version code)
    # 2. Artifacts shall contain an opaque version, allowing promotion of artifacts from alpha to a stable/GA release
    # without rebuilding for according increments within the SemVer pre-release version.
    sequential_versioning = True
    commit_version_property = False
    commit_sequential_version_property = True
    # When enabled, a branch will be discontinued as soon as a successor branch receives a sequential version.
    # The only exception in this case are pre-release type increments related to an existing sequential version number.
    tie_sequential_version_to_semantic_version = True
    # TODO checks on merge base
    allow_shared_release_branch_base = False
    # TODO distinction of commit-based and purely tag based increments
    allow_qualifier_increments_within_commit = True

    # TODO config var & CLI option
    # requires clean workspace and temporary detachment from branches to be pushed
    push_to_local = False
    pull_after_bump = True


class Context(object):
    args = None
    config: Config = None
    parsed_config: Config = None
    __repo = None

    root = None
    batch = False
    assume_yes = False
    dry_run = False
    verbose = False
    pretty = False

    temp_dirs: list = None
    clones: list = None

    def __init__(self):
        atexit.register(self.cleanup)

    @staticmethod
    def create(args: dict, result_out: Result) -> 'Context':
        context = Context()
        context.parsed_config: Config = Config()

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
                                .format(required_version=repr(const.MIN_GIT_VERSION, actual_version=repr(git_version))),
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

            context.config = filesystem.JavaPropertyFile(gitflow_config_file).load()
        else:
            context.config = dict()

        # project properties config

        context.parsed_config.property_file = context.config.get(const.CONFIG_PROJECT_PROPERTY_FILE)
        if context.parsed_config.property_file is not None:
            context.parsed_config.property_file = os.path.join(context.root, context.parsed_config.property_file)

        # version config

        qualifiers = context.config.get(const.CONFIG_PRE_RELEASE_VERSION_QUALIFIERS)
        if qualifiers is None:
            qualifiers = const.DEFAULT_PRE_RELEASE_QUALIFIERS
        qualifiers = [qualifier.strip() for qualifier in qualifiers.split(",")]
        if qualifiers != sorted(qualifiers):
            result_out.fail(
                os.EX_DATAERR,
                "Configuration failed.",
                "Pre-release qualifiers are not specified in ascending order: "
                + str(sorted(qualifiers)))
        context.parsed_config.version_config = VersionConfig()
        context.parsed_config.version_config.qualifiers = qualifiers

        # branch config

        context.parsed_config.release_branch_base = context.config.get(const.CONFIG_RELEASE_BRANCH_BASE,
                                                                       const.DEFAULT_RELEASE_BRANCH_BASE)

        context.parsed_config.release_base_branch_matcher = VersionMatcher(
            ['refs/heads/', 'refs/remotes/' + context.parsed_config.remote_name + '/'],
            None,
            re.escape(context.parsed_config.release_branch_base),
        )

        context.parsed_config.release_branch_matcher = VersionMatcher(
            ['refs/heads/', 'refs/remotes/' + context.parsed_config.remote_name + '/'],
            'release/',
            context.config.get(
                const.CONFIG_RELEASE_BRANCH_PATTERN,
                const.DEFAULT_RELEASE_BRANCH_PATTERN),
        )

        context.parsed_config.work_branch_matcher = VersionMatcher(
            ['refs/heads/', 'refs/remotes/' + context.parsed_config.remote_name + '/'],
            [const.BRANCH_PREFIX_DEV, const.BRANCH_PREFIX_PROD],
            context.config.get(
                const.CONFIG_WORK_BRANCH_PATTERN,
                const.DEFAULT_WORK_BRANCH_PATTERN),
        )

        context.parsed_config.version_tag_matcher = VersionMatcher(
            ['refs/tags/'],
            'version/',
            context.config.get(
                const.CONFIG_VERSION_TAG_PATTERN,
                const.DEFAULT_VERSION_TAG_PATTERN),
        )

        context.parsed_config.discontinuation_tag_matcher = VersionMatcher(
            ['refs/tags/'],
            'discontinued/',
            context.config.get(
                const.CONFIG_DISCONTINUATION_TAG_PATTERN,
                const.DEFAULT_DISCONTINUATION_TAG_PATTERN),
        )

        context.parsed_config.sequential_version_tag_matcher = VersionMatcher(
            ['refs/tags/'],
            'sequential_version/',
            context.config.get(
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
            lambda branch_ref: self.parsed_config.release_branch_matcher.format(
                branch_ref.name) is not None,
            repotools.git_list_refs(self.repo, 'refs/remotes/' + self.parsed_config.remote_name, 'refs/heads/')
        ))
        release_branches.sort(
            reverse=True,
            key=self.parsed_config.release_branch_matcher.key_func
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
