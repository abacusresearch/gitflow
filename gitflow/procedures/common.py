# TODO
# * Handle unpushed commits
# * Validate handle selective version bumps (e.g. search history for the reusable commit
#   when bumping the pre-release type).
# * parameter for slection remote(s) to operate on
# * Interactive confirmations for:
#   - version gaps
#   - potentially undesired effects
#   - operations involving a push
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
from typing import Union

import semver

from gitflow import cli, _, filesystem, utils
from gitflow import const
from gitflow import repotools
from gitflow import version
from gitflow.common import Result
from gitflow.context import Context
from gitflow.properties import PropertyIO
from gitflow.repotools import BranchSelection, git_get_current_branch, RepoContext


class CommitInfo(object):
    message_parts: list = None
    parents: list = None
    files: list = None

    def __init__(self):
        self.message_parts = list()
        self.parents = list()
        self.files = list()

    def add_parent(self, parent: str):
        self.parents.append(parent)

    def add_message(self, message: str):
        self.message_parts.append(message)

    def add_file(self, file: str):
        if file not in self.files:
            self.files.append(file)

    @property
    def message(self) -> str:
        return '\n'.join(self.message_parts) + ('\n' if len(self.message_parts) else '')


class BranchInfo(object):
    ref: repotools.Ref = None
    ref_is_local: bool = None
    local: list = None
    local_class: list = None
    upstream: repotools.Ref = None
    upstream_class: const.BranchClass = None


class CommandContext(object):
    object_arg: str = None
    context: Context = None
    result: Result = None

    selected_ref: repotools.Ref = None
    selected_branch: BranchInfo = None
    selected_commit: str = None
    selected_explicitly: bool = None

    current_branch: repotools.Ref = None
    affected_main_branches: list = None

    branch_info_dict = None
    upstreams: dict = None
    downstreams: dict = None

    def __init__(self):
        self.branch_info_dict = dict()
        self.result = Result()

    def warn(self, message, reason):
        self.context.warn(message, reason)

    def error(self, exit_code, message, reason, throw: bool = False):
        self.context.error(exit_code, message, reason, throw)

    def fail(self, exit_code, message, reason):
        self.context.fail(exit_code, message, reason)

    def add_subresult(self, subresult):
        self.context.add_subresult(subresult)

    def has_errors(self):
        return self.context.has_errors()

    def abort_on_error(self):
        return self.context.abort_on_error()

    def abort(self):
        return self.context.abort()


def select_ref(result_out: Result, branch_info: BranchInfo, selection: BranchSelection) \
        -> [repotools.Ref, const.BranchClass]:
    if branch_info.local is not None and len(branch_info.local) and branch_info.upstream is not None:
        if branch_info.local_class[0] != branch_info.upstream_class:
            result_out.error(os.EX_DATAERR,
                             _("Local and upstream branch have a mismatching branch class."),
                             None)
        if not branch_info.upstream.short_name.endswith('/' + branch_info.local[0].short_name):
            result_out.error(os.EX_DATAERR,
                             _("Local and upstream branch have a mismatching short name."),
                             None)

    candidate = None
    candidate_class = None
    if selection == BranchSelection.BRANCH_PREFER_LOCAL:
        candidate = branch_info.local[0] or branch_info.upstream
        candidate_class = branch_info.local_class[0] or branch_info.upstream_class
    elif selection == BranchSelection.BRANCH_LOCAL_ONLY:
        candidate = branch_info.local[0]
        candidate_class = branch_info.local_class[0]
    elif selection == BranchSelection.BRANCH_PREFER_REMOTE:
        candidate = branch_info.upstream or branch_info.local[0]
        candidate_class = branch_info.upstream_class or branch_info.local_class[0]
    elif selection == BranchSelection.BRANCH_REMOTE_ONLY:
        candidate = branch_info.upstream
        candidate_class = branch_info.upstream_class
    return candidate, candidate_class


def git(context: RepoContext, command: list) -> int:
    returncode, out, err = repotools.git(context, *command)
    return returncode


