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
import platform
import re
import shutil
import subprocess
import sys
from typing import Union, Callable

import colors
import semver

from gitflow import cli, utils, _, filesystem
from gitflow import const
from gitflow import repotools
from gitflow import version
from gitflow.common import Result
from gitflow.context import Context
from gitflow.repotools import BranchSelection, RepoContext
from gitflow.version import VersionConfig


class VersionUpdateCommit(object):
    message_parts = None

    def __init__(self):
        self.message_parts = list()

    def add_message(self, message: str):
        self.message_parts.append(message)

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


def get_branch_class(context: Context, ref: Union[repotools.Ref, str]):
    ref_name = repotools.ref_name(ref)

    # TODO optimize
    branch_class = None
    branch_classes = list()
    if context.parsed_config.release_base_branch_matcher.fullmatch(ref_name) is not None:
        branch_classes.append(const.BranchClass.DEVELOPMENT_BASE)
    if context.parsed_config.release_branch_matcher.fullmatch(ref_name) is not None:
        branch_classes.append(const.BranchClass.RELEASE)
    match = context.parsed_config.work_branch_matcher.fullmatch(ref_name)
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
                                 commit_out: VersionUpdateCommit):
    result = Result()

    commit_out.add_message("#version     : " + cli.if_none(new_version))
    commit_out.add_message("#seq_version : " + cli.if_none(new_sequential_version))

    version_property_name = context.config.get(const.CONFIG_VERSION_PROPERTY_NAME)
    sequential_version_property_name = context.config.get(const.CONFIG_SEQUENTIAL_VERSION_PROPERTY_NAME)

    properties = context.load_project_properties()
    if properties is not None:
        result.value = 0
        if context.parsed_config.commit_version_property:
            version = properties.get(version_property_name)

            if version_property_name not in properties:
                result.warn(_("Missing version property."),
                            _("Missing property {property} in file {file}.")
                            .format(property=repr(version_property_name),
                                    file=repr(context.config[const.CONFIG_VERSION_PROPERTY_FILE]))
                            )
            properties[version_property_name] = new_version
            commit_out.add_message('#properties[' + utils.quote(version_property_name, '"') + ']:' + new_version)
            if context.verbose:
                print("version     : " + cli.if_none(version))
                print("new_version : " + cli.if_none(properties[version_property_name]))

            result.value += 1

        if context.parsed_config.commit_sequential_version_property:
            sequential_version = properties.get(sequential_version_property_name)

            if sequential_version_property_name not in properties:
                result.warn(_("Missing version property."),
                            _("Missing property {property} in file {file}.")
                            .format(property=repr(sequential_version_property_name),
                                    file=repr(context.config[const.CONFIG_VERSION_PROPERTY_FILE]))
                            )
            properties[sequential_version_property_name] = str(new_sequential_version)
            commit_out.add_message('#properties[' + utils.quote(sequential_version_property_name, '"') + ']:' + str(
                new_sequential_version))

            if context.verbose:
                print("sequential_version     : " + cli.if_none(sequential_version))
                print("new_sequential_version : " + cli.if_none(properties[sequential_version_property_name]))

            result.value += 1

        if result.value:
            context.store_project_properties(properties)

    return result


def get_branch_version_component_for_version(context: Context,
                                             version_on_branch: Union[semver.VersionInfo, version.Version]):
    return str(version_on_branch.major) + '.' + str(version_on_branch.minor)


def get_branch_name_for_version(context: Context, version_on_branch: Union[semver.VersionInfo, version.Version]):
    return context.parsed_config.release_branch_matcher.ref_name_infixes[0] \
           + get_branch_version_component_for_version(context, version_on_branch)


def get_tag_name_for_version(context: Context, version_info: semver.VersionInfo):
    return context.parsed_config.version_tag_matcher.ref_name_infixes[0] \
           + version.format_version_info(version_info)


def get_discontinuation_tag_name_for_version(context, version: Union[semver.VersionInfo, version.Version]):
    return context.parsed_config.discontinuation_tag_matcher.ref_name_infixes[
               0] + get_branch_version_component_for_version(
        context, version)


def get_global_sequence_number(context):
    sequential_tags = repotools.git_list_refs(context.repo,
                                              'refs/tags/' +
                                              context.parsed_config.sequential_version_tag_matcher.ref_name_infixes[0])
    counter = 0
    for tag in sequential_tags:
        match = context.parsed_config.sequential_version_tag_matcher.fullmatch(tag.name)
        if match is not None:
            counter = max(counter,
                          int(match.group(context.parsed_config.sequential_version_tag_matcher.group_unique_code)))
        else:
            raise Exception("invalid tag: " + tag.name)
    return counter


def create_sequence_number_for_version(context, new_version: Union[semver.VersionInfo, version.Version]):
    return get_global_sequence_number(context) + 1


def create_sequential_version_tag_name(context, counter: int):
    return context.parsed_config.sequential_version_tag_matcher.ref_name_infixes[0] + str(counter)


def get_discontinuation_tags(context, version_branch):
    # TODO parse major.minor only
    version = context.parsed_config.release_branch_matcher.to_version(version_branch.name)
    if version is None:
        return [], None
    discontinuation_tag_name = get_discontinuation_tag_name_for_version(context, version)
    discontinuation_tags = repotools.git_list_refs(context.repo, '--contains', version_branch,
                                                   'refs/tags/' + discontinuation_tag_name)
    discontinuation_tags = list(discontinuation_tags)
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
        if not name.startswith(context.parsed_config.release_branch_matcher.ref_name_infixes[0]):
            branch_ref = repotools.get_branch_by_name(context.repo,
                                                      context.parsed_config.release_branch_matcher.ref_name_infixes[
                                                          0] + name,
                                                      search_mode)

    return branch_ref


