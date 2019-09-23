import atexit
import os
import re
import shutil
from enum import Enum
from typing import List, Optional

import collections

from gitflow import cli, const, repotools, _, utils
from gitflow.common import Result
from gitflow.const import VersioningScheme
from gitflow.procedures.scheme.versioning_scheme import VersioningSchemeImpl
from gitflow.properties import PropertyIO
from gitflow.repotools import RepoContext
from gitflow.version import SemVerVersionMatcher, VersionConfig


class BuildStepType(Enum):
    ASSEMBLE = 'assemble',

    TEST = 'test',
    INTEGRATION_TEST = 'integration_test',

    PACKAGE = 'package',
    DEPLOY = 'deploy'


class BuildLabels(Enum):
    OPENSHIFT_S2I_TEST = 'com.openshift:s2i'


class BuildStep(object):
    name: str = None
    commands: list = None
    """a list of command arrays"""
    labels: set = None
    """contains labels for mapping to the ci tasks, effectively extending the label set in the enclosing stage"""


class BuildStage(object):
    type: str
    steps: list = None
    labels: list = None
    """contains labels for mapping to ci tasks"""

    def __init__(self):
        self.steps = list()
        self.labels = list()


class Config(object):
    # project properties
    property_file: str = None
    sequence_number_property: str = None
    version_property: str = None

    # validation mode
    strict_mode = True

    # version
    version_config: VersionConfig = None

    # repo
    remote_name = None

    release_branch_base = None

    dev_branch_types = ['feature', 'integration',
                        'fix', 'chore', 'doc', 'issue']

    prod_branch_types = ['fix', 'chore', 'doc', 'issue']

    # build config
    version_change_actions: List[List[str]] = None

    build_stages: list = None

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
    def sequential_versioning(self) -> bool:
        return self.version_config.versioning_scheme == VersioningScheme.SEMVER_WITH_SEQ

    @property
    def tie_sequential_version_to_semantic_version(self) -> bool:
        return self.version_config.versioning_scheme == VersioningScheme.SEMVER_WITH_SEQ

    @property
    def commit_version_property(self) -> bool:
        return self.version_property is not None

    @property
    def commit_sequential_version_property(self) -> bool:
        return self.sequence_number_property is not None \
               and self.sequential_versioning

    @property
    def requires_property_commits(self) -> bool:
        return self.commit_version_property \
               or self.commit_sequential_version_property


class AbstractContext(object):
    result: Result = None

    def __init__(self):
        self.result = Result()

    def warn(self, message, reason):
        self.result.warn(message, reason)

    def error(self, exit_code, message, reason, throw: bool = False):
        self.result.error(exit_code, message, reason, throw)

    def fail(self, exit_code, message, reason):
        self.result.fail(exit_code, message, reason)

    def add_subresult(self, subresult):
        self.result.add_subresult(subresult)

    def has_errors(self):
        return self.result.has_errors()

    def abort_on_error(self):
        return self.result.abort_on_error()

    def abort(self):
        return self.result.abort()