def git_or_fail(context: RepoContext, result: Result, command: list,
                error_message: str = None, error_reason: str = None):
    returncode = git(context, command)
    if returncode != os.EX_OK:
        if error_message is not None:
            result.fail(os.EX_DATAERR, error_message, error_reason)
        else:
            first_command_token = next(filter(lambda token: not token.startswith('-'), command))
            result.fail(os.EX_DATAERR, _("git {sub_command} failed.")
                        .format(sub_command=repr(first_command_token)),
                        error_reason
                        )


def git_for_line_or_fail(context: RepoContext, result: Result, command: list,
                         error_message: str = None, error_reason: str = None):
    line = repotools.git_for_line(context, *command)
    if line is None:
        if error_message is not None:
            result.fail(os.EX_DATAERR, error_message, error_reason)
        else:
            result.fail(os.EX_DATAERR, _("git {sub_command} failed.")
                        .format(sub_command=repr(utils.command_to_str(command))),
                        error_reason
                        )
    return line


def fetch_all_and_ff(context: RepoContext, result_out: Result, remote: [repotools.Remote, str]):
    # attempt a complete fetch and a fast forward on the current branch
    remote_name = remote.name if isinstance(remote, repotools.Remote) else remote
    returncode, out, err = repotools.git(context, 'fetch', '--tags', remote_name)
    if returncode != os.EX_OK:
        result_out.warn(
            _("Failed to fetch from {remote}")
                .format(repr(remote_name)),
            None)

    returncode, out, err = repotools.git(context, 'merge', '--ff-only')
    if returncode != os.EX_OK:
        result_out.warn(
            _("Failed to fast forward"),
            None)


def get_branch_class(context: Context, ref: Union[repotools.Ref, str]):
    ref_name = repotools.ref_name(ref)

    # TODO optimize
    branch_class = None
    branch_classes = list()
    if context.release_base_branch_matcher.fullmatch(ref_name) is not None:
        branch_classes.append(const.BranchClass.DEVELOPMENT_BASE)
    if context.release_branch_matcher.fullmatch(ref_name) is not None:
        branch_classes.append(const.BranchClass.RELEASE)
    match = context.work_branch_matcher.fullmatch(ref_name)
    if match is not None:
        prefix = match.group('prefix').strip('/')
        if prefix == const.BRANCH_PREFIX_DEV:
            branch_classes.append(const.BranchClass.WORK_DEV)
        elif prefix == const.BRANCH_PREFIX_PROD:
            branch_classes.append(const.BranchClass.WORK_PROD)
        else:
            raise ValueError("invalid prefix: " + prefix)
    if len(branch_classes) == 1:
        branch_class = branch_classes[0]
    elif len(branch_classes) == 0:
        branch_class = None
    else:
        raise Exception("internal error")
    return branch_class


def update_branch_info(context: Context, branch_info_out: dict, upstreams: dict,
                       branch_ref: repotools.Ref) -> BranchInfo:
    # TODO optimize

    branch_info = None

    if branch_ref.local_branch_name:
        branch_info = BranchInfo()
        branch_info.local = [branch_ref]

        upstream = upstreams.get(branch_ref.name)
        if upstream is not None:
            branch_info.upstream = repotools.get_ref_by_name(context.repo, upstream)

    elif branch_ref.remote_branch_name:
        branch_info = BranchInfo()
        branch_info.upstream = branch_ref

        branch_info.local = list()

        for ref, upstream in upstreams.items():
            if upstream == branch_ref.name:
                branch_info.local.append(repotools.get_ref_by_name(context.repo, ref))

    if branch_info is not None:
        if branch_info.local is not None:
            branch_info.local_class = list()
            for local in branch_info.local:
                branch_info.local_class.append(get_branch_class(context, local.name))
                branch_info_out[local.name] = branch_info
        if branch_info.upstream is not None:
            branch_info.upstream_class = get_branch_class(context, branch_info.upstream.name)
            branch_info_out[branch_info.upstream.name] = branch_info

    return branch_info


def get_branch_info(command_context: CommandContext, ref: Union[repotools.Ref, str]) -> BranchInfo:
    # TODO optimize

    if isinstance(ref, str):
        ref = repotools.get_ref_by_name(command_context.context.repo, ref)

    if ref is not None:
        branch_info = command_context.branch_info_dict.get(repotools.ref_name(ref))
        if branch_info is None:
            branch_info = update_branch_info(command_context.context,
                                             command_context.branch_info_dict,
                                             command_context.upstreams,
                                             ref
                                             )
    else:
        branch_info = None
    return branch_info


