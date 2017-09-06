import os

import semver

from gitflow import cli, const, filesystem, repotools, _
from gitflow.repotools import RepoContext
from gitflow.version import VersionMatcher, VersionConfig


class Config(object):
    strict_mode = True

    remote_name = "origin"

    release_branch_base = None
    release_branch_matcher = None

    version_tag_matcher = None
    discontinuation_tag_matcher = None
    sequential_version_tag_matcher = None

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
    parsed_config = None
    __property_store = None
    __repo = None

    root = None
    batch = False
    assume_yes = False
    dry_run = False
    verbose = False
    pretty = False

    def __init__(self, args):
        self.parsed_config: Config = Config()

        if args is not None:
            self.args = args

            self.batch = self.args['--batch']
            self.assume_yes = self.args.get('--assume-yes')
            self.dry_run = self.args.get('--dry-run')
            self.verbose = self.args['--verbose']
            self.pretty = self.args['--pretty']
        else:
            self.args = dict()

        # configure CLI
        cli.set_allow_color(not self.batch)

        # initialize repo context and attempt to load the config file
        if '--root' in self.args and self.args['--root'] is not None:
            self.root = self.args['--root']

            self.__repo = RepoContext()
            self.__repo.dir = self.root
            self.__repo.verbose = self.verbose

            git_version = repotools.git_version(self.__repo)
            if semver.compare(git_version, const.MIN_GIT_VERSION) < 0:
                cli.fail(os.EX_UNAVAILABLE,
                              _("git {required_version} or newer required, got {actual_version}.")
                              .format(required_version=repr(const.MIN_GIT_VERSION, actual_version=repr(git_version)))
                              )

            root = repotools.git_rev_parse(self.__repo, '--show-toplevel')
            # None when invalid or bare
            if root is not None:
                self.__repo.dir = root

            gitflow_config_file = os.path.join(self.__repo.dir, self.args['--config'])
            if self.verbose >= const.TRACE_VERBOSITY:
                cli.print("gitflow_config_file: " + gitflow_config_file)

            if not os.path.isfile(gitflow_config_file):
                cli.fail(os.EX_DATAERR,
                              _("gitflow_config_file does not exist or is not a regular file: {path}.")
                              .format(path=repr(gitflow_config_file))
                              )

            self.config = filesystem.JavaPropertyFile(gitflow_config_file).load()
        else:
            self.config = dict()

        # project properties config

        property_file = self.config.get(const.CONFIG_VERSION_PROPERTY_FILE)
        if property_file is not None:
            property_file = os.path.join(self.root, property_file)
        version_property_name = self.config.get(const.CONFIG_VERSION_PROPERTY_NAME)

        if property_file is not None:
            if property_file.endswith(".properties"):
                self.__property_store = filesystem.JavaPropertyFile(property_file)
            else:
                cli.fail(os.EX_DATAERR,
                              _("property file not supported: {path}\n"
                                "Currently supported:\n"
                                "{listing}")
                              .format(path=repr(property_file),
                                      listing='\n'.join(' - ' + type for type in ['*.properties']))
                              )

        # version config

        qualifiers = self.config.get(const.CONFIG_PRE_RELEASE_VERSION_QUALIFIERS)
        if qualifiers is None:
            qualifiers = const.DEFAULT_PRE_RELEASE_QUALIFIERS
        qualifiers = [qualifier.strip() for qualifier in qualifiers.split(",")]
        if qualifiers != sorted(qualifiers):
            cli.fail(
                os.EX_DATAERR,
                "Configuration failed.",
                "Pre-release qualifiers are not specified in ascending order: "
                + str(sorted(qualifiers)))
        self.parsed_config.version_config = VersionConfig()
        self.parsed_config.version_config.qualifiers = qualifiers

        # branch config

        self.parsed_config.release_branch_base = self.config.get(const.CONFIG_RELEASE_BRANCH_BASE,
                                                                 const.DEFAULT_RELEASE_BRANCH_BASE)

        self.parsed_config.release_branch_matcher = VersionMatcher(
            ['refs/heads/', 'refs/remotes/' + self.parsed_config.remote_name + '/'],
            'release/',
            self.config.get(
                const.CONFIG_RELEASE_BRANCH_PATTERN,
                const.DEFAULT_RELEASE_BRANCH_PATTERN),
        )

        self.parsed_config.version_tag_matcher = VersionMatcher(
            ['refs/tags/'],
            'version/',
            self.config.get(
                const.CONFIG_VERSION_TAG_PATTERN,
                const.DEFAULT_VERSION_TAG_PATTERN),
        )

        self.parsed_config.discontinuation_tag_matcher = VersionMatcher(
            ['refs/tags/'],
            'discontinued/',
            self.config.get(
                const.CONFIG_DISCONTINUATION_TAG_PATTERN,
                const.DEFAULT_DISCONTINUATION_TAG_PATTERN),
        )

        self.parsed_config.sequential_version_tag_matcher = VersionMatcher(
            ['refs/tags/'],
            'sequential_version/',
            self.config.get(
                const.CONFIG_SEQUENTIAL_VERSION_TAG_PATTERN,
                const.DEFAULT_SEQUENTIAL_VERSION_TAG_PATTERN),
            '{unique_code}')

    @property
    def repo(self):
        return self.__repo

    def load_project_properties(self):
        if self.__property_store:
            return self.__property_store.load()
        else:
            return None

    def store_project_properties(self, properties):
        if self.__property_store:
            return self.__property_store.store(properties)
        else:
            cli.fail(os.EX_SOFTWARE,
                          _("Failed to save properties."
                            "Missing property store."))

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
