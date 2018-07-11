import atexit
import json
import os
import re
import shutil
from enum import Enum

from gitflow import cli, const, repotools, _, utils
from gitflow.common import Result
from gitflow.const import VersioningScheme
from gitflow.repotools import RepoContext
from gitflow.version import VersionMatcher, VersionConfig


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
    labels: set = None
    """contains labels for mapping to ci tasks"""

    def __init__(self):
        self.steps = list()
        self.labels = list()


class Config(object):
    # project properties
    property_file: str = None
    version_property_name: str = None
    sequential_version_property_name: str = None
    opaque_version_property_name: str = None

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
        return self.version_property_name is not None

    @property
    def commit_sequential_version_property(self) -> bool:
        return self.sequential_version_property_name is not None \
               and self.sequential_versioning

    @property
    def commit_opaque_version_property(self) -> bool:
        return self.opaque_version_property_name is not None \
               and self.sequential_versioning

    @property
    def requires_property_commits(self) -> bool:
        return self.commit_version_property \
               or self.commit_sequential_version_property \
               or self.commit_opaque_version_property


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
    release_base_branch_matcher: VersionMatcher = None
    release_branch_matcher: VersionMatcher = None
    work_branch_matcher: VersionMatcher = None

    version_tag_matcher: VersionMatcher = None
    discontinuation_tag_matcher: VersionMatcher = None

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

            root = repotools.git_rev_parse(context.repo, '--show-toplevel')
            # None when invalid or bare
            if root is not None:
                context.repo.dir = root

                if context.verbose >= const.TRACE_VERBOSITY:
                    cli.print("--------------------------------------------------------------------------------")
                    cli.print("refs in {repo}:".format(repo=context.repo.dir))
                    cli.print("--------------------------------------------------------------------------------")
                    for ref in repotools.git_list_refs(context.repo):
                        cli.print(repr(ref))
                    cli.print("--------------------------------------------------------------------------------")
                gitflow_config_file = os.path.join(context.repo.dir, context.args['--config'])
            else:
                context.repo = None
                gitflow_config_file = os.path.join(context.root, context.args['--config'])

            if context.verbose >= const.TRACE_VERBOSITY:
                cli.print("gitflow_config_file: " + gitflow_config_file)

            if not os.path.isfile(gitflow_config_file):
                result_out.fail(os.EX_DATAERR,
                                _("gitflow_config_file does not exist or is not a regular file: {path}.")
                                .format(path=repr(gitflow_config_file)),
                                None
                                )

            with open(gitflow_config_file) as json_file:
                config = json.load(fp=json_file)
        else:
            config = object()

        build_config_json = config.get(const.CONFIG_BUILD)

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

        context.config.version_property_name = config.get(const.CONFIG_VERSION_PROPERTY_NAME)
        context.config.sequential_version_property_name = config.get(
            const.CONFIG_SEQUENTIAL_VERSION_PROPERTY_NAME)
        context.config.opaque_version_property_name = config.get(
            const.CONFIG_OPAQUE_VERSION_PROPERTY_NAME)

        # version config

        context.config.version_config = VersionConfig()

        versioning_scheme = config.get(const.CONFIG_VERSIONING_SCHEME, const.DEFAULT_VERSIONING_SCHEME)

        if versioning_scheme not in const.VERSIONING_SCHEMES:
            result_out.fail(os.EX_DATAERR, _("Configuration failed."),
                            _("The versioning scheme {versioning_scheme} is invalid.").format(
                                versioning_scheme=utils.quote(versioning_scheme, '\'')))

        context.config.version_config.versioning_scheme = const.VERSIONING_SCHEMES[versioning_scheme]

        if context.config.version_config.versioning_scheme == VersioningScheme.SEMVER:
            qualifiers = config.get(const.CONFIG_PRE_RELEASE_QUALIFIERS)
            if qualifiers is None:
                qualifiers = const.DEFAULT_PRE_RELEASE_QUALIFIERS
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
            context.config.version_config.qualifiers = None
            context.config.version_config.initial_version = const.DEFAULT_INITIAL_SEQ_VERSION
        else:
            context.fail(os.EX_CONFIG, "configuration error", "invalid versioning scheme")

        # branch config

        context.config.remote_name = "origin"
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
            config.get(
                const.CONFIG_RELEASE_BRANCH_PREFIX,
                const.DEFAULT_RELEASE_BRANCH_PREFIX),
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
            config.get(
                const.CONFIG_VERSION_TAG_PREFIX,
                const.DEFAULT_VERSION_TAG_PREFIX),
            config.get(
                const.CONFIG_VERSION_TAG_PATTERN,
                const.DEFAULT_SEMVER_VERSION_TAG_PATTERN
                if context.config.version_config.versioning_scheme == VersioningScheme.SEMVER
                else const.DEFAULT_SEMVER_WITH_SEQ_VERSION_TAG_PATTERN)
        )
        context.version_tag_matcher.group_unique_code = None \
            if context.config.version_config.versioning_scheme == VersioningScheme.SEMVER \
            else 'prerelease_type'

        context.discontinuation_tag_matcher = VersionMatcher(
            [const.LOCAL_TAG_PREFIX],
            config.get(
                const.CONFIG_DISCONTINUATION_TAG_PREFIX,
                const.DEFAULT_DISCONTINUATION_TAG_PREFIX),
            config.get(
                const.CONFIG_DISCONTINUATION_TAG_PATTERN,
                const.DEFAULT_DISCONTINUATION_TAG_PATTERN),
            None
        )

        return context

    def add_temp_dir(self, dir):
        if self.temp_dirs is None:
            self.temp_dirs = list()
        self.temp_dirs.append(dir)
        pass

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
                if self.verbose >= const.DEBUG_VERBOSITY:
                    cli.print("deleting temp dir: " + temp_dir)
                shutil.rmtree(temp_dir)
            self.temp_dirs = None
        if self.clones is not None:
            for clone in self.clones:
                clone.cleanup()
            self.clones = None

    def __del__(self):
        self.cleanup()