def update_project_properties(context: Context,
                              prev_properties: dict,
                              new_version: str,
                              new_sequential_version: int) -> dict:
    new_version_info = semver.parse_version_info(new_version)

    if new_version_info.build is not None:
        raise ValueError("build info must not be set in version tag")

    properties = prev_properties.copy() if prev_properties is not None else dict()

    if context.config.commit_version_property:
        properties[context.config.version_property] = new_version
    if context.config.commit_sequential_version_property:
        properties[context.config.sequence_number_property] = str(new_sequential_version)

    return properties


def update_project_property_file(context: Context,
                                 prev_properties: dict,
                                 new_version: str,
                                 new_sequential_version: int,
                                 commit_out: CommitInfo):
    result = Result()
    result.value = False

    if context.config.property_file is not None:
        property_reader = PropertyIO.get_instance_by_filename(context.config.property_file)
        if property_reader is None:
            result.fail(os.EX_DATAERR,
                        _("Property file not supported: {path}\n"
                          "Currently supported:\n"
                          "{listing}")
                        .format(path=repr(context.config.property_file),
                                listing='\n'.join(' - ' + type for type in ['*.properties'])),
                        None
                        )

        properties = update_project_properties(context, prev_properties, new_version, new_sequential_version)

        property_reader.write_file(context.config.property_file, properties)
        commit_out.add_file(context.config.property_file)
        result.value = True
    else:
        properties = None

    var_separator = ' : '

    if properties is not None:
        def log_property(properties: dict, key: str):
            if key is not None:
                commit_out.add_message('#properties[' + utils.quote(key, '"') + ']'
                                       + var_separator + cli.if_none(properties.get(key), "null"))

        for property_key in [context.config.version_property,
                             context.config.sequence_number_property]:
            log_property(properties, property_key)

    if context.verbose and result.value != 0:
        print("properties have changed")
        print("commit message:")
        print(commit_out.message)

    return result


def execute_version_change_actions(context: Context, old_version: str, new_version: str):
    variables = dict(os.environ)
    variables['OLD_VERSION'] = old_version or ''
    variables['NEW_VERSION'] = new_version

    for command in context.config.version_change_actions:
        command_string = ' '.join(shlex.quote(token) for token in command)
        if context.verbose >= const.TRACE_VERBOSITY:
            print(command_string)

        command = [expand_vars(token, variables) for token in command]

        proc = subprocess.Popen(args=command,
                                # stdin=subprocess.PIPE,
                                # stdout=subprocess.PIPE,
                                cwd=context.repo.dir,
                                env=None)
        proc.wait()
        if proc.returncode != os.EX_OK:
            context.fail(os.EX_DATAERR,
                         _("version change action failed."),
                         _("{command}\n"
                           "returned with an error.")
                         .format(command=command_string))


def get_branch_version_component_for_version(context: Context,
                                             version_on_branch: Union[semver.VersionInfo, version.Version]):
    return str(version_on_branch.major) + '.' + str(version_on_branch.minor)


def get_branch_name_for_version(context: Context, version_on_branch: Union[semver.VersionInfo, version.Version]):
    return (context.release_branch_matcher.ref_name_infix or '') \
           + get_branch_version_component_for_version(context, version_on_branch)


def get_tag_name_for_version(context: Context, version_info: semver.VersionInfo):
    return (context.version_tag_matcher.ref_name_infix or '') \
           + version.format_version_info(version_info)


def get_discontinuation_tag_name_for_version(context, version: Union[semver.VersionInfo, version.Version]):
    return (context.discontinuation_tag_matcher.ref_name_infix or '') + get_branch_version_component_for_version(
        context, version)


def get_global_sequence_number(context: Context) -> Union[int, None]:
    if context.version_tag_matcher.group_unique_code:
        tags = repotools.git_list_refs(context.repo,
                                       repotools.create_ref_name(
                                           const.LOCAL_TAG_PREFIX,
                                           context.version_tag_matcher.ref_name_infix or '')
                                       )
        seq = None

        for tag in tags:
            match = context.version_tag_matcher.fullmatch(tag.name)
            if match is not None:
                version_code = int(match.group(context.version_tag_matcher.group_unique_code))
                if seq is None:
                    seq = version_code
                else:
                    seq = max(seq, version_code)

        return seq
    else:
        return None


