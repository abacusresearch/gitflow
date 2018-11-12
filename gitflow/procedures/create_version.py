import json
import os
from typing import Callable, Union, Optional

import semver

from gitflow import utils, _, version, repotools, cli, const
from gitflow.common import Result
from gitflow.const import BranchClass
from gitflow.context import Context
from gitflow.procedures.common import get_command_context, check_requirements, get_branch_name_for_version, \
    fetch_all_and_ff, \
    CommandContext, create_sequence_number_for_version, \
    git_or_fail, get_tag_name_for_version, \
    CommitInfo, update_project_property_file, create_commit, prompt_for_confirmation, \
    check_in_repo, read_properties_in_commit, read_config_in_commit, get_global_sequence_number, \
    execute_version_change_actions, create_temp_context, clone_repository
from gitflow.procedures.scheme import scheme_procedures
from gitflow.repotools import BranchSelection, RepoContext
from gitflow.version import VersionConfig


def create_version_tag(command_context: CommandContext,
                       operation: Callable[[VersionConfig, Optional[str], Optional[int]], str]) -> Result:
    result = Result()
    context: Context = command_context.context

    # TODO configuration
    allow_merge_base_tags = True  # context.config.allow_shared_release_branch_base

    branch_base_version = context.release_branch_matcher.format(command_context.selected_ref.name)
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

    # fork_point = repotools.git_merge_base(context.repo, context.config.release_branch_base,
    #                                       command_context.selected_commit)
    # if fork_point is None:
    #     result.fail(os.EX_USAGE,
    #                 _("Cannot bump version."),
    #                 _("{branch} has no fork point on {base_branch}.")
    #                 .format(branch=repr(command_context.selected_ref.name),
    #                         base_branch=repr(context.config.release_branch_base)))
    fork_point = None

    # abort scan, when a preceding commit for each tag type has been processed.
    # enclosing_versions now holds enough information for operation validation,
    # assuming the branch has not gone haywire in earlier commits
    # TODO evaluate upper and lower bound version for efficiency
    abort_version_scan = False
    abort_sequential_version_scan = False

    before_commit = False
    for history_commit in repotools.git_list_commits(
            context=context.repo,
            start=fork_point,
            end=command_context.selected_ref,
            options=const.BRANCH_COMMIT_SCAN_OPTIONS):
        at_commit = history_commit.obj_name == command_context.selected_commit
        version_tag_refs = None

        assert not at_commit if before_commit else not before_commit

        for tag_ref in repotools.git_get_tags_by_referred_object(context.repo, history_commit.obj_name):
            version_info = context.version_tag_matcher.to_version_info(tag_ref.name)
            if version_info is not None:
                tag_matches = version_info.major == branch_base_version_info.major \
                              and version_info.minor == branch_base_version_info.minor

                if tag_matches:
                    if version_tag_refs is None:
                        version_tag_refs = list()
                    version_tag_refs.append(tag_ref)
                else:
                    if fork_point is not None:
                        # fail stray tags on exclusive branch commits
                        result.fail(os.EX_DATAERR,
                                    _("Cannot bump version."),
                                    _("Found stray version tag: {version}.")
                                    .format(version=repr(version.format_version_info(version_info)))
                                    )
                    else:
                        # when no merge base is used, abort at the first mismatching tag
                        abort_version_scan = True
                        abort_sequential_version_scan = True
                        break

        if not abort_version_scan and version_tag_refs is not None and len(version_tag_refs):
            version_tag_refs.sort(
                reverse=True,
                key=utils.cmp_to_key(
                    lambda tag_ref_a, tag_ref_b: semver.compare(
                        context.version_tag_matcher.format(tag_ref_a.name),
                        context.version_tag_matcher.format(tag_ref_b.name)
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
                enclosing_versions.add(context.version_tag_matcher.format(tag_ref.name))

            if before_commit:
                abort_version_scan = True

        if at_commit:
            before_commit = True

        if abort_version_scan and abort_sequential_version_scan:
            break

    if context.config.sequential_versioning and preceding_version_tag is not None:
        match = context.version_tag_matcher.fullmatch(preceding_version_tag.name)
        preceding_sequential_version = match.group(context.version_tag_matcher.group_unique_code)
    else:
        preceding_sequential_version = None
    if preceding_sequential_version is not None:
        preceding_sequential_version = int(preceding_sequential_version)

    if context.verbose:
        cli.print("Tags on selected commit:\n"
                  + '\n'.join(' - ' + repr(tag_ref.name) for tag_ref in version_tags_on_same_commit))

        cli.print("Tags in subsequent history:\n"
                  + '\n'.join(' - ' + repr(tag_ref.name) for tag_ref in subsequent_version_tags))

    if preceding_version_tag is not None:
        latest_branch_version = context.version_tag_matcher.format(preceding_version_tag.name)
    else:
        latest_branch_version = None

    if latest_branch_version is not None:
        version_result = operation(context.config.version_config, latest_branch_version,
                                   get_global_sequence_number(context))
        result.add_subresult(version_result)

        new_version = version_result.value
        if result.has_errors():
            return result
    else:
        template_version_info = semver.parse_version_info(context.config.version_config.initial_version)
        new_version = semver.format_version(
            major=branch_base_version_info.major,
            minor=branch_base_version_info.minor,

            patch=template_version_info.patch,
            prerelease=template_version_info.prerelease,
            build=template_version_info.build,
        )

    new_version_info = semver.parse_version_info(new_version)
    new_sequential_version = scheme_procedures.get_sequence_number(context.config.version_config, new_version_info)

    if new_version_info.major != branch_base_version_info.major or new_version_info.minor != branch_base_version_info.minor:
        result.fail(os.EX_USAGE,
                    _("Tag creation failed."),
                    _("The major.minor part of the new version {new_version}"
                      " does not match the branch version {branch_version}.")
                    .format(new_version=repr(new_version),
                            branch_version=repr(
                                "%d.%d" % (branch_base_version_info.major, branch_base_version_info.minor)))
                    )

    try:
        config_in_selected_commit = read_config_in_commit(context.repo, command_context.selected_commit)
    except FileNotFoundError:
        config_in_selected_commit = dict()

    try:
        properties_in_selected_commit = read_properties_in_commit(context,
                                                                  context.repo,
                                                                  config_in_selected_commit,
                                                                  command_context.selected_commit)
    except FileNotFoundError:
        properties_in_selected_commit = dict()

    if context.verbose:
        print("properties in selected commit:")
        print(json.dumps(obj=properties_in_selected_commit, indent=2))

    valid_tag = False

    # validate the commit
    if len(version_tags_on_same_commit):
        if config_in_selected_commit is None:
            result.fail(os.EX_DATAERR,
                        _("Tag creation failed."),
                        _("The selected commit does not contain a configuration file.")
                        )

        version_property_name = config_in_selected_commit.get(const.CONFIG_VERSION_PROPERTY)
        if version_property_name is not None \
                and properties_in_selected_commit.get(version_property_name) is None:
            result.warn(_("Missing version info."),
                        _("The selected commit does not contain a version in property '{property_name}'.")
                        .format(property_name=version_property_name)
                        )

    if len(version_tags_on_same_commit):
        if context.config.allow_qualifier_increments_within_commit:
            preceding_commit_version = context.version_tag_matcher.format(
                version_tags_on_same_commit[0].name)
            prerelease_keywords_list = [context.config.version_config.qualifiers, 1]

            preceding_commit_version_ = version.parse_version(preceding_commit_version)
            new_commit_version_ = version.parse_version(new_version)
            version_delta = version.determine_version_delta(preceding_commit_version_,
                                                            new_commit_version_,
                                                            prerelease_keywords_list
                                                            )

            version_increment_eval_result = version.evaluate_version_increment(preceding_commit_version_,
                                                                               new_commit_version_,
                                                                               context.config.strict_mode,
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

            valid_tag = True
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

    if not valid_tag:
        if len(subsequent_version_tags):
            result.fail(os.EX_USAGE,
                        _("Tag creation failed."),
                        _("There are version tags in branch history following the selected commit {commit}:\n"
                          "{listing}")
                        .format(commit=command_context.selected_commit,
                                listing='\n'.join(
                                    ' - ' + repr(tag_ref.name) for tag_ref in subsequent_version_tags))
                        )

    global_seq_number = get_global_sequence_number(context)
    if context.config.tie_sequential_version_to_semantic_version \
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

        if context.config.push_to_local \
                and command_context.current_branch.short_name == command_context.selected_ref.short_name:
            if context.verbose:
                cli.print(
                    _('Checking out {base_branch} in order to avoid failing the push to a checked-out release branch')
                        .format(base_branch=repr(context.config.release_branch_base)))

            git_or_fail(context.repo, result, ['checkout', context.config.release_branch_base])
            original_current_branch = command_context.current_branch
        else:
            original_current_branch = None

        branch_name = get_branch_name_for_version(context, new_version_info)
        tag_name = get_tag_name_for_version(context, new_version_info)

        clone_result = clone_repository(context, context.config.release_branch_base)
        cloned_repo = clone_result.value

        commit_info = CommitInfo()
        commit_info.add_message("#version: " + cli.if_none(new_version))

        # run version change hooks on release branch
        if (context.config.commit_version_property and new_version is not None) \
                or (context.config.commit_sequential_version_property and new_sequential_version is not None):
            checkout_command = ['checkout', '--force', '--track', '-b', branch_name,
                                repotools.create_ref_name(const.REMOTES_PREFIX,
                                                          context.config.remote_name,
                                                          branch_name)]

            returncode, out, err = repotools.git(cloned_repo, *checkout_command)
            if returncode != os.EX_OK:
                result.fail(os.EX_DATAERR,
                            _("Failed to check out release branch."),
                            _("An unexpected error occurred.")
                            )

            clone_context: Context = create_temp_context(context, result, cloned_repo.dir)
            clone_context.config.remote_name = 'origin'

            update_result = update_project_property_file(clone_context,
                                                         properties_in_selected_commit,
                                                         new_version,
                                                         new_sequential_version,
                                                         commit_info)
            result.add_subresult(update_result)
            if result.has_errors():
                result.fail(os.EX_DATAERR,
                            _("Property update failed."),
                            _("An unexpected error occurred.")
                            )
        else:
            clone_context: Context = create_temp_context(context, result, cloned_repo.dir)
            clone_context.config.remote_name = 'origin'

        if new_version is not None:
            execute_version_change_actions(clone_context, latest_branch_version, new_version)

        if commit_info is not None:
            if command_context.selected_commit != command_context.selected_ref.target.obj_name:
                result.fail(os.EX_USAGE,
                            _("Failed to commit version update."),
                            _("The selected parent commit {commit} does not represent the tip of {branch}.")
                            .format(commit=command_context.selected_commit,
                                    branch=repr(command_context.selected_ref.name))
                            )

            # commit changes
            commit_info.add_parent(command_context.selected_commit)
            object_to_tag = create_commit(clone_context, result, commit_info)
            new_branch_ref_object = object_to_tag
        else:
            object_to_tag = command_context.selected_commit
            new_branch_ref_object = None

        # if command_context.selected_branch not in repotools.git_list_refs(context.repo,
        #                                                                   '--contains', object_to_tag,
        #                                                                   command_context.selected_branch.ref):

        # show info and prompt for confirmation
        cli.print("ref                 : " + cli.if_none(command_context.selected_ref.name))
        cli.print("ref_" + const.DEFAULT_VERSION_VAR_NAME + "         : " + cli.if_none(latest_branch_version))
        cli.print("new_tag             : " + cli.if_none(tag_name))
        cli.print("new_" + const.DEFAULT_VERSION_VAR_NAME + "         : " + cli.if_none(new_version))
        cli.print("selected object     : " + cli.if_none(command_context.selected_commit))
        cli.print("tagged object       : " + cli.if_none(object_to_tag))

        prompt_result = prompt_for_confirmation(
            context=context,
            fail_title=_("Failed to create release tag based on {branch}.")
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
        push_command.append(context.config.remote_name)

        # push the release branch commit or its version increment commit
        if new_branch_ref_object is not None:
            push_command.append(
                new_branch_ref_object + ':' + repotools.create_ref_name(const.LOCAL_BRANCH_PREFIX, branch_name))

        # check, if preceding tags exist on remote
        if preceding_version_tag is not None:
            push_command.append('--force-with-lease='
                                + preceding_version_tag.name + ':'
                                + preceding_version_tag.name)

        # push the new version tag or fail if it exists
        push_command.extend(['--force-with-lease=' + repotools.create_ref_name(const.LOCAL_TAG_PREFIX, tag_name) + ':',
                             repotools.ref_target(object_to_tag) + ':' + repotools.create_ref_name(
                                 const.LOCAL_TAG_PREFIX, tag_name)])

        returncode, out, err = repotools.git(clone_context.repo, *push_command)
        if returncode != os.EX_OK:
            result.fail(os.EX_DATAERR,
                        _("Failed to push."),
                        _("git push exited with " + returncode)
                        )

        if original_current_branch is not None:
            if context.verbose:
                cli.print(
                    _('Switching back to {original_branch} ')
                        .format(original_branch=repr(original_current_branch.name)))

            git_or_fail(context.repo, result, ['checkout', original_current_branch.short_name])

    return result


def create_version_branch(command_context: CommandContext,
                          operation: Callable[[VersionConfig, Optional[str], Optional[int]], str]) -> Result:
    result = Result()
    context: Context = command_context.context

    if command_context.selected_ref.name not in [
        repotools.create_ref_name(const.LOCAL_BRANCH_PREFIX, context.config.release_branch_base),
        repotools.create_ref_name(const.REMOTES_PREFIX,
                                  context.config.remote_name,
                                  context.config.release_branch_base)]:
        result.fail(os.EX_USAGE,
                    _("Failed to create release branch based on {branch}.")
                    .format(branch=repr(command_context.selected_ref.name)),
                    _("Release branches (major.minor) can only be created off {branch}")
                    .format(branch=repr(context.config.release_branch_base))
                    )

    existing_release_branches = list(repotools.git_list_refs(context.repo, repotools.ref_name([
        const.REMOTES_PREFIX,
        context.config.remote_name,
        'release'])))

    release_branch_merge_bases = dict()
    for release_branch in context.get_release_branches():
        merge_base = repotools.git_merge_base(context.repo, context.config.release_branch_base, release_branch)
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

    for history_commit in repotools.git_list_commits(
            context=context.repo,
            start=None,
            end=command_context.selected_commit,
            options=const.BRANCH_COMMIT_SCAN_OPTIONS):
        branch_refs = release_branch_merge_bases.get(history_commit.obj_name)
        if branch_refs is not None and len(branch_refs):
            branch_refs = list(
                filter(lambda tag_ref: context.release_branch_matcher.format(tag_ref.name) is not None,
                       branch_refs))
            if not len(branch_refs):
                continue

            branch_refs.sort(
                reverse=True,
                key=utils.cmp_to_key(
                    lambda tag_ref_a, tag_ref_b: semver.compare(
                        context.release_branch_matcher.format(tag_ref_a.name),
                        context.release_branch_matcher.format(tag_ref_b.name)
                    )
                )
            )
            if latest_branch is None:
                latest_branch = branch_refs[0]
            if history_commit.obj_name == command_context.selected_commit:
                branch_points_on_same_commit.extend(branch_refs)
            # for tag_ref in tag_refs:
            #     print('<<' + tag_ref.name)
            break

    for history_commit in repotools.git_list_commits(context.repo,
                                                     command_context.selected_commit,
                                                     command_context.selected_ref):
        branch_refs = release_branch_merge_bases.get(history_commit.obj_name)
        if branch_refs is not None and len(branch_refs):
            branch_refs = list(
                filter(lambda tag_ref: context.release_branch_matcher.format(tag_ref.name) is not None,
                       branch_refs))
            if not len(branch_refs):
                continue

            branch_refs.sort(
                reverse=True,
                key=utils.cmp_to_key(
                    lambda tag_ref_a, tag_ref_b: semver.compare(
                        context.release_branch_matcher.format(tag_ref_a.name),
                        context.release_branch_matcher.format(tag_ref_b.name)
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
        latest_branch_version = context.release_branch_matcher.format(latest_branch.name)
        latest_branch_version_info = semver.parse_version_info(latest_branch_version)
    else:
        latest_branch_version = None
        latest_branch_version_info = None

    if latest_branch_version is not None:
        version_result = operation(context.config.version_config, latest_branch_version,
                                   get_global_sequence_number(context))
        result.add_subresult(version_result)

        new_version = version_result.value
        new_version_info = semver.parse_version_info(new_version)
    else:
        new_version_info = semver.parse_version_info(context.config.version_config.initial_version)
        new_version = version.format_version_info(new_version_info)

    scheme_procedures.get_sequence_number(context.config.version_config, new_version_info)

    if context.config.sequential_versioning:
        new_sequential_version = create_sequence_number_for_version(context, new_version)
    else:
        new_sequential_version = None

    try:
        config_in_selected_commit = read_config_in_commit(context.repo, command_context.selected_commit)
    except FileNotFoundError:
        config_in_selected_commit = dict()

    try:
        properties_in_selected_commit = read_properties_in_commit(context,
                                                                  context.repo,
                                                                  config_in_selected_commit,
                                                                  command_context.selected_commit)
    except FileNotFoundError:
        properties_in_selected_commit = dict()

    if not context.config.allow_shared_release_branch_base and len(branch_points_on_same_commit):
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

    if context.config.tie_sequential_version_to_semantic_version \
            and len(existing_release_branches):
        prompt_result = prompt_for_confirmation(
            context=context,
            fail_title=_("Failed to create release branch based on {branch}.")
                .format(branch=repr(command_context.selected_ref.name)),
            message=_("This operation disables version increments "
                      "on all existing release branches.\n"
                      "Affected branches are:\n"
                      "{listing}")
                .format(listing=os.linesep.join(repr(branch.name) for branch in existing_release_branches))
            if not context.config.commit_version_property
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

        clone_result = clone_repository(context, context.config.release_branch_base)
        cloned_repo: RepoContext = clone_result.value

        # run version change hooks on new release branch
        git_or_fail(cloned_repo, result, ['checkout', '--force',
                                          '-b', branch_name,
                                          command_context.selected_commit],
                    _("Failed to check out release branch."))

        clone_context: Context = create_temp_context(context, result, cloned_repo.dir)
        clone_context.config.remote_name = 'origin'

        commit_info = CommitInfo()
        commit_info.add_message("#version: " + cli.if_none(new_version))

        if (context.config.commit_version_property and new_version is not None) \
                or (context.config.commit_sequential_version_property and new_sequential_version is not None):

            update_result = update_project_property_file(clone_context,
                                                         properties_in_selected_commit,
                                                         new_version,
                                                         new_sequential_version,
                                                         commit_info)
            result.add_subresult(update_result)
            if result.has_errors():
                result.fail(os.EX_DATAERR,
                            _("Property update failed."),
                            _("An unexpected error occurred.")
                            )

        if new_version is not None:
            execute_version_change_actions(clone_context, latest_branch_version, new_version)

        if commit_info is not None:
            if command_context.selected_commit != command_context.selected_ref.target.obj_name:
                result.fail(os.EX_USAGE,
                            _("Failed to commit version update."),
                            _("The selected parent commit {commit} does not represent the tip of {branch}.")
                            .format(commit=command_context.selected_commit,
                                    branch=repr(command_context.selected_ref.name))
                            )

            # commit changes
            commit_info.add_parent(command_context.selected_commit)
            object_to_tag = create_commit(clone_context, result, commit_info)
        else:
            object_to_tag = command_context.selected_commit

        # show info and prompt for confirmation
        cli.print("ref                 : " + cli.if_none(command_context.selected_ref.name))
        cli.print("ref_" + const.DEFAULT_VERSION_VAR_NAME + "         : " + cli.if_none(latest_branch_version))
        cli.print("new_branch          : " + cli.if_none(branch_name))
        cli.print("new_" + const.DEFAULT_VERSION_VAR_NAME + "         : " + cli.if_none(new_version))
        cli.print("selected object     : " + cli.if_none(command_context.selected_commit))
        cli.print("tagged object       : " + cli.if_none(object_to_tag))

        prompt_result = prompt_for_confirmation(
            context=context,
            fail_title=_("Failed to create release branch based on {branch}.")
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
        push_command.append(context.config.remote_name)

        # push the base branch commit
        # push_command.append(commit + ':' + const.LOCAL_BRANCH_PREFIX + selected_ref.local_branch_name)

        # push the new branch or fail if it exists
        push_command.extend(
            ['--force-with-lease=' + repotools.create_ref_name(const.LOCAL_BRANCH_PREFIX, branch_name) + ':',
             repotools.ref_target(object_to_tag) + ':' + repotools.create_ref_name(const.LOCAL_BRANCH_PREFIX,
                                                                                   branch_name)])
        # push the new version tag or fail if it exists
        push_command.extend(['--force-with-lease=' + repotools.create_ref_name(const.LOCAL_TAG_PREFIX, tag_name) + ':',
                             repotools.ref_target(object_to_tag) + ':' + repotools.create_ref_name(
                                 const.LOCAL_TAG_PREFIX, tag_name)])

        git_or_fail(cloned_repo, result, push_command, _("Failed to push."))

    return result


def call(context: Context, operation: Callable[[VersionConfig, str], Union[str, None]]) -> Result:
    command_context = get_command_context(
        context=context,
        object_arg=context.args['<object>']
    )

    check_in_repo(command_context)

    # determine the type of operation to be performed and run according subroutines
    if operation == scheme_procedures.version_bump_major \
            or operation == scheme_procedures.version_bump_minor:

        check_requirements(command_context=command_context,
                           ref=command_context.selected_ref,
                           branch_classes=[BranchClass.DEVELOPMENT_BASE],
                           modifiable=True,
                           with_upstream=True,  # not context.config.push_to_local
                           in_sync_with_upstream=True,
                           fail_message=_("Version creation failed.")
                           )

        tag_result = create_version_branch(command_context, operation)
        command_context.add_subresult(tag_result)

    elif operation == scheme_procedures.version_bump_patch \
            or operation == scheme_procedures.version_bump_qualifier \
            or operation == scheme_procedures.version_bump_prerelease \
            or operation == scheme_procedures.version_bump_to_release:

        check_requirements(command_context=command_context,
                           ref=command_context.selected_ref,
                           branch_classes=[BranchClass.RELEASE],
                           modifiable=True,
                           with_upstream=True,  # not context.config.push_to_local
                           in_sync_with_upstream=True,
                           fail_message=_("Version creation failed.")
                           )

        tag_result = create_version_tag(command_context, operation)
        command_context.add_subresult(tag_result)

    elif isinstance(operation, scheme_procedures.version_set):
        check_requirements(command_context=command_context,
                           ref=command_context.selected_ref,
                           branch_classes=None,
                           modifiable=True,
                           with_upstream=True,  # not context.config.push_to_local
                           in_sync_with_upstream=True,
                           fail_message=_("Version creation failed.")
                           )

        version_result = operation(context.config.version_config, None, get_global_sequence_number(context))
        command_context.add_subresult(version_result)
        new_version = version_result.value
        if new_version is None:
            command_context.fail(os.EX_USAGE,
                                 _("Illegal argument."),
                                 _("Failed to parse version.")
                                 )
        new_version_info = semver.parse_version_info(new_version)

        branch_name = get_branch_name_for_version(context, new_version_info)

        release_branch = repotools.get_branch_by_name(context.repo, {context.config.remote_name}, branch_name,
                                                      BranchSelection.BRANCH_PREFER_LOCAL)
        if release_branch is None:
            tag_result = create_version_branch(command_context, operation)
            command_context.add_subresult(tag_result)
        else:
            selected_ref = release_branch
            tag_result = create_version_tag(command_context, operation)
            command_context.add_subresult(tag_result)

    if not command_context.has_errors() \
            and context.config.pull_after_bump \
            and not context.config.push_to_local:
        fetch_all_and_ff(context.repo, command_context.result, context.config.remote_name)

    return context.result