def create_shared_clone_repository(context):
    """
    :rtype: Result
    """
    result = Result()

    remote = repotools.git_get_remote(context.repo, context.parsed_config.remote_name)
    if remote is None:
        result.fail(os.EX_DATAERR,
                    _("Failed to clone repo."),
                    _("The remote {remote} does not exist.")
                    .format(remote=repr(context.parsed_config.remote_name))
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

    if context.parsed_config.push_to_local:
        proc = repotools.git(context.repo, 'clone', '--shared',
                             '--branch', context.parsed_config.release_branch_base,
                             '.',
                             tempdir_path)
    else:
        proc = repotools.git(context.repo, 'clone', '--reference', '.',
                             '--branch', context.parsed_config.release_branch_base,
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


def get_command_context(context, object_arg: str) -> Result:
    result = Result()

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
            result.fail(os.EX_USAGE,
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
        result.fail(os.EX_USAGE,
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
                                       const.REMOTES_PREFIX + context.parsed_config.remote_name + '/release',
                                       'refs/heads/release',
                                       'refs/heads/master',
                                       # const.REMOTES_PREFIX + context.parsed_config.remote_name + '/' + context.parsed_config.release_branch_base,
                                       # 'refs/heads/' + context.parsed_config.release_branch_base,
                                       )))
    if len(affected_main_branches) == 1:
        if selected_ref is None or selected_ref.name.startswith('refs/tags/'):
            selected_ref = affected_main_branches[0]
    if selected_ref is None:
        if len(affected_main_branches) == 0:
            result.fail(os.EX_USAGE,
                        _("Failed to resolve target branch"),
                        _("Failed to resolve branch containing object: {object}")
                        .format(object=repr(object_arg))
                        )
        else:
            result.fail(os.EX_USAGE,
                        _("Failed to resolve unique release branch for object: {object}")
                        .format(object=repr(object_arg)),
                        _("Multiple different branches contain this commit:\n"
                          "{listing}")
                        .format(listing='\n'.join(' - ' + repr(ref.name) for ref in affected_main_branches))
                        )
    if selected_ref is None or commit is None:
        result.fail(os.EX_USAGE,
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

    result.value = command_context

    return result


def create_version_branch(command_context: CommandContext, operation: Callable[[VersionConfig, str], str]):
    result = Result()
    context: Context = command_context.context

    if not command_context.selected_ref.name in [const.LOCAL_BRANCH_PREFIX + context.parsed_config.release_branch_base,
                                                 const.REMOTES_PREFIX + context.parsed_config.remote_name + '/' + context.parsed_config.release_branch_base]:
        result.fail(os.EX_USAGE,
                    _("Failed to create release branch based on {branch}.")
                    .format(branch=repr(command_context.selected_ref.name)),
                    _("Release branches (major.minor) can only be created off {branch}")
                    .format(branch=repr(context.parsed_config.release_branch_base))
                    )

    existing_release_branches = list(repotools.git_list_refs(context.repo, repotools.ref_name([
        const.REMOTES_PREFIX,
        context.parsed_config.remote_name,
        'release'])))

    release_branch_merge_bases = dict()
    for release_branch in context.get_release_branches():
        merge_base = repotools.git_merge_base(context.repo, context.parsed_config.release_branch_base, release_branch)
        if merge_base is None:
            result.fail(os.EX_DATAERR,
                        "Failed to resolve merge base.",
                        None)
        branch_refs = release_branch_merge_bases.get(merge_base)
        if branch_refs is None:
            release_branch_merge_bases[merge_base] = branch_refs = list()
        branch_refs.append(release_branch)

    latest_branch = None
    branch_points_on_same_commit = list()
    subsequent_branches = list()

    for history_commit in repotools.git_list_commits(context.repo, None, command_context.selected_commit):
        branch_refs = release_branch_merge_bases.get(history_commit)
        if branch_refs is not None and len(branch_refs):
            branch_refs = list(
                filter(lambda tag_ref: context.parsed_config.release_branch_matcher.format(tag_ref.name) is not None,
                       branch_refs))
            if not len(branch_refs):
                continue

            branch_refs.sort(
                reverse=True,
                key=utils.cmp_to_key(
                    lambda tag_ref_a, tag_ref_b: semver.compare(
                        context.parsed_config.release_branch_matcher.format(tag_ref_a.name),
                        context.parsed_config.release_branch_matcher.format(tag_ref_b.name)
                    )
                )
            )
            if latest_branch is None:
                latest_branch = branch_refs[0]
            if history_commit == command_context.selected_commit:
                branch_points_on_same_commit.extend(branch_refs)
            # for tag_ref in tag_refs:
            #     print('<<' + tag_ref.name)
            break

    for history_commit in repotools.git_list_commits(context.repo, command_context.selected_commit,
                                                     command_context.selected_ref):
        branch_refs = release_branch_merge_bases.get(history_commit)
        if branch_refs is not None and len(branch_refs):
            branch_refs = list(
                filter(lambda tag_ref: context.parsed_config.release_branch_matcher.format(tag_ref.name) is not None,
                       branch_refs))
            if not len(branch_refs):
                continue

            branch_refs.sort(
                reverse=True,
                key=utils.cmp_to_key(
                    lambda tag_ref_a, tag_ref_b: semver.compare(
                        context.parsed_config.release_branch_matcher.format(tag_ref_a.name),
                        context.parsed_config.release_branch_matcher.format(tag_ref_b.name)
                    )
                )
            )
            # for tag_ref in tag_refs:
            #     print('>>' + tag_ref.name)
            subsequent_branches.extend(branch_refs)

    if context.verbose:
        cli.print("Branches on same commit:\n"
                  + '\n'.join(' - ' + repr(tag_ref.name) for tag_ref in branch_points_on_same_commit))

        cli.print("Subsequent branches:\n"
                  + '\n'.join(' - ' + repr(tag_ref.name) for tag_ref in subsequent_branches))

    if latest_branch is not None:
        latest_branch_version = context.parsed_config.release_branch_matcher.format(latest_branch.name)
        latest_branch_version_info = semver.parse_version_info(latest_branch_version)
    else:
        latest_branch_version = None
        latest_branch_version_info = None

    if latest_branch_version is not None:
        version_result = operation(context.parsed_config.version_config, latest_branch_version)
        result.add_subresult(version_result)

        new_version = version_result.value
        new_version_info = semver.parse_version_info(new_version)
    else:
        new_version_info = semver.parse_version_info(const.DEFAULT_INITIAL_VERSION)
        new_version = version.format_version_info(new_version_info)

    if context.parsed_config.sequential_versioning:
        new_sequential_version = create_sequence_number_for_version(context, new_version)
        sequential_version_tag_name = create_sequential_version_tag_name(context, new_sequential_version)
    else:
        new_sequential_version = None
        sequential_version_tag_name = None

    if not context.parsed_config.allow_shared_release_branch_base and len(branch_points_on_same_commit):
        result.fail(os.EX_USAGE,
                    _("Branch creation failed."),
                    _("Release branches cannot share a common ancestor commit.\n"
                      "Existing branches on commit {commit}:\n"
                      "{listing}")
                    .format(commit=command_context.selected_commit,
                            listing='\n'.join(' - ' + repr(tag_ref.name) for tag_ref in branch_points_on_same_commit)))

    if len(subsequent_branches):
        result.fail(os.EX_USAGE,
                    _("Branch creation failed."),
                    _("Subsequent release branches in history: %s\n")
                    % '\n'.join(' - ' + repr(tag_ref.name) for tag_ref in subsequent_branches))

    if context.parsed_config.tie_sequential_version_to_semantic_version \
            and len(existing_release_branches):
        prompt_result = prompt_for_confirmation(
            context=context,
            fail_title=_("Failed to create release branch based on {branch} in batch mode.")
                .format(branch=repr(command_context.selected_ref.name)),
            message=_("This operation disables version increments except for pre-release increments "
                      "on all existing branches.\n"
                      "Affected branches are:\n"
                      "{listing}")
                .format(listing=os.linesep.join(repr(branch.name) for branch in existing_release_branches))
            if not context.parsed_config.commit_version_property
            else _("This operation disables version increments on all existing branches.\n"
                   "Affected branches are:\n"
                   "{listing}")
                .format(listing=os.linesep.join(repr(branch.name) for branch in existing_release_branches)),
            prompt=_("Continue?"),
        )
        result.add_subresult(prompt_result)
        if result.has_errors() or not prompt_result.value:
            return result

    if not result.has_errors():
        if new_version is None:
            result.error(os.EX_SOFTWARE,
                         _("Internal error."),
                         _("Missing result version.")
                         )
        if latest_branch_version is not None and semver.compare(latest_branch_version, new_version) >= 0:
            result.error(os.EX_DATAERR,
                         _("Failed to increment version from {current_version} to {new_version}.")
                         .format(current_version=repr(latest_branch_version), new_version=repr(new_version)),
                         _("The new version is lower than or equal to the current version.")
                         )
        result.abort_on_error()

        branch_name = get_branch_name_for_version(context, new_version_info)
        tag_name = get_tag_name_for_version(context, new_version_info)

        clone_result = create_shared_clone_repository(context)
        result.add_subresult(clone_result)
        if result.has_errors():
            return result

        clone_context = clone_result.value

        # create branch ref
        git_or_fail(clone_context, result,
                    ['update-ref', 'refs/heads/' + branch_name, command_context.selected_commit],
                    _("Failed to push."))

        # # checkout base branch
        # cloned_repo_commands = []
        # checkout_command = ['checkout', '--force', context.parsed_config.release_branch_base]
        # cloned_repo_commands.append(checkout_command)
        #
        # for command in cloned_repo_commands:
        #     proc = repotools.git(clone_context.repo, *command)
        #     proc.wait()
        #     if proc.returncode != os.EX_OK:
        #         result.fail(os.EX_DATAERR,
        #                     _("Failed to check out release branch."),
        #                     _("An unexpected error occurred.")
        #                     )
        #
        # # run version change hooks on base branch
        # update_result = update_project_metadata(clone_context, new_version)
        # result.add_subresult(update_result)
        # if (result.has_errors()):
        #     result.fail(os.EX_DATAERR,
        #                 _("Version change hook run failed."),
        #                 _("An unexpected error occurred.")
        #                 )

        has_local_commit = False

        if (context.parsed_config.commit_version_property and new_version is not None) \
                or (
                            context.parsed_config.commit_sequential_version_property and new_sequential_version is not None):
            # if commit != selected_ref.target.obj_name:
            #     result.fail(os.EX_DATAERR,
            #                 _("Failed to commit version update."),
            #                 _("The selected commit {commit} does not represent the tip of {branch}.")
            #                 .format(commit=commit, branch=repr(selected_ref.name))
            #                 )

            # run version change hooks on new release branch
            git_or_fail(clone_context, result, ['checkout', '--force', branch_name],
                        _("Failed to check out release branch."))

            commit_info = VersionUpdateCommit()
            update_result = update_project_property_file(clone_context, new_version, new_sequential_version,
                                                         commit_info)
            result.add_subresult(update_result)
            if (result.has_errors()):
                result.fail(os.EX_DATAERR,
                            _("Version change hook run failed."),
                            _("An unexpected error occurred.")
                            )

            has_local_commit = True
        else:
            commit_info = None

        if has_local_commit:
            # commit changes
            cloned_repo_commands = []

            add_command = ['add', '--all']
            if context.verbose:
                add_command.append('--verbose')
            cloned_repo_commands.append(add_command)

            commit_command = ['commit', '--allow-empty']
            if context.verbose:
                commit_command.append('--verbose')
            commit_command.extend(['--message', commit_info.message])
            cloned_repo_commands.append(commit_command)

            for command in cloned_repo_commands:
                git_or_fail(clone_context, result, command, _("Failed to commit."))

        object_to_tag = 'refs/heads/' + branch_name

        # create sequential tag ref
        if sequential_version_tag_name is not None:
            git_or_fail(clone_context, result,
                        ['update-ref', 'refs/tags/' + sequential_version_tag_name, object_to_tag],
                        _("Failed to tag."))

        # create tag ref
        git_or_fail(clone_context, result, ['update-ref', 'refs/tags/' + tag_name, object_to_tag],
                    _("Failed to tag."))

        # show info and prompt for confirmation
        cli.print("branch              : " + cli.if_none(command_context.selected_ref.name))
        cli.print("branch_version      : " + cli.if_none(latest_branch_version))
        cli.print("new_branch          : " + cli.if_none(branch_name))
        cli.print("new_version         : " + cli.if_none(new_version))

        prompt_result = prompt_for_confirmation(
            context=context,
            fail_title=_("Failed to create release branch based on {branch} in batch mode.")
                .format(branch=repr(command_context.selected_ref.name)),
            message=_("The branch and tags are about to be pushed."),
            prompt=_("Continue?"),
        )
        result.add_subresult(prompt_result)
        if result.has_errors() or not prompt_result.value:
            return result

        # push atomically
        push_command = ['push', '--atomic']
        if context.dry_run:
            push_command.append('--dry-run')
        if context.verbose:
            push_command.append('--verbose')
        push_command.append('origin')
        # push the base branch commit
        # push_command.append(commit + ':' + 'refs/heads/' + selected_ref.local_branch_name)
        # push the new branch or fail if it exists
        push_command.extend(['--force-with-lease=refs/heads/' + branch_name + ':',
                             object_to_tag + ':' + 'refs/heads/' + branch_name])
        # push the new version tag or fail if it exists
        push_command.extend(['--force-with-lease=refs/tags/' + tag_name + ':',
                             'refs/tags/' + tag_name + ':' + 'refs/tags/' + tag_name])
        # push the new sequential version tag or fail if it exists
        if sequential_version_tag_name is not None:
            push_command.extend(['--force-with-lease=refs/tags/' + sequential_version_tag_name + ':',
                                 'refs/tags/' + sequential_version_tag_name + ':' + 'refs/tags/' + sequential_version_tag_name])

        git_or_fail(clone_context, result, push_command, _("Failed to push."))

    return result


def create_version_tag(command_context: CommandContext, operation: Callable[[VersionConfig, str], str]):
    result = Result()
    context: Context = command_context.context

    # TODO configuration
    allow_merge_base_tags = True  # context.parsed_config.allow_shared_release_branch_base

    branch_base_version = context.parsed_config.release_branch_matcher.format(command_context.selected_ref.name)
    if branch_base_version is not None:
        branch_base_version_info = semver.parse_version_info(branch_base_version)
    else:
        branch_base_version_info = None

    if branch_base_version is None:
        result.fail(os.EX_USAGE,
                    _("Cannot bump version."),
                    _("{branch} is not a release branch.")
                    .format(branch=repr(command_context.selected_ref.name)))

    latest_version_tag = None
    preceding_version_tag = None
    version_tags_on_same_commit = list()
    subsequent_version_tags = list()
    enclosing_versions = set()

    preceding_sequential_version_tag = None
    sequential_version_tags_on_same_commit = list()
    subsequent_sequential_version_tags = list()

    # merge_base = context.parsed_config.release_branch_base
    merge_base = repotools.git_merge_base(context.repo, context.parsed_config.release_branch_base,
                                          command_context.selected_commit)
    if merge_base is None:
        result.fail(os.EX_USAGE,
                    _("Cannot bump version."),
                    _("{branch} has no merge base with {base_branch}.")
                    .format(branch=repr(command_context.selected_ref.name),
                            base_branch=repr(context.parsed_config.release_branch_base)))

    # abort scan, when a preceding commit for each tag type has been processed.
    # enclosing_versions now holds enough information for operation validation,
    # assuming the branch has not gone haywire in earlier commits
    # TODO evaluate upper and lower bound version for efficiency
    abort_version_scan = False
    abort_sequential_version_scan = False

    before_commit = False
    for history_commit in repotools.git_list_commits(context.repo, merge_base, command_context.selected_ref):
        at_commit = history_commit == command_context.selected_commit
        at_merge_base = history_commit == merge_base
        version_tag_refs = None
        sequential_version_tag_refs = None

        assert not at_commit if before_commit else not before_commit
        assert not at_merge_base if not allow_merge_base_tags else True

        for tag_ref in repotools.git_get_tags_by_referred_object(context.repo, history_commit):
            version_info = context.parsed_config.version_tag_matcher.to_version_info(tag_ref.name)
            if version_info is not None:
                if at_merge_base:
                    # ignore apparent stray tags on potentially shared merge base
                    if version_info.major != branch_base_version_info.major \
                            or version_info.minor != branch_base_version_info.minor:
                        continue
                else:
                    # fail stray tags on exclusive branch commits
                    if version_info.major != branch_base_version_info.major \
                            or version_info.minor != branch_base_version_info.minor:
                        result.fail(os.EX_DATAERR,
                                    _("Cannot bump version."),
                                    _("Found stray version tag: {version}.")
                                    .format(version=repr(version.format_version_info(version_info)))
                                    )
                if version_tag_refs is None:
                    version_tag_refs = list()
                version_tag_refs.append(tag_ref)

            match = context.parsed_config.sequential_version_tag_matcher.fullmatch(tag_ref.name)
            if match is not None:
                if sequential_version_tag_refs is None:
                    sequential_version_tag_refs = list()
                sequential_version_tag_refs.append(tag_ref)

        if not abort_version_scan and version_tag_refs is not None and len(version_tag_refs):
            version_tag_refs.sort(
                reverse=True,
                key=utils.cmp_to_key(
                    lambda tag_ref_a, tag_ref_b: semver.compare(
                        context.parsed_config.version_tag_matcher.format(tag_ref_a.name),
                        context.parsed_config.version_tag_matcher.format(tag_ref_b.name)
                    )
                )
            )
            if latest_version_tag is None:
                latest_version_tag = version_tag_refs[0]
            if at_commit:
                version_tags_on_same_commit.extend(version_tag_refs)
            elif not before_commit:
                subsequent_version_tags.extend(version_tag_refs)
            if at_commit or before_commit and preceding_version_tag is None:
                preceding_version_tag = version_tag_refs[0]

            for tag_ref in version_tag_refs:
                enclosing_versions.add(context.parsed_config.version_tag_matcher.format(tag_ref.name))

            if before_commit:
                abort_version_scan = True

        if not abort_sequential_version_scan and sequential_version_tag_refs is not None and len(
                sequential_version_tag_refs):
            sequential_version_tag_refs.sort(
                reverse=True,
                key=utils.cmp_to_key(
                    lambda tag_ref_a, tag_ref_b: version.cmp_alnum_token(
                        context.parsed_config.sequential_version_tag_matcher.format(tag_ref_a.name),
                        context.parsed_config.sequential_version_tag_matcher.format(tag_ref_b.name)
                    )
                )
            )
            if at_commit:
                sequential_version_tags_on_same_commit.extend(sequential_version_tag_refs)
            elif not before_commit:
                subsequent_sequential_version_tags.extend(sequential_version_tag_refs)
            if at_commit or before_commit and preceding_sequential_version_tag is None:
                preceding_sequential_version_tag = sequential_version_tag_refs[0]

            if before_commit:
                abort_sequential_version_scan = True

        if at_commit:
            before_commit = True

        if abort_version_scan and abort_sequential_version_scan:
            break

    preceding_version = context.parsed_config.version_tag_matcher.format(
        preceding_version_tag.name) if preceding_version_tag is not None else None

    preceding_sequential_version = context.parsed_config.sequential_version_tag_matcher.format(
        preceding_sequential_version_tag.name) if preceding_sequential_version_tag is not None else None
    if preceding_sequential_version is not None:
        preceding_sequential_version = int(preceding_sequential_version)

    if context.verbose:
        cli.print("Tags on selected commit:\n"
                  + '\n'.join(' - ' + repr(tag_ref.name) for tag_ref in version_tags_on_same_commit))

        cli.print("Tags in subsequent history:\n"
                  + '\n'.join(' - ' + repr(tag_ref.name) for tag_ref in subsequent_version_tags))

    if preceding_version_tag is not None:
        latest_branch_version = context.parsed_config.version_tag_matcher.format(preceding_version_tag.name)
        latest_branch_version_info = semver.parse_version_info(latest_branch_version)
    else:
        latest_branch_version = None
        latest_branch_version_info = None

    if latest_branch_version is not None:
        version_result = operation(context.parsed_config.version_config, latest_branch_version)
        result.add_subresult(version_result)

        new_version = version_result.value
        if result.has_errors():
            return result
    else:
        template_version_info = semver.parse_version_info(const.DEFAULT_INITIAL_VERSION)
        new_version = semver.format_version(
            major=branch_base_version_info.major,
            minor=branch_base_version_info.minor,

            patch=template_version_info.patch,
            prerelease=template_version_info.prerelease,
            build=template_version_info.build,
        )

    new_version_info = semver.parse_version_info(new_version)

    if context.parsed_config.sequential_versioning \
            and not len(sequential_version_tags_on_same_commit):
        new_sequential_version = create_sequence_number_for_version(context, new_version)
        sequential_version_tag_name = create_sequential_version_tag_name(context, new_sequential_version)
    else:
        new_sequential_version = None
        sequential_version_tag_name = None

    if new_version_info.major != branch_base_version_info.major or new_version_info.minor != branch_base_version_info.minor:
        result.fail(os.EX_USAGE,
                    _("Tag creation failed."),
                    _("The major.minor part of the new version {new_version}"
                      " does not match the branch version {branch_version}.")
                    .format(new_version=repr(new_version),
                            branch_version=repr(
                                "%d.%d" % (branch_base_version_info.major, branch_base_version_info.minor)))
                    )

    if len(subsequent_version_tags):
        result.fail(os.EX_USAGE,
                    _("Tag creation failed."),
                    _("There are version tags in branch history following the selected commit {commit}:\n"
                      "{listing}")
                    .format(commit=command_context.selected_commit,
                            listing='\n'.join(' - ' + repr(tag_ref.name) for tag_ref in subsequent_version_tags))
                    )

    if len(version_tags_on_same_commit):
        if context.parsed_config.allow_qualifier_increments_within_commit:
            preceding_commit_version = context.parsed_config.version_tag_matcher.format(
                version_tags_on_same_commit[0].name)
            prerelease_keywords_list = [context.parsed_config.version_config.qualifiers, 1]

            preceding_commit_version_ = version.parse_version(preceding_commit_version)
            new_commit_version_ = version.parse_version(new_version)
            version_delta = version.determine_version_delta(preceding_commit_version_,
                                                            new_commit_version_,
                                                            prerelease_keywords_list
                                                            )

            version_increment_eval_result = version.evaluate_version_increment(preceding_commit_version_,
                                                                               new_commit_version_,
                                                                               context.parsed_config.strict_mode,
                                                                               prerelease_keywords_list)
            result.add_subresult(version_increment_eval_result)
            if result.has_errors():
                return result

            if not version_delta.prerelease_field_only(0, False):
                result.fail(os.EX_USAGE,
                            _("Tag creation failed."),
                            _("The selected commit already has version tags.\n"
                              "Operations on such a commit are limited to pre-release type increments.")
                            )
        else:
            result.fail(os.EX_USAGE,
                        _("Tag creation failed."),
                        _("There are version tags pointing to the selected commit {commit}.\n"
                          "Consider reusing these versions or bumping them to stable."
                          "{listing}")
                        .format(commit=command_context.selected_commit,
                                listing='\n'.join(
                                    ' - ' + repr(tag_ref.name) for tag_ref in subsequent_version_tags))
                        )

    global_seq_number = get_global_sequence_number(context)
    if context.parsed_config.tie_sequential_version_to_semantic_version \
            and global_seq_number is not None \
            and new_sequential_version is not None \
            and preceding_sequential_version != global_seq_number:
        result.fail(os.EX_USAGE,
                    _("Tag creation failed."),
                    _(
                        "The preceding sequential version {seq_val} "
                        "does not equal the global sequential version {global_seq_val}.")
                    .format(seq_val=preceding_sequential_version
                    if preceding_sequential_version is not None
                    else '<none>',
                            global_seq_val=global_seq_number)
                    )

    if not result.has_errors():
        if new_version is None:
            result.fail(os.EX_SOFTWARE,
                        _("Internal error."),
                        _("Missing result version.")
                        )
        if latest_branch_version is not None and semver.compare(latest_branch_version, new_version) >= 0:
            result.fail(os.EX_DATAERR,
                        _("Failed to increment version from {current} to {new}.")
                        .format(current=repr(latest_branch_version), new=repr(new_version)),
                        _("The new version is lower than or equal to the current version.")
                        )

        if context.parsed_config.push_to_local \
                and command_context.current_branch.short_name == command_context.selected_ref.short_name:
            if context.verbose:
                cli.print(
                    _('Checking out {base_branch} in order to avoid failing the push to a checked-out release branch')
                        .format(base_branch=repr(context.parsed_config.release_branch_base)))

            git_or_fail(context, result, ['checkout', context.parsed_config.release_branch_base])
            original_current_branch = command_context.current_branch
        else:
            original_current_branch = None

        branch_name = get_branch_name_for_version(context, new_version_info)
        tag_name = get_tag_name_for_version(context, new_version_info)

        has_local_commit = False

        clone_result = create_shared_clone_repository(context)
        result.add_subresult(clone_result)
        if result.has_errors():
            return result

        clone_context = clone_result.value

        # run version change hooks on release branch
        if (context.parsed_config.commit_version_property and new_version is not None) \
                or (
                            context.parsed_config.commit_sequential_version_property and new_sequential_version is not None):
            if command_context.selected_commit != command_context.selected_ref.target.obj_name:
                result.fail(os.EX_DATAERR,
                            _("Failed to commit version update."),
                            _("The selected commit {commit} does not represent the tip of {branch}.")
                            .format(commit=command_context.selected_commit,
                                    branch=repr(command_context.selected_ref.name))
                            )

            checkout_command = ['checkout', '--force', '--track', '-b', branch_name,
                                const.REMOTES_PREFIX + context.parsed_config.remote_name + '/' + branch_name]

            proc = repotools.git(clone_context.repo, *checkout_command)
            proc.wait()
            if proc.returncode != os.EX_OK:
                result.fail(os.EX_DATAERR,
                            _("Failed to check out release branch."),
                            _("An unexpected error occurred.")
                            )

            commit_info = VersionUpdateCommit()
            update_result = update_project_property_file(clone_context, new_version, new_sequential_version,
                                                         commit_info)
            result.add_subresult(update_result)
            if (result.has_errors()):
                result.fail(os.EX_DATAERR,
                            _("Version change hook run failed."),
                            _("An unexpected error occurred.")
                            )

            has_local_commit = True
        else:
            commit_info = None

        if has_local_commit:
            # commit changes
            cloned_repo_commands = []

            add_command = ['add', '--all']
            if context.verbose:
                add_command.append('--verbose')
            cloned_repo_commands.append(add_command)

            commit_command = ['commit', '--allow-empty']
            if context.verbose:
                commit_command.append('--verbose')
            commit_command.extend(['--message', commit_info.message])
            cloned_repo_commands.append(commit_command)

            for command in cloned_repo_commands:
                proc = repotools.git(clone_context.repo, *command)
                proc.wait()
                if proc.returncode != os.EX_OK:
                    result.fail(os.EX_DATAERR,
                                _("Failed to commit."),
                                _("An unexpected error occurred.")
                                )

        object_to_tag = branch_name if has_local_commit else command_context.selected_commit

        # create sequential tag ref
        if sequential_version_tag_name is not None:
            proc = repotools.git(clone_context.repo,
                                 *['update-ref', 'refs/tags/' + sequential_version_tag_name, object_to_tag])
            proc.wait()
            if proc.returncode != os.EX_OK:
                result.fail(os.EX_DATAERR,
                            _("Failed to tag."),
                            _("An unexpected error occurred.")
                            )

        # create tag ref
        proc = repotools.git(clone_context.repo, *['update-ref', 'refs/tags/' + tag_name, object_to_tag])
        proc.wait()
        if proc.returncode != os.EX_OK:
            result.fail(os.EX_DATAERR,
                        _("Failed to tag."),
                        _("An unexpected error occurred.")
                        )

        # show info and prompt for confirmation
        print("branch              : " + cli.if_none(command_context.selected_ref.name))
        print("branch_version      : " + cli.if_none(latest_branch_version))
        print("new_tag             : " + cli.if_none(tag_name))
        print("new_version         : " + cli.if_none(new_version))

        prompt_result = prompt_for_confirmation(
            context=context,
            fail_title=_("Failed to create release tag based on {branch} in batch mode.")
                .format(branch=repr(command_context.selected_ref.name)),
            message=_("The tags are about to be pushed."),
            prompt=_("Continue?"),
        )
        result.add_subresult(prompt_result)
        if result.has_errors() or not prompt_result.value:
            return result

        # push atomically
        push_command = ['push', '--atomic']
        if context.dry_run:
            push_command.append('--dry-run')
        if context.verbose:
            push_command.append('--verbose')
        push_command.append('origin')
        # push the release branch commit or its version increment commit
        push_command.append(repotools.ref_target(object_to_tag) + ':' + 'refs/heads/' + branch_name)
        # push the new version tag or fail if it exists
        push_command.extend(['--force-with-lease=refs/tags/' + tag_name + ':',
                             'refs/tags/' + tag_name + ':' + 'refs/tags/' + tag_name])
        # push the new sequential version tag or fail if it exists
        if sequential_version_tag_name is not None:
            push_command.extend(['--force-with-lease=refs/tags/' + sequential_version_tag_name + ':',
                                 'refs/tags/' + sequential_version_tag_name + ':' + 'refs/tags/' + sequential_version_tag_name])

        proc = repotools.git(clone_context.repo, *push_command)
        proc.wait()
        if proc.returncode != os.EX_OK:
            result.fail(os.EX_DATAERR,
                        _("Failed to push."),
                        _("An unexpected error occurred.")
                        )

        if original_current_branch is not None:
            if context.verbose:
                cli.print(
                    _('Switching back to {original_branch} ')
                        .format(original_branch=repr(original_current_branch.name)))

            git_or_fail(context, result, ['checkout', original_current_branch.short_name])

    return result


def check_requirements(result_out: Result,
                       command_context: CommandContext,
                       ref: repotools.Ref,
                       for_modification: bool,
                       with_upstream: bool,
                       in_sync_with_upstream: bool,
                       fail_message: str):
    if ref.local_branch_name is not None:
        # check, whether the  selected branch/commit is on remote

        if with_upstream and command_context.selected_branch.upstream is None:
            result_out.fail(os.EX_USAGE,
                            fail_message,
                            _("{branch} does not have an upstream branch.")
                            .format(branch=repr(ref.name)))

        # if branch_info.upstream.short_name != selected_ref.short_name:
        #     result.fail(os.EX_USAGE,
        #                 _("Version creation failed."),
        #                 _("{branch} has an upstream branch with mismatching short name: {remote_branch}.")
        #                 .format(branch=repr(selected_ref.name),
        #                         remote_branch=repr(branch_info.upstream.name))
        #                 )

        if in_sync_with_upstream and command_context.selected_branch.upstream is not None:
            push_merge_base = repotools.git_merge_base(command_context.context.repo, command_context.selected_commit,
                                                       command_context.selected_branch.upstream)
            if push_merge_base is None:
                result_out.fail(os.EX_USAGE,
                                fail_message,
                                _("{branch} does not have a common base with its upstream branch: {remote_branch}")
                                .format(branch=repr(ref.name),
                                        remote_branch=repr(command_context.selected_branch.upstream.name)))
            elif push_merge_base != command_context.selected_commit:
                result_out.fail(os.EX_USAGE,
                                fail_message,
                                _("{branch} is not in sync with its upstream branch.\n"
                                  "Push your changes and try again.")
                                .format(branch=repr(ref.name),
                                        remote_branch=repr(command_context.selected_branch.upstream.name)))

    discontinuation_tags, discontinuation_tag_name = get_discontinuation_tags(command_context.context,
                                                                              ref)
    if for_modification and len(discontinuation_tags):
        result_out.fail(os.EX_USAGE,
                        fail_message,
                        _("{branch} is discontinued.")
                        .format(branch=repr(ref.name)))


def create_version(context: Context, operation: Callable[[VersionConfig, str], str]):
    result = Result()
    context_result = get_command_context(
        context=context,
        object_arg=utils.get_or_default(context.args, '<object>', None)
    )
    result.add_subresult(context_result)
    command_context = context_result.value

    check_requirements(result_out=result,
                       command_context=command_context,
                       ref=command_context.selected_ref,
                       for_modification=True,
                       with_upstream=True,  # not context.parsed_config.push_to_local
                       in_sync_with_upstream=True,
                       fail_message=_("Version creation failed.")
                       )

    # determine the type of operation to be performed and run according subroutines
    if operation == version.version_bump_major \
            or operation == version.version_bump_minor:

        tag_result = create_version_branch(command_context, operation)
        result.add_subresult(tag_result)

    elif operation == version.version_bump_patch \
            or operation == version.version_bump_qualifier \
            or operation == version.version_bump_prerelease \
            or operation == version.version_bump_to_release:

        tag_result = create_version_tag(command_context, operation)
        result.add_subresult(tag_result)

    elif isinstance(operation, version.version_set):

        version_result = operation(context.parsed_config.version_config, None)
        result.add_subresult(version_result)
        new_version = version_result.value
        if new_version is None:
            result.fail(os.EX_USAGE,
                        _("Illegal argument."),
                        _("Failed to parse version.")
                        )
        new_version_info = semver.parse_version_info(new_version)

        branch_name = get_branch_name_for_version(context, new_version_info)

        release_branch = repotools.get_branch_by_name(context.repo, branch_name, BranchSelection.BRANCH_PREFER_LOCAL)
        if release_branch is None:
            tag_result = create_version_branch(command_context, operation)
            result.add_subresult(tag_result)
        else:
            selected_ref = release_branch
            tag_result = create_version_tag(command_context, operation)
            result.add_subresult(tag_result)

    if not result.has_errors() \
            and context.parsed_config.pull_after_bump \
            and not context.parsed_config.push_to_local:
        proc = repotools.git(context.repo, 'fetch', context.parsed_config.remote_name)
        proc.wait()
        if proc.returncode != os.EX_OK:
            result.fail(os.EX_UNAVAILABLE,
                        _("Failed to fetch from {remote}")
                        .format(remote=context.parsed_config.remote_name),
                        None)
        proc = repotools.git(context.repo, 'fetch', '--tags', context.parsed_config.remote_name)
        proc.wait()
        if proc.returncode != os.EX_OK:
            result.fail(os.EX_UNAVAILABLE,
                        _("Failed to fetch from {remote}")
                        .format(remote=context.parsed_config.remote_name),
                        None)
        proc = repotools.git(context.repo, 'pull', '--ff-only', context.parsed_config.remote_name)
        proc.wait()
        if proc.returncode != os.EX_OK:
            result.warn(
                _("Failed to fast forward from {remote}")
                    .format(remote=command_context.current_branch.name),
                None)

    return result


def discontinue_version(context: Context):
    result = Result()

    object_arg = context.args['<object>']

    reintegrate = cli.get_boolean_opt(context.args, '--reintegrate')

    context_result = get_command_context(
        context=context,
        object_arg=utils.get_or_default(context.args, '<object>', None)
    )
    result.add_subresult(context_result)
    command_context: CommandContext = context_result.value

    base_branch_ref = repotools.get_branch_by_name(context.repo, context.parsed_config.release_branch_base,
                                                   BranchSelection.BRANCH_PREFER_LOCAL)

    release_branch = command_context.selected_ref

    release_branch_info = get_branch_info(command_context, release_branch)

    check_requirements(result_out=result,
                       command_context=command_context,
                       ref=release_branch,
                       for_modification=True,
                       with_upstream=True,  # not context.parsed_config.push_to_local
                       in_sync_with_upstream=True,
                       fail_message=_("Build failed.")
                       )

    if release_branch is None:
        result.fail(os.EX_USAGE,
                    _("Branch discontinuation failed."),
                    _("Failed to resolve an object for token {object}.")
                    .format(object=repr(object_arg))
                    )

    discontinuation_tags, discontinuation_tag_name = get_discontinuation_tags(context, release_branch)

    if discontinuation_tag_name is None:
        result.fail(os.EX_USAGE,
                    _("Branch discontinuation failed."),
                    _("{branch} cannot be discontinued.")
                    .format(branch=repr(release_branch.name))
                    )

    if context.verbose:
        cli.print("discontinuation tags:")
        for discontinuation_tag in discontinuation_tags:
            print(' - ' + discontinuation_tag.name)
        pass

    if len(discontinuation_tags):
        result.fail(os.EX_USAGE,
                    _("Branch discontinuation failed."),
                    _("The branch {branch} is already discontinued.")
                    .format(branch=repr(release_branch.name))
                    )
    # show info and prompt for confirmation
    print("discontinued_branch : " + cli.if_none(release_branch.name))

    if reintegrate is None:
        prompt_result = prompt_for_confirmation(
            context=context,
            fail_title=_("Failed to determine merge mode for {branch} in batch mode."),
            message=_("Branches may be reintegrated upon discontinuation."),
            prompt=_("Do you want to reintegrate {branch} into {base_branch}?")
                .format(branch=repr(release_branch.short_name),
                        base_branch=repr(base_branch_ref.short_name)),
        )
        result.add_subresult(prompt_result)
        if result.has_errors():
            return result

        reintegrate = prompt_result.value

    if not result.has_errors():
        # run merge on local clone

        clone_result = create_shared_clone_repository(context)
        result.add_subresult(clone_result)
        if result.has_errors():
            return result

        clone_context: Context = clone_result.value

        changes = list()

        if reintegrate:
            git_or_fail(clone_context, result,
                        ['checkout', base_branch_ref.short_name],
                        _("Failed to checkout branch {branch_name}.")
                        .format(branch_name=repr(base_branch_ref.short_name))
                        )

            git_or_fail(clone_context, result,
                        ['merge', '--no-ff', release_branch_info.upstream.name],
                        _("Failed to merge work branch.\n"
                          "Rebase {work_branch} on {base_branch} and try again")
                        .format(work_branch=repr(release_branch.short_name),
                                base_branch=repr(base_branch_ref.short_name))
                        )
            changes.append(_("{branch} reintegrated into {base_branch}")
                           .format(branch=repr(release_branch.name), base_branch=repr(base_branch_ref.name)))

        changes.append(_("Discontinuation tag"))
        prompt_result = prompt_for_confirmation(
            context=context,
            fail_title=_("Failed to discontinue {branch} in batch mode.")
                .format(branch=repr(release_branch.name)),
            message=(" - " + (os.linesep + " - ").join([_("Changes to be pushed:")] + changes)),
            prompt=_("Continue?"),
        )
        result.add_subresult(prompt_result)
        if result.has_errors() or not prompt_result.value:
            return result

        push_command = ['push', '--atomic']
        if context.dry_run:
            push_command.append('--dry-run')
        if context.verbose:
            push_command.append('--verbose')
        push_command.append('origin')

        push_command.append(base_branch_ref.name + ':' + 'refs/heads/' + base_branch_ref.short_name)
        push_command.append('--force-with-lease=refs/tags/' + discontinuation_tag_name + ':')
        push_command.append(release_branch.obj_name + ':' + 'refs/tags/' + discontinuation_tag_name)

        git_or_fail(clone_context, result, push_command)

        # attempt a fast forward pull
        proc = repotools.git(context.repo, 'pull', '--ff-only', context.parsed_config.remote_name)
        proc.wait()
        if proc.returncode != os.EX_OK:
            result.warn(
                _("Failed to fast forward from {remote}")
                    .format(remote=context.parsed_config.remote_name),
                None)

        proc = repotools.git(context.repo, 'pull', '--ff-only', '--tags', context.parsed_config.remote_name)
        proc.wait()
        if proc.returncode != os.EX_OK:
            result.warn(
                _("Failed to fast forward from {remote}")
                    .format(remote=context.parsed_config.remote_name),
                None)

    return result


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


def begin(context: Context):
    result = Result()
    context_result = get_command_context(
        context=context,
        object_arg=utils.get_or_default(context.args, '<base-object>', None)
    )
    result.add_subresult(context_result)
    command_context: CommandContext = context_result.value

    check_requirements(result_out=result,
                       command_context=command_context,
                       ref=command_context.selected_ref,
                       for_modification=True,
                       with_upstream=True,  # not context.parsed_config.push_to_local
                       in_sync_with_upstream=True,
                       fail_message=_("Version creation failed.")
                       )

    branch_supertype = context.args['<supertype>']
    branch_type = context.args['<type>']
    branch_short_name = context.args['<name>']

    if branch_supertype not in [const.BRANCH_PREFIX_DEV, const.BRANCH_PREFIX_PROD]:
        result.fail(os.EX_USAGE,
                    _("Invalid branch super type: {supertype}.")
                    .format(supertype=repr(branch_supertype)),
                    None)

    work_branch_name = utils.split_join('/', False, False, branch_supertype, branch_type, branch_short_name)
    work_branch_ref_name = utils.split_join('/', False, False, const.LOCAL_BRANCH_PREFIX, work_branch_name)
    work_branch_class = get_branch_class(context, work_branch_ref_name)

    if True:
        work_branch_info = get_branch_info(command_context, work_branch_ref_name)
        if work_branch_info is not None:
            result.fail(os.EX_USAGE,
                        _("The branch {branch} already exists locally or remotely.")
                        .format(branch=repr(work_branch_name)),
                        None)

    allowed_base_branch_class = const.BRANCHING[work_branch_class]

    base_branch, base_branch_class = select_ref(result, command_context.selected_branch,
                                                BranchSelection.BRANCH_PREFER_LOCAL)
    if not command_context.selected_explicitly and branch_supertype == const.BRANCH_PREFIX_DEV:
        fixed_base_branch_info = get_branch_info(command_context,
                                                 'refs/heads/' + context.parsed_config.release_branch_base)
        fixed_base_branch, fixed_destination_branch_class = select_ref(result,
                                                                       fixed_base_branch_info,
                                                                       BranchSelection.BRANCH_PREFER_LOCAL)

        base_branch, base_branch_class = fixed_base_branch, fixed_destination_branch_class

    if allowed_base_branch_class != base_branch_class:
        result.fail(os.EX_USAGE,
                    _("The branch {branch} is not a valid base for {supertype} branches.")
                    .format(branch=repr(base_branch.name),
                            supertype=repr(branch_supertype)),
                    None)

    if base_branch is None:
        result.fail(os.EX_USAGE,
                    _("Base branch undetermined."),
                    None)

    if context.verbose:
        cli.print("branch_name: " + command_context.selected_ref.name)
        cli.print("work_branch_name: " + work_branch_name)
        cli.print("base_branch_name: " + base_branch.name)

    if not context.dry_run and not result.has_errors():
        index_status = git(context, ['diff-index', 'HEAD', '--'])
        if index_status == 1:
            result.fail(os.EX_USAGE,
                        _("Branch creation aborted."),
                        _("You have staged changes in your workspace.\n"
                          "Unstage, commit or stash them and try again."))
        elif index_status != 0:
            result.fail(os.EX_DATAERR,
                        _("Failed to determine index status."),
                        None)

        git_or_fail(context, result,
                    ['update-ref', work_branch_ref_name, command_context.selected_commit, ''],
                    _("Failed to create branch {branch_name}.")
                    .format(branch_name=work_branch_name)
                    )
        git_or_fail(context, result,
                    ['checkout', work_branch_name],
                    _("Failed to checkout branch {branch_name}.")
                    .format(branch_name=work_branch_name)
                    )

    return result


def end(context: Context):
    result = Result()
    context_result = get_command_context(
        context=context,
        object_arg=utils.get_or_default(context.args, '<work-branch>', None)
    )
    result.add_subresult(context_result)
    command_context: CommandContext = context_result.value

    base_context_result = get_command_context(
        context=context,
        object_arg=utils.get_or_default(context.args, '<base-branch>', None)
    )
    result.add_subresult(base_context_result)
    base_command_context: CommandContext = base_context_result.value

    check_requirements(result_out=result,
                       command_context=command_context,
                       ref=command_context.selected_ref,
                       for_modification=True,
                       with_upstream=True,  # not context.parsed_config.push_to_local
                       in_sync_with_upstream=True,
                       fail_message=_("Version creation failed.")
                       )

    work_branch = None

    arg_work_branch = WorkBranch()
    arg_work_branch.prefix = context.args['<supertype>']
    arg_work_branch.type = context.args['<type>']
    arg_work_branch.name = context.args['<name>']

    if arg_work_branch.prefix is not None and arg_work_branch.type is not None and arg_work_branch.name is not None:
        if arg_work_branch.prefix not in [const.BRANCH_PREFIX_DEV, const.BRANCH_PREFIX_PROD]:
            result.fail(os.EX_USAGE,
                        _("Invalid branch super type: {supertype}.")
                        .format(supertype=repr(arg_work_branch.prefix)),
                        None)

    else:
        arg_work_branch = None

    ref_work_branch = WorkBranch()
    selected_ref_match = context.parsed_config.work_branch_matcher.fullmatch(command_context.selected_ref.name)
    if selected_ref_match is not None:
        ref_work_branch.prefix = selected_ref_match.group('prefix')
        ref_work_branch.type = selected_ref_match.group('type')
        ref_work_branch.name = selected_ref_match.group('name')
    else:
        ref_work_branch = None

        if command_context.selected_explicitly:
            result.fail(os.EX_USAGE,
                        _("The ref {branch} does not refer to a work branch.")
                        .format(branch=repr(command_context.selected_ref.name)),
                        None)

    work_branch = ref_work_branch or arg_work_branch

    work_branch_info = get_branch_info(command_context, work_branch.local_ref_name())
    if work_branch_info is None:
        result.fail(os.EX_USAGE,
                    _("The branch {branch} does neither exist locally nor remotely.")
                    .format(branch=repr(work_branch.branch_name())),
                    None)

    work_branch_ref, work_branch_class = select_ref(result,
                                                    work_branch_info,
                                                    BranchSelection.BRANCH_PREFER_LOCAL)

    allowed_base_branch_class = const.BRANCHING[work_branch_class]

    base_branch_info = get_branch_info(base_command_context,
                                       base_command_context.selected_ref)

    base_branch_ref, base_branch_class = select_ref(result,
                                                    base_branch_info,
                                                    BranchSelection.BRANCH_PREFER_LOCAL)
    if not base_command_context.selected_explicitly:
        if work_branch.prefix == const.BRANCH_PREFIX_DEV:
            fixed_base_branch_info = get_branch_info(base_command_context,
                                                     repotools.create_ref_name(const.LOCAL_BRANCH_PREFIX,
                                                                               context.parsed_config.release_branch_base))
            fixed_base_branch, fixed_destination_branch_class = select_ref(result,
                                                                           fixed_base_branch_info,
                                                                           BranchSelection.BRANCH_PREFER_LOCAL)

            base_branch_ref, base_branch_class = fixed_base_branch, fixed_destination_branch_class
        elif work_branch.prefix == const.BRANCH_PREFIX_PROD:
            # discover closest merge base in release branches

            release_branches = repotools.git_list_refs(context.repo,
                                                       repotools.create_ref_name(const.REMOTES_PREFIX,
                                                                                 context.parsed_config.remote_name,
                                                                                 'release'))
            release_branches = list(release_branches)
            release_branches.sort(reverse=True, key=utils.cmp_to_key(lambda ref_a, ref_b: semver.compare(
                context.parsed_config.release_branch_matcher.format(ref_a.name),
                context.parsed_config.release_branch_matcher.format(ref_b.name)
            )))
            for release_branch_ref in release_branches:
                merge_base = repotools.git_merge_base(context.repo, base_branch_ref, work_branch_ref.name)
                if merge_base is not None:
                    base_branch_info = get_branch_info(base_command_context, release_branch_ref)

                    base_branch_ref, base_branch_class = select_ref(result,
                                                                    base_branch_info,
                                                                    BranchSelection.BRANCH_PREFER_LOCAL)
                    break

    if allowed_base_branch_class != base_branch_class:
        result.fail(os.EX_USAGE,
                    _("The branch {branch} is not a valid base for {supertype} branches.")
                    .format(branch=repr(base_branch_ref.name),
                            supertype=repr(work_branch.prefix)),
                    None)

    if base_branch_ref is None:
        result.fail(os.EX_USAGE,
                    _("Base branch undetermined."),
                    None)

    if context.verbose:
        cli.print("branch_name: " + command_context.selected_ref.name)
        cli.print("work_branch_name: " + work_branch_ref.name)
        cli.print("base_branch_name: " + base_branch_ref.name)

    # check, if already merged
    merge_base = repotools.git_merge_base(context.repo, base_branch_ref, work_branch_ref.name)
    if work_branch_ref.obj_name == merge_base:
        cli.print(_("Branch {branch} is already merged.")
                  .format(branch=repr(work_branch_ref.name)))
        return result

    # check for staged changes
    index_status = git(context, ['diff-index', 'HEAD', '--'])
    if index_status == 1:
        result.fail(os.EX_USAGE,
                    _("Branch creation aborted."),
                    _("You have staged changes in your workspace.\n"
                      "Unstage, commit or stash them and try again."))
    elif index_status != 0:
        result.fail(os.EX_DATAERR,
                    _("Failed to determine index status."),
                    None)

    if not context.dry_run and not result.has_errors():
        # run merge
        git_or_fail(context, result,
                    ['checkout', base_branch_ref.short_name],
                    _("Failed to checkout branch {branch_name}.")
                    .format(branch_name=repr(base_branch_ref.short_name))
                    )

        git_or_fail(context, result,
                    ['merge', '--no-ff', work_branch_ref],
                    _("Failed to merge work branch.\n"
                      "Rebase {work_branch} on {base_branch} and try again")
                    .format(work_branch=repr(work_branch_ref.short_name),
                            base_branch=repr(base_branch_ref.short_name))
                    )

        git_or_fail(context, result,
                    ['push', context.parsed_config.remote_name, base_branch_ref.short_name],
                    _("Failed to push branch {branch_name}.")
                    .format(branch_name=repr(base_branch_ref.short_name))
                    )

    return result


def log(context: Context):
    result = Result()

    object_arg = context.args['<object>']
    args = context.args['<git-arg>']

    if object_arg is not None:
        selected_branch = get_branch_by_branch_name_or_version_tag(context, object_arg,
                                                                   BranchSelection.BRANCH_PREFER_LOCAL)
        if selected_branch is None:
            result.fail(os.EX_USAGE,
                        _("Log failed."),
                        _("Failed to resolve an object for token {object}.")
                        .format(object=repr(object_arg))
                        )
    else:
        selected_branch = None

    log_command = ['log']
    if context.pretty:
        log_command.append('--pretty')
    if context.dry_run:
        log_command.append('--dry-run')
    if context.verbose:
        log_command.append('--verbose')
    if selected_branch is not None:
        log_command.append(selected_branch)

    proc = repotools.git_interactive(context.repo, *(log_command + args))
    proc.wait()

    return result


def status(context):
    result = Result()

    git_context = RepoContext()
    git_context.dir = context.root

    unique_codes = set()
    unique_version_codes = list()

    upstreams = repotools.git_get_upstreams(context.repo)
    branch_info_dict = dict()

    for branch_ref in repotools.git_list_refs(git_context, const.REMOTES_PREFIX + context.parsed_config.remote_name):
        branch_match = context.parsed_config.release_branch_matcher.fullmatch(branch_ref.name)
        if branch_match:
            branch_version = context.parsed_config.release_branch_matcher.to_version(branch_ref.name)

            branch_version_string = get_branch_version_component_for_version(context, branch_version)

            discontinuation_tags, discontinuation_tag_name = get_discontinuation_tags(context, branch_ref)

            update_branch_info(context, branch_info_dict, upstreams, branch_ref)

            branch_info = branch_info_dict.get(branch_ref.name)
            discontinued = len(discontinuation_tags)

            if discontinued:
                status_color = colors.partial(colors.color, fg='gray')
                status_error_color = colors.partial(colors.color, fg='red')
                status_local_color = colors.partial(colors.color, fg='blue')
                status_remote_color = colors.partial(colors.color, fg='green')
            else:
                status_color = colors.partial(colors.color, fg='white', style='bold')
                status_error_color = colors.partial(colors.color, fg='red', style='bold')
                status_local_color = colors.partial(colors.color, fg='blue', style='bold')
                status_remote_color = colors.partial(colors.color, fg='green', style='bold')

            error_color = colors.partial(colors.color, fg='white', bg='red', style='bold')

            cli.fcwrite(sys.stdout, status_color, "version: " + branch_version_string + ' [')
            if branch_info.local is not None:
                local_branch_color = status_local_color
                if not branch_info.upstream.short_name.endswith('/' + branch_info.local.short_name):
                    result.error(os.EX_DATAERR,
                                 _("Local and upstream branch have a mismatching short name."),
                                 None)
                    local_branch_color = error_color
                if context.verbose:
                    cli.fcwrite(sys.stdout, local_branch_color, branch_info.local.name)
                else:
                    cli.fcwrite(sys.stdout, local_branch_color, branch_info.local.short_name)
            if branch_info.upstream is not None:
                if branch_info.local is not None:
                    cli.fcwrite(sys.stdout, status_color, ' => ')
                if context.verbose:
                    cli.fcwrite(sys.stdout, status_remote_color, branch_info.upstream.name)
                else:
                    cli.fcwrite(sys.stdout, status_remote_color, branch_info.upstream.short_name)
            cli.fcwrite(sys.stdout, status_color, "]")
            if discontinued:
                cli.fcwrite(sys.stdout, status_color, ' (' + _('discontinued') + ')')

            cli.fcwriteln(sys.stdout, status_color)

            tags = repotools.git_get_branch_tags(context=git_context,
                                                 base=context.parsed_config.release_branch_base,
                                                 dest=branch_ref.name,
                                                 from_fork_point=False,
                                                 reverse=True,
                                                 tag_filter=None,
                                                 commit_tag_comparator=lambda a, b:
                                                 -1 if context.parsed_config.sequential_version_tag_matcher.fullmatch(
                                                     a.name) is not None
                                                 else 1)

            tags = list(tags)

            for branch_tag_ref in tags:
                # print the sequential version tag
                tag_match = context.parsed_config.sequential_version_tag_matcher.fullmatch(branch_tag_ref.name)
                if tag_match:
                    unique_code = tag_match.group(
                        context.parsed_config.sequential_version_tag_matcher.group_unique_code)
                    version_string = unique_code

                    unique_version_codes.append(int(unique_code))

                    if unique_code in unique_codes:
                        result.error(os.EX_DATAERR,
                                     _("Invalid sequential version tag {tag}.")
                                     .format(tag=branch_tag_ref.name),
                                     _("The code element of version {version_string} is not unique.")
                                     .format(version_string=version_string)
                                     )
                    else:
                        unique_codes.add(unique_code)

                    cli.fcwriteln(sys.stdout, status_color, "  code: " + version_string)

                # print the version tag
                version_string = context.parsed_config.version_tag_matcher.format(branch_tag_ref.name)
                if version_string:
                    version_info = semver.parse_version_info(version_string)
                    if version_info.major == branch_version.major and version_info.minor == branch_version.minor:
                        cli.fcwriteln(sys.stdout, status_color, "    " + version_string)
                    else:
                        result.error(os.EX_DATAERR,
                                     _("Invalid version tag {tag}.")
                                     .format(tag=repr(branch_tag_ref.name)),
                                     _("The major.minor part of the new version {new_version}"
                                       " does not match the branch version {branch_version}.")
                                     .format(new_version=repr(version_string),
                                             branch_version=repr(branch_version_string))
                                     )
                        cli.fcwriteln(sys.stdout, status_error_color, "    " + version_string)

    unique_version_codes.sort(key=utils.cmp_to_key(lambda a, b: version.cmp_alnum_token(a, b)))

    last_unique_code = None
    for unique_code in unique_version_codes:
        if not (last_unique_code is None or unique_code > last_unique_code):
            result.error(os.EX_DATAERR,
                         _("Version {version} breaks the sequence.")
                         .format(version=unique_code),
                         None
                         )
        last_unique_code = unique_code

    return result


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


def build(context):
    from urllib import parse
    import zipfile

    result = Result()

    context_result = get_command_context(
        context=context,
        object_arg=utils.get_or_default(context.args, '<object>', None)
    )
    result.add_subresult(context_result)
    command_context: CommandContext = context_result.value

    check_requirements(result_out=result,
                       command_context=command_context,
                       ref=command_context.selected_ref,
                       for_modification=True,
                       with_upstream=True,  # not context.parsed_config.push_to_local
                       in_sync_with_upstream=True,
                       fail_message=_("Build failed.")
                       )

    remote = repotools.git_get_remote(context.repo, context.parsed_config.remote_name)
    if remote is None:
        cli.fail(os.EX_CONFIG, "missing remote \"" + context.parsed_config.remote_name + "\"")

    # tempdir = TemporaryDirectory(prefix="gitflow_build_")
    # tempdir_path = tempdir.name
    tempdir_path = "/tmp/gitflow_build_XXXXXX"
    if not os.path.isdir(tempdir_path):
        os.makedirs(tempdir_path, mode=0o700)

    gradle_module_name = 'gradle-3.5.1'
    gradle_dist_url = 'https://services.gradle.org/distributions/' + gradle_module_name + '-bin.zip'
    gradle_dist_hash_sha256 = '8dce35f52d4c7b4a4946df73aa2830e76ba7148850753d8b5e94c5dc325ceef8'

    repo_url = parse.urlparse(remote.url)
    repo_dir_name = repo_url.path.rsplit('/', 1)[-1]

    build_repo_path = os.path.join(tempdir_path, repo_dir_name)
    gradle_dist_archive_path = os.path.join(tempdir_path, parse.urlparse(gradle_dist_url).path.rsplit('/', 1)[-1])

    gradle_dist_install_root = os.path.join(tempdir_path, 'buildtools')
    gradle_dist_install_path = os.path.join(gradle_dist_install_root, gradle_module_name)
    gradle_dist_bin_path = os.path.join(gradle_dist_install_path, 'bin')

    if os.path.exists(build_repo_path):
        shutil.rmtree(build_repo_path)

    repo = repotools.git_export(context.repo, build_repo_path, command_context.selected_ref)
    if repo is None:
        result.fail(os.EX_IOERR,
                    _("Failed to clone {remote}.")
                    .format(remote=repr(remote.url)),
                    None
                    )

    download_result = download_file(gradle_dist_url, gradle_dist_archive_path, gradle_dist_hash_sha256)
    result.add_subresult(download_result)

    if os.path.exists(gradle_dist_install_path):
        shutil.rmtree(gradle_dist_install_path)
    zip_ref = zipfile.ZipFile(gradle_dist_archive_path, 'r')
    zip_ref.extractall(gradle_dist_install_root)
    zip_ref.close()

    gradle_executable = os.path.join(gradle_dist_bin_path,
                                     "gradle.bat" if platform.system().lower() == "windows" else "gradle")

    st = os.stat(gradle_executable)
    os.chmod(gradle_executable, st.st_mode | 0o100)

    env = os.environ.copy()
    env['PATH'] += ':' + gradle_dist_bin_path

    gradle_command = [gradle_executable, '--no-daemon']
    if context.batch:
        gradle_command.append('--console=plain')
    if context.verbose:
        gradle_command.append('--info')
    gradle_command.append('app:assembleGenericDebug')

    gradle_process = subprocess.run(gradle_command,
                                    env=env,
                                    cwd=build_repo_path,
                                    # stdout=subprocess.PIPE,
                                    # stderr=subprocess.PIPE
                                    )
    # print(gradle_process.stdout)
    # print(gradle_process.stderr)


    return result