def create_sequence_number_for_version(context, new_version: Union[semver.VersionInfo, version.Version]):
    sequence_number = get_global_sequence_number(context)
    return (sequence_number if sequence_number is not None else 0) + 1


def get_discontinuation_tags(context, version_branch: Union[repotools.Ref, str]):
    # TODO parse major.minor only
    version = context.release_branch_matcher.to_version(version_branch.name)
    if version is None:
        return [], None

    discontinuation_tag_name = get_discontinuation_tag_name_for_version(context, version)
    discontinuation_tag = repotools.create_ref_name(const.LOCAL_TAG_PREFIX, discontinuation_tag_name)

    discontinuation_tags = [discontinuation_tag] \
        if repotools.git_rev_parse(context.repo, '--verify', discontinuation_tag) is not None \
        else []

    return discontinuation_tags, discontinuation_tag_name


def get_branch_by_branch_name_or_version_tag(context: Context, name: str, search_mode: BranchSelection):
    branch_ref = repotools.get_branch_by_name(context.repo, {context.config.remote_name}, name, search_mode)

    if branch_ref is None:
        tag_version = version.parse_version(name)
        if tag_version is not None:
            version_branch_name = get_branch_name_for_version(context, tag_version)
            branch_ref = repotools.get_branch_by_name(context.repo, {context.config.remote_name}, version_branch_name,
                                                      search_mode)

    if branch_ref is None:
        # TODO common definition
        match = re.compile(r'(\d+).(\d+)').fullmatch(name)
        if match is not None:
            branch_version = version.Version()
            branch_version.major = int(match.group(1))
            branch_version.minor = int(match.group(2))
            version_branch_name = get_branch_name_for_version(context, branch_version)
            branch_ref = repotools.get_branch_by_name(context.repo, {context.config.remote_name}, version_branch_name,
                                                      search_mode)

    if branch_ref is None:
        if not name.startswith(context.release_branch_matcher.ref_name_infix):
            branch_ref = repotools.get_branch_by_name(context.repo, {context.config.remote_name},
                                                      context.release_branch_matcher.ref_name_infix + name,
                                                      search_mode)

    return branch_ref


def clone_repository(context: Context, branch: str) -> Result:
    """
    :rtype: Result
    """
    result = Result()

    remote = repotools.git_get_remote(context.repo, context.config.remote_name)
    if remote is None:
        result.fail(os.EX_DATAERR,
                    _("Failed to clone repo."),
                    _("The remote {remote} does not exist.")
                    .format(remote=repr(context.config.remote_name))
                    )

    tempdir_path = tempfile.mkdtemp(prefix=os.path.basename(context.repo.dir) + ".gitflow-clone.")
    try:
        if os.path.exists(tempdir_path):
            os.chmod(path=tempdir_path, mode=0o700)
            if os.path.isdir(tempdir_path):
                if os.listdir(tempdir_path):
                    result.fail(os.EX_DATAERR,
                                _("Failed to clone repo."),
                                _("Directory is not empty: {path}").format(path=tempdir_path)
                                )
            else:
                result.fail(os.EX_DATAERR,
                            _("Failed to clone repo."),
                            _("File is not a directory: {path}").format(path=tempdir_path)
                            )
        else:
            result.fail(os.EX_DATAERR,
                        _("Failed to clone repo."),
                        _("File does not exist: {path}").format(path=tempdir_path)
                        )

        if context.config.push_to_local:
            returncode, out, err = repotools.git_raw(
                git=context.repo.git,
                args=['clone',
                      '--branch', branch,
                      '--shared',
                      context.repo.dir,
                      tempdir_path
                      ],
                verbose=context.verbose)
        else:
            returncode, out, err = repotools.git_raw(
                git=context.repo.git,
                args=['clone',
                      '--branch', branch,
                      '--reference', context.repo.dir,
                      remote.url,
                      tempdir_path],
                verbose=context.verbose)

        if returncode != os.EX_OK:
            result.error(os.EX_DATAERR,
                         _("Failed to clone the repository."),
                         _("An unexpected error occurred.")
                         )
    except:
        result.error(os.EX_DATAERR,
                     _("Failed to clone the repository."),
                     _("An unexpected error occurred.")
                     )
    finally:
        context.add_subresult(result)

    if not result.has_errors():
        repo = RepoContext()
        repo.git = context.repo.git
        repo.dir = tempdir_path
        repo.verbose = context.repo.verbose
        result.value = repo
    else:
        shutil.rmtree(path=tempdir_path)

    return result