class Context(AbstractContext):
    config_properties: dict = {}
    config: Config = None
    repo: RepoContext = None

    # args
    args = None

    root = None
    batch = False
    assume_yes = False
    dry_run = False
    verbose = const.ERROR_VERBOSITY
    pretty = False

    # matchers
    # TODO remove
    @property
    def release_base_branch_matcher(self) -> SemVerVersionMatcher:
        return self.versioning_scheme.release_base_branch_matcher

    @property
    def release_branch_matcher(self) -> SemVerVersionMatcher:
        return self.versioning_scheme.release_branch_matcher

    @property
    def work_branch_matcher(self) -> SemVerVersionMatcher:
        return self.versioning_scheme.work_branch_matcher

    @property
    def version_tag_matcher(self) -> SemVerVersionMatcher:
        return self.versioning_scheme.version_tag_matcher

    @property
    def discontinuation_tag_matcher(self) -> SemVerVersionMatcher:
        return self.versioning_scheme.discontinuation_tag_matcher

    # version scheme implementation
    versioning_scheme: VersioningSchemeImpl = None

    # resources
    temp_dirs: list = None
    clones: list = None

    # misc
    git_version: str = None

    def __init__(self):
        super().__init__()
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
            # TODO remove this workaround
            context.verbose = (context.args['--verbose'] + 1) // 2
            context.pretty = context.args['--pretty']
        else:
            context.args = dict()

        # configure CLI
        cli.set_allow_color(not context.batch)

        # initialize repo context and attempt to load the config file
        if '--root' in context.args and context.args['--root'] is not None:
            context.root = context.args['--root']

            context.repo = RepoContext()
            context.repo.dir = context.root
            context.repo.verbose = context.verbose

            context.git_version = repotools.git_version(context.repo)
            # context.repo.use_root_dir_arg = semver.compare(context.git_version, "2.9.0") >= 0
            context.repo.use_root_dir_arg = False

            repo_root = repotools.git_rev_parse(context.repo, '--show-toplevel')

            # None when invalid or bare
            if repo_root is not None:
                context.repo.dir = repo_root

                if context.verbose >= const.TRACE_VERBOSITY:
                    cli.print("--------------------------------------------------------------------------------")
                    cli.print("refs in {repo}:".format(repo=context.repo.dir))
                    cli.print("--------------------------------------------------------------------------------")
                    for ref in repotools.git_list_refs(context.repo):
                        cli.print(repr(ref))
                    cli.print("--------------------------------------------------------------------------------")
                config_dir = context.repo.dir
            else:
                context.repo = None
                config_dir = context.root

            gitflow_config_file: Optional[str] = None
            if context.args['--config'] is not None:
                gitflow_config_file = os.path.join(config_dir, context.args['--config'])
                if gitflow_config_file is None:
                    result_out.fail(os.EX_DATAERR,
                                    _("the specified config file does not exist or is not a regular file: {path}.")
                                    .format(path=repr(gitflow_config_file)),
                                    None
                                    )
            else:
                for config_filename in const.DEFAULT_CONFIGURATION_FILE_NAMES:
                    path = os.path.join(config_dir, config_filename)
                    if os.path.exists(path):
                        gitflow_config_file = path
                        break
                if gitflow_config_file is None:
                    result_out.fail(os.EX_DATAERR,
                                    _("config file not found.")
                                    .format(path=repr(gitflow_config_file)),
                                    _("Default config files are\n:{list}")
                                    .format(list=const.DEFAULT_CONFIGURATION_FILE_NAMES)
                                    )

            if context.verbose >= const.TRACE_VERBOSITY:
                cli.print("gitflow_config_file: " + gitflow_config_file)

            with open(gitflow_config_file) as json_file:
                config = PropertyIO.get_instance_by_filename(gitflow_config_file).from_stream(json_file)
        else:
            config = object()

        context.config_properties = config

        build_config_json = config.get(const.CONFIG_BUILD)

        context.config.version_change_actions = config.get(const.CONFIG_ON_VERSION_CHANGE, [])

        context.config.build_stages = list()

        if build_config_json is not None:
            stages_json = build_config_json.get('stages')
            if stages_json is not None:
                for stage_key, stage_json in stages_json.items():

                    stage = BuildStage()

                    if isinstance(stage_json, dict):
                        stage.type = stage_json.get('type') or stage_key
                        if stage.type not in const.BUILD_STAGE_TYPES:
                            result_out.fail(
                                os.EX_DATAERR,
                                _("Configuration failed."),
                                _("Invalid build stage type {key}."
                                  .format(key=repr(stage.type)))
                            )

                        stage.name = stage_json.get('name') or stage_key

                        stage_labels = stage_json.get('labels')
                        if isinstance(stage_labels, list):
                            stage.labels.extend(stage_labels)
                        else:
                            stage.labels.append(stage_labels)

                        stage_steps_json = stage_json.get('steps')
                        if stage_steps_json is not None:
                            for step_key, step_json in stage_steps_json.items():
                                step = BuildStep()

                                if isinstance(step_json, dict):
                                    step.name = step_json.get('name') or step_key
                                    step.commands = step_json.get('commands')

                                    stage_labels = stage_json.get('labels')
                                    if isinstance(stage_labels, list):
                                        stage.labels.extend(stage_labels)
                                    else:
                                        stage.labels.append(stage_labels)
                                elif isinstance(step_json, list):
                                    step.name = step_key
                                    step.type = step_key
                                    step.commands = step_json
                                else:
                                    result_out.fail(
                                        os.EX_DATAERR,
                                        _("Configuration failed."),
                                        _("Invalid build step definition {type} {key}."
                                          .format(type=repr(type(step_json)), key=repr(step_key)))
                                    )

                                stage.steps.append(step)
                    elif isinstance(stage_json, list):
                        stage.type = stage_key
                        stage.name = stage_key

                        if len(stage_json):
                            step = BuildStep()
                            step.name = '#'
                            step.commands = stage_json
                            stage.steps.append(step)
                    else:
                        result_out.fail(
                            os.EX_DATAERR,
                            _("Configuration failed."),
                            _("Invalid build stage definition {key}."
                              .format(key=repr(stage_key)))
                        )
                    context.config.build_stages.append(stage)

        context.config.build_stages.sort(key=utils.cmp_to_key(lambda stage_a, stage_b:
                                                              const.BUILD_STAGE_TYPES.index(stage_a.type)
                                                              - const.BUILD_STAGE_TYPES.index(stage_b.type)
                                                              ),
                                         reverse=False
                                         )

        # project properties config

        context.config.property_file = config.get(const.CONFIG_PROJECT_PROPERTY_FILE)
        if context.config.property_file is not None:
            context.config.property_file = os.path.join(context.root, context.config.property_file)

        context.config.version_property = config.get(const.CONFIG_VERSION_PROPERTY)
        context.config.sequence_number_property = config.get(
            const.CONFIG_SEQUENCE_NUMBER_PROPERTY)
        context.config.version_property = config.get(
            const.CONFIG_VERSION_PROPERTY)

        property_names = [property for property in
                          [context.config.sequence_number_property, context.config.version_property] if
                          property is not None]
        duplicate_property_names = [item for item, count in collections.Counter(property_names).items() if count > 1]

        if len(duplicate_property_names):
            result_out.fail(os.EX_DATAERR, _("Configuration failed."),
                            _("Duplicate property names: {duplicate_property_names}").format(
                                duplicate_property_names=', '.join(duplicate_property_names))
                            )

        # version config

        context.config.version_config = VersionConfig()

        versioning_scheme = config.get(const.CONFIG_VERSIONING_SCHEME, const.DEFAULT_VERSIONING_SCHEME)

        if versioning_scheme not in const.VERSIONING_SCHEMES:
            result_out.fail(os.EX_DATAERR, _("Configuration failed."),
                            _("The versioning scheme {versioning_scheme} is invalid.").format(
                                versioning_scheme=utils.quote(versioning_scheme, '\'')))

        context.config.remote_name = "origin"
        context.config.version_config.versioning_scheme = const.VERSIONING_SCHEMES[versioning_scheme]
        context.config.release_branch_base = config.get(const.CONFIG_RELEASE_BRANCH_BASE,
                                                        const.DEFAULT_RELEASE_BRANCH_BASE)

        if context.config.version_config.versioning_scheme == VersioningScheme.SEMVER:
            from gitflow.procedures.scheme.semver import SemVer
            context.versioning_scheme = SemVer(context)

            qualifiers = config.get(const.CONFIG_VERSION_TYPES, const.DEFAULT_PRE_RELEASE_QUALIFIERS)
            if isinstance(qualifiers, str):
                qualifiers = [qualifier.strip() for qualifier in qualifiers.split(",")]
            if qualifiers != sorted(qualifiers):
                result_out.fail(
                    os.EX_DATAERR,
                    _("Configuration failed."),
                    _("Pre-release qualifiers are not specified in ascending order.")
                )
            context.config.version_config.qualifiers = qualifiers
            context.config.version_config.initial_version = const.DEFAULT_INITIAL_VERSION
        elif context.config.version_config.versioning_scheme == VersioningScheme.SEMVER_WITH_SEQ:
            from gitflow.procedures.scheme.semver import SemVer
            context.versioning_scheme = SemVer(context)

            context.config.version_config.qualifiers = None
            context.config.version_config.initial_version = const.DEFAULT_INITIAL_SEQ_VERSION
        elif context.config.version_config.versioning_scheme == VersioningScheme.CANONICAL_DATETIME:
            from gitflow.procedures.scheme.canonical_datetime import CanonicalDateTime
            context.versioning_scheme = CanonicalDateTime(context)

            context.config.version_config.qualifiers = None
            context.config.version_config.initial_version = '1'

            context.config.allow_qualifier_increments_within_commit = False

        return context

    def add_temp_dir(self, dir):
        if self.temp_dirs is None:
            self.temp_dirs = list()
        self.temp_dirs.append(dir)
        pass

    def get_release_branches(self, reverse: bool = True):
        release_branches = list(filter(
            lambda branch_ref: self.release_branch_matcher.fullmatch(branch_ref.name) is not None,
            repotools.git_list_refs(self.repo,
                                    repotools.create_ref_name(const.REMOTES_PREFIX, self.config.remote_name))
        ))
        release_branches.sort(
            reverse=reverse,
            key=self.release_branch_matcher.key_func
        )
        return release_branches

    def cleanup(self):
        atexit.unregister(self.cleanup)
        if self.temp_dirs is not None:
            for temp_dir in self.temp_dirs:
                if self.verbose >= const.DEBUG_VERBOSITY:
                    cli.print("deleting temp dir: " + temp_dir)
                shutil.rmtree(temp_dir)
            self.temp_dirs.clear()
        if self.clones is not None:
            for clone in self.clones:
                clone.cleanup()
            self.clones.clear()

    def __del__(self):
        self.cleanup()
