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
import shutil
import sys
from typing import Union

import semver

from gitflow import cli, utils, _, filesystem
from gitflow import const
from gitflow import repotools
from gitflow import version
from gitflow.common import Result
from gitflow.context import Context
from gitflow.repotools import BranchSelection


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
    local: repotools.Ref = None
    local_class: const.BranchClass = None
    upstream: repotools.Ref = None
    upstream_class: const.BranchClass = None


def select_ref(result_out: Result, branch_info: BranchInfo, selection: BranchSelection) \
        -> [repotools.Ref, const.BranchClass]:
    if branch_info.local is not None and branch_info.upstream is not None:
        if branch_info.local_class != branch_info.upstream_class:
            result_out.error(os.EX_DATAERR,
                             _("Local and upstream branch have a mismatching branch class."),
                             None)
        if not branch_info.upstream.short_name.endswith('/' + branch_info.local.short_name):
            result_out.error(os.EX_DATAERR,
                             _("Local and upstream branch have a mismatching short name."),
                             None)

    candidate = None
    candidate_class = None
    if selection == BranchSelection.BRANCH_PREFER_LOCAL:
        candidate = branch_info.local or branch_info.upstream
        candidate_class = branch_info.local_class or branch_info.upstream_class
    elif selection == BranchSelection.BRANCH_LOCAL_ONLY:
        candidate = branch_info.local
        candidate_class = branch_info.local_class
    elif selection == BranchSelection.BRANCH_PREFER_REMOTE:
        candidate = branch_info.upstream or branch_info.local
        candidate_class = branch_info.upstream_class or branch_info.local_class
    elif selection == BranchSelection.BRANCH_REMOTE_ONLY:
        candidate = branch_info.upstream
        candidate_class = branch_info.upstream_class
    return candidate, candidate_class


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


def git(context: Context, command: list) -> int:
    proc = repotools.git(context.repo, *command)
    proc.wait()
    return proc.returncode