def create_temp_context(context: Context, result: Result, directory: str) -> Context:
    clone_context = Context.create({
        '--root': directory,

        '--config': context.args['--config'],  # no override here

        '--batch': context.batch,
        '--dry-run': context.dry_run,

        '--verbose': context.verbose,
        '--pretty': context.pretty,
    }, result)
    if clone_context.temp_dirs is None:
        clone_context.temp_dirs = list()
    clone_context.temp_dirs.append(directory)
    if context.clones is None:
        context.clones = list()
    context.clones.append(clone_context)
    return clone_context


def prompt_for_confirmation(context: Context, fail_title: str, message: str, prompt: str):
    result = Result()

    if context.batch:
        result.value = context.assume_yes
        if not result.value:
            sys.stdout.write(prompt + ' -' + os.linesep)
            result.fail(const.EX_ABORTED, fail_title, _("Operation aborted in batch mode."))
    else:
        if message is not None:
            cli.warn(message)
        sys.stderr.flush()
        sys.stdout.flush()

        if context.assume_yes:
            sys.stdout.write(prompt + ' y' + os.linesep)
            result.value = True
        else:
            result.value = cli.query_yes_no(sys.stdout, prompt, "no")

        if result.value is not True:
            result.error(const.EX_ABORTED_BY_USER, fail_title, _("Operation aborted."), False)

    return result


def prompt(context: Context, message: str, prompt: str):
    result = Result()

    if context.batch:
        result.value = context.assume_yes
        if not result.value:
            sys.stdout.write(prompt + ' -' + os.linesep)
            result.fail(const.EX_ABORTED, _("Operation failed."), _("Operation aborted in batch mode."))
    else:
        if message is not None:
            cli.warn(message)
        sys.stderr.flush()
        sys.stdout.flush()

        if context.assume_yes:
            sys.stdout.write(prompt + ' y' + os.linesep)
            result.value = True
        else:
            result.value = cli.query_yes_no(sys.stdout, prompt, "no")

    return result


def get_command_context(context, object_arg: str) -> CommandContext:
    command_context = CommandContext()

    command_context.object_arg = object_arg
    command_context.context = context

    if context.repo is not None:
        command_context.upstreams = repotools.git_get_upstreams(context.repo, const.LOCAL_BRANCH_PREFIX)
        command_context.downstreams = {v: k for k, v in command_context.upstreams.items()}

        # resolve the full rev name and its hash for consistency
        selected_ref = None
        current_branch = repotools.git_get_current_branch(context.repo)
        affected_main_branches = None
        if object_arg is None:
            if current_branch is None:
                command_context.fail(os.EX_USAGE,
                                     _("Operation failed."),
                                     _("No object specified and not on a branch (may be an empty repository).")
                                     )
            commit = current_branch.target.obj_name
            selected_ref = current_branch
        else:
            branch_ref = get_branch_by_branch_name_or_version_tag(context, object_arg,
                                                                  BranchSelection.BRANCH_PREFER_LOCAL)
            if branch_ref is not None:
                selected_ref = branch_ref
                commit = branch_ref.target.obj_name
            else:
                branch_ref = repotools.git_rev_parse(context.repo, '--revs-only', '--symbolic-full-name', object_arg)
                commit = repotools.git_rev_parse(context.repo, '--revs-only', object_arg)
                if branch_ref is not None:
                    selected_ref = repotools.Ref()
                    selected_ref.name = branch_ref
                    selected_ref.obj_type = 'commit'
                    selected_ref.obj_name = commit
        if commit is None:
            command_context.fail(os.EX_USAGE,
                                 _("Failed to resolve object {object}.")
                                 .format(object=repr(object_arg)),
                                 _("No corresponding commit found.")
                                 )

        # determine affected branches
        affected_main_branches = list(
            filter(lambda ref:
                   (ref.name not in command_context.downstreams
                    and commit in [reachable_commit.obj_name for reachable_commit in
                                   repotools.git_list_commits(context=context.repo, start=None, end=ref,
                                                              options=['--first-parent'])]),
                   repotools.git_list_refs(context.repo,
                                           '--contains', commit,
                                           repotools.create_ref_name(const.REMOTES_PREFIX,
                                                                     context.config.remote_name,
                                                                     'release'),
                                           'refs/heads/release',
                                           'refs/heads/' + context.config.release_branch_base,
                                           # const.REMOTES_PREFIX + context.config.remote_name + '/' + context.config.release_branch_base,
                                           # const.LOCAL_BRANCH_PREFIX + context.config.release_branch_base,
                                           )))
        if len(affected_main_branches) == 1:
            if selected_ref is None or selected_ref.name.startswith(const.LOCAL_TAG_PREFIX):
                selected_ref = affected_main_branches[0]
        if selected_ref is None:
            if len(affected_main_branches) == 0:
                command_context.fail(os.EX_USAGE,
                                     _("Failed to resolve target branch"),
                                     _("Failed to resolve branch containing object: {object}")
                                     .format(object=repr(object_arg))
                                     )
            else:
                command_context.fail(os.EX_USAGE,
                                     _("Failed to resolve unique branch for object: {object}")
                                     .format(object=repr(object_arg)),
                                     _("Multiple different branches contain this commit:\n"
                                       "{listing}")
                                     .format(
                                         listing='\n'.join(' - ' + repr(ref.name) for ref in affected_main_branches))
                                     )
        if selected_ref is None or commit is None:
            command_context.fail(os.EX_USAGE,
                                 _("Failed to resolve ref."),
                                 _("{object} could not be resolved.")
                                 .format(object=repr(object_arg)))
        if context.verbose >= const.INFO_VERBOSITY:
            cli.print(_("Target branch: {name} ({commit})")
                      .format(name=repr(selected_ref.name), commit=selected_ref.target.obj_name))
            cli.print(_("Target commit: {commit}")
                      .format(commit=commit))

        branch_info = get_branch_info(command_context, selected_ref)

        command_context.selected_ref = selected_ref
        command_context.selected_commit = commit
        command_context.selected_branch = branch_info
        command_context.selected_explicitly = object_arg is not None

        command_context.affected_main_branches = affected_main_branches
        command_context.current_branch = current_branch

    return command_context


def create_commit(context: Context, result, commit_info: CommitInfo):
    add_command = ['update-index', '--add', '--']
    add_command.extend(commit_info.files)
    git_or_fail(context.repo, result, add_command)

    write_tree_command = ['write-tree']
    new_tree = git_for_line_or_fail(context.repo, result, write_tree_command)

    commit_command = ['commit-tree']
    for parent in commit_info.parents:
        commit_command.append('-p')
        commit_command.append(parent)

    commit_command.extend(['-m', commit_info.message, new_tree])
    new_commit = git_for_line_or_fail(context.repo, result, commit_command)

    # reset_command = ['reset', 'HEAD', new_commit]
    # git_or_fail(clone_context, result, reset_command)

    object_to_tag = new_commit
    return object_to_tag


def check_in_repo(command_context: CommandContext):
    if command_context.context.repo is None:
        command_context.fail(os.EX_USAGE,
                             _("No repo at this location."),
                             None)