def git_or_fail(context: Context, result: Result, command: list,
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


def git_for_line_or_fail(context: Context, result: Result, command: list,
                         error_message: str = None, error_reason: str = None):
    line = repotools.git_for_line(context.repo, *command)
    if line is None:
        if error_message is not None:
            result.fail(os.EX_DATAERR, error_message, error_reason)
        else:
            first_command_token = next(filter(lambda token: not token.startswith('-'), command))
            result.fail(os.EX_DATAERR, _("git {sub_command} failed.")
                        .format(sub_command=repr(first_command_token)),
                        error_reason
                        )
    return line


def fetch_all_and_ff(context: Context, result_out: Result, remote: [repotools.Remote, str]):
    # attempt a complete fetch and a fast forward on the current branch
    remote_name = remote.name if isinstance(remote, repotools.Remote) else remote
    proc = repotools.git(context.repo, 'fetch', '--tags', remote_name)
    proc.wait()
    if proc.returncode != os.EX_OK:
        result_out.warn(
            _("Failed to fetch from {remote}")
                .format(repr(remote_name)),
            None)
    proc = repotools.git(context.repo, 'merge', '--ff-only')
    proc.wait()
    if proc.returncode != os.EX_OK:
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
        branch_info.local = branch_ref

        upstream = upstreams.get(branch_ref.name)
        if upstream is not None:
            branch_info.upstream = repotools.get_ref_by_name(context.repo, upstream)

    elif branch_ref.remote_branch_name:
        branch_info = BranchInfo()
        branch_info.upstream = branch_ref

        for ref, upstream in upstreams.items():
            if upstream == branch_ref.name:
                branch_info.local = repotools.get_ref_by_name(context.repo, ref)
                break

    if branch_info is not None:
        if branch_info.local is not None:
            branch_info.local_class = get_branch_class(context, branch_info.local.name)
            branch_info_out[branch_info.local.name] = branch_info
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


def update_project_property_file(context: Context,
                                 new_version: str, new_sequential_version: int,
                                 commit_out: CommitInfo):
    result = Result()

    commit_out.add_message("#version     : " + cli.if_none(new_version))
    commit_out.add_message("#seq_version : " + cli.if_none(new_sequential_version))

    version_property_name = context.config.version_property_name
    sequential_version_property_name = context.config.sequential_version_property_name

    property_store = None
    if context.config.property_file is not None and version_property_name is not None:
        if context.config.property_file.endswith(".properties"):
            property_store = filesystem.JavaPropertyFile(context.config.property_file)
        else:
            result.fail(os.EX_DATAERR,
                        _("Property file not supported: {path}\n"
                          "Currently supported:\n"
                          "{listing}")
                        .format(path=repr(context.config.property_file),
                                listing='\n'.join(' - ' + type for type in ['*.properties'])),
                        None
                        )

        properties = property_store.load()
        if properties is None:
            result.fail(os.EX_DATAERR,
                        _("Failed to load properties from file: {path}")
                        .format(path=repr(context.config.property_file)),
                        None
                        )
        result.value = 0
        if context.config.commit_version_property:
            version = properties.get(version_property_name)

            if version_property_name not in properties:
                result.warn(_("Missing version property."),
                            _("Missing property {property} in file {file}.")
                            .format(property=repr(version_property_name),
                                    file=repr(context.config.property_file))
                            )
            properties[version_property_name] = new_version
            commit_out.add_message('#properties[' + utils.quote(version_property_name, '"') + ']:' + new_version)
            if context.verbose:
                print("version     : " + cli.if_none(version))
                print("new_version : " + cli.if_none(properties[version_property_name]))

            result.value += 1

        if context.config.commit_sequential_version_property and sequential_version_property_name is not None:
            sequential_version = properties.get(sequential_version_property_name)

            if sequential_version_property_name not in properties:
                result.warn(_("Missing version property."),
                            _("Missing property {property} in file {file}.")
                            .format(property=repr(sequential_version_property_name),
                                    file=repr(context.config.property_file))
                            )
            properties[sequential_version_property_name] = str(new_sequential_version)
            commit_out.add_message('#properties[' + utils.quote(sequential_version_property_name, '"') + ']:' + str(
                new_sequential_version))

            if context.verbose:
                print("sequential_version     : " + cli.if_none(sequential_version))
                print("new_sequential_version : " + cli.if_none(properties[sequential_version_property_name]))

            result.value += 1

        if result.value:
            property_store.store(properties)
            commit_out.add_file(context.config.property_file)

    return result


def get_branch_version_component_for_version(context: Context,
                                             version_on_branch: Union[semver.VersionInfo, version.Version]):
    return str(version_on_branch.major) + '.' + str(version_on_branch.minor)


def get_branch_name_for_version(context: Context, version_on_branch: Union[semver.VersionInfo, version.Version]):
    return context.release_branch_matcher.ref_name_infixes[0] \
           + get_branch_version_component_for_version(context, version_on_branch)


def get_tag_name_for_version(context: Context, version_info: semver.VersionInfo):
    return context.version_tag_matcher.ref_name_infixes[0] \
           + version.format_version_info(version_info)


def get_discontinuation_tag_name_for_version(context, version: Union[semver.VersionInfo, version.Version]):
    return context.discontinuation_tag_matcher.ref_name_infixes[
               0] + get_branch_version_component_for_version(
        context, version)


def get_global_sequence_number(context):
    sequential_tags = repotools.git_list_refs(context.repo,
                                              repotools.create_ref_name(
                                                  const.LOCAL_TAG_PREFIX,
                                                  context.sequential_version_tag_matcher.ref_name_infixes[0])
                                              )
    counter = 0
    for tag in sequential_tags:
        match = context.sequential_version_tag_matcher.fullmatch(tag.name)
        if match is not None:
            counter = max(counter,
                          int(match.group(context.sequential_version_tag_matcher.group_unique_code)))
        else:
            raise Exception("invalid tag: " + tag.name)
    return counter


def create_sequence_number_for_version(context, new_version: Union[semver.VersionInfo, version.Version]):
    return get_global_sequence_number(context) + 1


def create_sequential_version_tag_name(context, counter: int):
    return context.sequential_version_tag_matcher.ref_name_infixes[0] + str(counter)


def get_discontinuation_tags(context, version_branch: Union[repotools.Ref, str]):
    # TODO parse major.minor only
    version = context.release_branch_matcher.to_version(version_branch.name)
    if version is None:
        return [], None

    discontinuation_tag_name = get_discontinuation_tag_name_for_version(context, version)
    discontinuation_tag = repotools.create_ref_name(const.LOCAL_TAG_PREFIX, discontinuation_tag_name)

    discontinuation_tags = [discontinuation_tag] \
        if repotools.git_rev_parse(context.repo, discontinuation_tag) is not None \
        else []

    return discontinuation_tags, discontinuation_tag_name


def get_branch_by_branch_name_or_version_tag(context: Context, name: str, search_mode: BranchSelection):
    branch_ref = repotools.get_branch_by_name(context.repo, name, search_mode)

    if branch_ref is None:
        tag_version = version.parse_version(name)
        if tag_version is not None:
            version_branch_name = get_branch_name_for_version(context, tag_version)
            branch_ref = repotools.get_branch_by_name(context.repo, version_branch_name, search_mode)

    if branch_ref is None:
        # TODO common definition
        match = re.compile(r'(\d+).(\d+)').fullmatch(name)
        if match is not None:
            branch_version = version.Version()
            branch_version.major = int(match.group(1))
            branch_version.minor = int(match.group(2))
            version_branch_name = get_branch_name_for_version(context, branch_version)
            branch_ref = repotools.get_branch_by_name(context.repo, version_branch_name, search_mode)

    if branch_ref is None:
        if not name.startswith(context.release_branch_matcher.ref_name_infixes[0]):
            branch_ref = repotools.get_branch_by_name(context.repo,
                                                      context.release_branch_matcher.ref_name_infixes[
                                                          0] + name,
                                                      search_mode)

    return branch_ref


def create_shared_clone_repository(context):
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

    tempdir_path = os.path.join(os.path.dirname(context.repo.dir),
                                '.' + os.path.basename(context.repo.dir) + ".gitflow-clone")
    clone_dir_mode = 0o700
    if os.path.exists(tempdir_path):
        if not os.path.isdir(tempdir_path):
            result.fail(os.EX_DATAERR,
                        _("Failed to clone repo."),
                        _("The temporary target directory exists, but is not a directory.")
                        )
        else:
            shutil.rmtree(tempdir_path)
    os.mkdir(path=tempdir_path, mode=clone_dir_mode)

    if context.config.push_to_local:
        proc = repotools.git(context.repo, 'clone', '--shared',
                             '--branch', context.config.release_branch_base,
                             '.',
                             tempdir_path)
    else:
        proc = repotools.git(context.repo, 'clone', '--reference', '.',
                             '--branch', context.config.release_branch_base,
                             remote.url,
                             tempdir_path)
    proc.wait()
    if proc.returncode != os.EX_OK:
        result.fail(os.EX_DATAERR,
                    _("Failed to clone repo."),
                    _("An unexpected error occurred.")
                    )

    clone_context = Context.create({
        '--root': tempdir_path,

        '--config': context.args['--config'],  # no override here

        '--batch': context.batch,
        '--dry-run': context.dry_run,

        '--verbose': context.verbose,
        '--pretty': context.pretty,
    }, result)

    if clone_context.temp_dirs is None:
        clone_context.temp_dirs = list()
    clone_context.temp_dirs.append(tempdir_path)

    if context.clones is None:
        context.clones = list()
    context.clones.append(clone_context)

    if not result.has_errors():
        result.value = clone_context
    else:
        context.cleanup()
    return result


def prompt_for_confirmation(context: Context, fail_title: str, message: str, prompt: str):
    result = Result()

    if context.batch:
        result.value = context.assume_yes
        if not result.value:
            result.fail(os.EX_TEMPFAIL, fail_title, message)
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
        branch_ref = get_branch_by_branch_name_or_version_tag(context, object_arg, BranchSelection.BRANCH_PREFER_LOCAL)
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
               (ref.name not in command_context.downstreams),
               repotools.git_list_refs(context.repo,
                                       '--contains', commit,
                                       repotools.create_ref_name(const.REMOTES_PREFIX,
                                                                 context.config.remote_name,
                                                                 'release'),
                                       'refs/heads/release',
                                       'refs/heads/master',
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
                                 _("Failed to resolve unique release branch for object: {object}")
                                 .format(object=repr(object_arg)),
                                 _("Multiple different branches contain this commit:\n"
                                   "{listing}")
                                 .format(listing='\n'.join(' - ' + repr(ref.name) for ref in affected_main_branches))
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

    command_context.value = command_context

    return command_context


def create_commit(clone_context, result, commit_info: CommitInfo):
    add_command = ['update-index', '--add', '--']
    add_command.extend(commit_info.files)
    git_or_fail(clone_context, result, add_command)

    write_tree_command = ['write-tree']
    new_tree = git_for_line_or_fail(clone_context, result, write_tree_command)

    commit_command = ['commit-tree']
    for parent in commit_info.parents:
        commit_command.append('-p')
        commit_command.append(parent)

    commit_command.extend(['-m', commit_info.message, new_tree])
    new_commit = git_for_line_or_fail(clone_context, result, commit_command)

    # reset_command = ['reset', 'HEAD', new_commit]
    # git_or_fail(clone_context, result, reset_command)

    object_to_tag = new_commit
    return object_to_tag


def check_requirements(command_context: CommandContext,
                       ref: repotools.Ref,
                       modifiable: bool,
                       with_upstream: bool,
                       in_sync_with_upstream: bool,
                       fail_message: str,
                       throw=True):
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