def check_requirements(command_context: CommandContext,
                       ref: repotools.Ref,
                       branch_classes: Union[list, None],
                       modifiable: bool,
                       with_upstream: bool,
                       in_sync_with_upstream: bool,
                       fail_message: str,
                       allow_unversioned_changes: bool = None,
                       throw=True):
    branch_class = get_branch_class(command_context.context, ref)

    if branch_classes is not None and branch_class not in branch_classes:
        command_context.error(os.EX_USAGE,
                              fail_message,
                              _("The branch {branch} is of type {type} must be one of these types:{allowed_types}")
                              .format(branch=repr(ref.name),
                                      type=repr(branch_class.name if branch_class is not None else None),
                                      allowed_types='\n - ' + '\n - '.join(
                                          branch_class.name for branch_class in branch_classes)),
                              throw)

    if ref.local_branch_name is not None:
        # check, whether the  selected branch/commit is on remote

        if with_upstream and command_context.selected_branch.upstream is None:
            command_context.error(os.EX_USAGE,
                                  fail_message,
                                  _("{branch} does not have an upstream branch.")
                                  .format(branch=repr(ref.name)),
                                  throw)

        # if branch_info.upstream.short_name != selected_ref.short_name:
        #     result.error(os.EX_USAGE,
        #                 _("Version creation failed."),
        #                 _("{branch} has an upstream branch with mismatching short name: {remote_branch}.")
        #                 .format(branch=repr(selected_ref.name),
        #                         remote_branch=repr(branch_info.upstream.name))
        #                 )

        if in_sync_with_upstream and command_context.selected_branch.upstream is not None:
            push_merge_base = repotools.git_merge_base(command_context.context.repo, command_context.selected_commit,
                                                       command_context.selected_branch.upstream)
            if push_merge_base is None:
                command_context.error(os.EX_USAGE,
                                      fail_message,
                                      _(
                                          "{branch} does not have a common base with its upstream branch: {remote_branch}")
                                      .format(branch=repr(ref.name),
                                              remote_branch=repr(command_context.selected_branch.upstream.name)),
                                      throw)
            elif push_merge_base != command_context.selected_commit:
                command_context.error(os.EX_USAGE,
                                      fail_message,
                                      _("{branch} is not in sync with its upstream branch.\n"
                                        "Push your changes and try again.")
                                      .format(branch=repr(ref.name),
                                              remote_branch=repr(command_context.selected_branch.upstream.name)),
                                      throw)

    discontinuation_tags, discontinuation_tag_name = get_discontinuation_tags(command_context.context,
                                                                              ref)
    if modifiable and len(discontinuation_tags):
        command_context.error(os.EX_USAGE,
                              fail_message,
                              _("{branch} is discontinued.")
                              .format(branch=repr(ref.name)),
                              throw)

    if not allow_unversioned_changes:
        current_branch = git_get_current_branch(command_context.context.repo)
        if ref == current_branch:
            returncode = git(command_context.context.repo,
                             ['diff-index', '--name-status', '--exit-code', current_branch])

            if returncode != os.EX_OK:
                command_context.error(os.EX_USAGE,
                                      fail_message,
                                      _("{branch} has uncommitted changes.")
                                      .format(branch=repr(ref.name)),
                                      throw)


def read_config_in_commit(repo: RepoContext, commit: str, config_file_path: str = const.DEFAULT_CONFIG_FILE) -> dict:
    if config_file_path is None:
        config_str = None
        for config_filename in const.DEFAULT_CONFIGURATION_FILE_NAMES:
            config_str = repotools.get_file_contents(
                repo,
                commit,
                config_filename
            )
            if config_filename is not None:
                break
    else:
        config_str = repotools.get_file_contents(
            repo,
            commit,
            config_file_path
        )

    if config_str is not None:
        config = PropertyIO.get_instance_by_filename(config_file_path).from_bytes(config_str,
                                                                                  const.DEFAULT_PROPERTY_ENCODING)
    else:
        config = None
    return config


def read_properties_in_commit(context: Context, repo: RepoContext, config: dict, commit: str):
    if config is not None:
        property_file = config.get(const.CONFIG_PROJECT_PROPERTY_FILE)

        if property_file is None:
            return None

        properties_bytes = repotools.get_file_contents(
            repo,
            commit,
            property_file
        )

        if properties_bytes is None:
            return

        property_reader = PropertyIO.get_instance_by_filename(property_file)
        properties = property_reader.from_bytes(properties_bytes, const.DEFAULT_PROPERTY_ENCODING)

        if properties is None:
            context.fail(os.EX_DATAERR,
                         _("Failed to parse properties."),
                         None)

        return properties


class WorkBranch(object):
    prefix: str
    type: str
    name: str

    def branch_name(self):
        return repotools.create_ref_name(self.prefix, self.type, self.name)

    def local_ref_name(self):
        return repotools.create_ref_name(const.LOCAL_BRANCH_PREFIX, self.prefix, self.type, self.name)

    def remote_ref_name(self, remote: str):
        return repotools.create_ref_name(const.REMOTES_PREFIX, remote, self.prefix, self.type, self.name)

    def __repr__(self):
        return self.branch_name()

    def __str__(self):
        return self.branch_name()


def update_hash_with_file(hash_state, file: str):
    with open(file, 'rb') as file:
        while True:
            buffer = file.read(65536)
            if len(buffer):
                hash_state.update(buffer)
            else:
                break


def hash_file(hash_state, file):
    update_hash_with_file(hash_state, file)
    return hash_state.digest()


def download_file(source_uri: str, dest_file: str, hash_hex: str):
    from urllib import request
    import hashlib

    result = Result()

    hash = bytes.fromhex(hash_hex)

    download = False

    if not os.path.exists(dest_file):
        cli.print("file does not exist: " + dest_file)
        download = True
    elif hash_file(hashlib.sha256(), dest_file) != hash:
        cli.print("file hash does not match: " + dest_file)
        download = True
    else:
        cli.print("keeping file: " + dest_file + ", sha256 matched: " + hash_hex)

    if download:
        cli.print("downloading: " + source_uri + " to " + dest_file)
        request.urlretrieve(url=str(source_uri), filename=dest_file + "~")
        filesystem.replace_file(dest_file + "~", dest_file)

        if hash is not None:
            actual_hash = hash_file(hashlib.sha256(), dest_file)
            if actual_hash != hash:
                result.error(os.EX_IOERR,
                             _("File verification failed."),
                             _("The file {file} is expected to hash to {expected_hash},\n"
                               "The actual hash is: {actual_hash}")
                             .format(
                                 file=repr(dest_file),
                                 expected_hash=repr(hash_hex),
                                 actual_hash=repr(actual_hash.hex()),
                             )
                             )

    if not result.has_errors():
        result.value = dest_file

    return result


def __var_subst(match, vars: dict):
    subst = ''
    if match.group(1) is not None:
        subst += match.group(1)[:len(match.group(1)) >> 1]
    if match.group(2) is not None:
        if match.group(3) is None:
            subst += vars[match.group(5) or match.group(6)]
        else:
            subst += match.group(4)
    return subst


def expand_vars(s: str, vars: dict):
    return re.sub(r'((?:\\\\)+)|((\\)?(\$(?:{([^}]*)}|(\w+))))', lambda match: __var_subst(match, vars), s)


def execute_build_steps(command_context: CommandContext, types: list = None):
    if types is not None:
        stages = filter(lambda stage: stage.type in types, command_context.context.config.build_stages)
    else:
        stages = command_context.context.config.build_stages

    for stage in stages:
        for step in stage.steps:
            step_errors = 0

            for command in step.commands:
                command_string = ' '.join(shlex.quote(token) for token in command)
                if command_context.context.verbose >= const.TRACE_VERBOSITY:
                    print(command_string)

                command = [expand_vars(token, os.environ) for token in command]

                if not command_context.context.dry_run:
                    try:
                        proc = subprocess.Popen(args=command,
                                                stdin=subprocess.PIPE,
                                                cwd=command_context.context.root)
                        proc.wait()
                        if proc.returncode != os.EX_OK:
                            command_context.fail(os.EX_DATAERR,
                                                 _("{stage}:{step} failed.")
                                                 .format(stage=stage.name, step=step.name),
                                                 _("{command}\n"
                                                   "returned with an error.")
                                                 .format(command=command_string))
                    except FileNotFoundError as e:
                        step_errors += 1
                        command_context.fail(os.EX_DATAERR,
                                             _("{stage}:{step} failed.")
                                             .format(stage=stage.name, step=step.name),
                                             _("{command}\n"
                                               "could not be executed.\n"
                                               "File not found: {file}")
                                             .format(command=command_string, file=e.filename))

            if not step_errors:
                cli.print(stage.name + ":" + step.name + ": OK")
            else:
                cli.print(stage.name + ":" + step.name + ": FAILED")
