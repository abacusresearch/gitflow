import os
from typing import Callable

import semver

from gitflow import utils, _, version, repotools, cli, const
from gitflow.common import Result
from gitflow.context import Context
from gitflow.procedures import get_command_context, check_requirements, get_branch_name_for_version, fetch_all_and_ff, \
    CommandContext, create_sequence_number_for_version, \
    create_sequential_version_tag_name, get_global_sequence_number, git_or_fail, get_tag_name_for_version, \
    create_shared_clone_repository, CommitInfo, update_project_property_file, create_commit, prompt_for_confirmation
from gitflow.repotools import BranchSelection
from gitflow.version import VersionConfig


def create_version_tag(command_context: CommandContext, operation: Callable[[VersionConfig, str], str]) -> Result:
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

    preceding_sequential_version_tag = None
    sequential_version_tags_on_same_commit = list()
    subsequent_sequential_version_tags = list()

    # merge_base = context.config.release_branch_base
    merge_base = repotools.git_merge_base(context.repo, context.config.release_branch_base,
                                          command_context.selected_commit)
    if merge_base is None:
        result.fail(os.EX_USAGE,
                    _("Cannot bump version."),
                    _("{branch} has no merge base with {base_branch}.")
                    .format(branch=repr(command_context.selected_ref.name),
                            base_branch=repr(context.config.release_branch_base)))

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
            version_info = context.version_tag_matcher.to_version_info(tag_ref.name)
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

            match = context.sequential_version_tag_matcher.fullmatch(tag_ref.name)
            if match is not None:
                if sequential_version_tag_refs is None:
                    sequential_version_tag_refs = list()
                sequential_version_tag_refs.append(tag_ref)

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

        if not abort_sequential_version_scan and sequential_version_tag_refs is not None and len(
                sequential_version_tag_refs):
            sequential_version_tag_refs.sort(
                reverse=True,
                key=utils.cmp_to_key(
                    lambda tag_ref_a, tag_ref_b: version.cmp_alnum_token(
                        context.sequential_version_tag_matcher.format(tag_ref_a.name),
                        context.sequential_version_tag_matcher.format(tag_ref_b.name)
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

    preceding_version = context.version_tag_matcher.format(
        preceding_version_tag.name) if preceding_version_tag is not None else None

    preceding_sequential_version = context.sequential_version_tag_matcher.format(
        preceding_sequential_version_tag.name) if preceding_sequential_version_tag is not None else None
    if preceding_sequential_version is not None:
        preceding_sequential_version = int(preceding_sequential_version)

    if context.verbose:
        cli.print("Tags on selected commit:\n"
                  + '\n'.join(' - ' + repr(tag_ref.name) for tag_ref in version_tags_on_same_commit))

        cli.print("Tags in subsequent history:\n"
                  + '\n'.join(' - ' + repr(tag_ref.name) for tag_ref in subsequent_version_tags))

    if preceding_version_tag is not None:
        latest_branch_version = context.version_tag_matcher.format(preceding_version_tag.name)
        latest_branch_version_info = semver.parse_version_info(latest_branch_version)
    else:
        latest_branch_version = None
        latest_branch_version_info = None

    if latest_branch_version is not None:
        version_result = operation(context.config.version_config, latest_branch_version)
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

    if context.config.sequential_versioning \
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

            git_or_fail(context, result, ['checkout', context.config.release_branch_base])
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
        if (context.config.commit_version_property and new_version is not None) \
                or (
                            context.config.commit_sequential_version_property and new_sequential_version is not None):
            if command_context.selected_commit != command_context.selected_ref.target.obj_name:
                result.fail(os.EX_DATAERR,
                            _("Failed to commit version update."),
                            _("The selected commit {commit} does not represent the tip of {branch}.")
                            .format(commit=command_context.selected_commit,
                                    branch=repr(command_context.selected_ref.name))
                            )

            checkout_command = ['checkout', '--force', '--track', '-b', branch_name,
                                repotools.create_ref_name(const.REMOTES_PREFIX,
                                                          context.config.remote_name,
                                                          branch_name)]

            proc = repotools.git(clone_context.repo, *checkout_command)
            proc.wait()
            if proc.returncode != os.EX_OK:
                result.fail(os.EX_DATAERR,
                            _("Failed to check out release branch."),
                            _("An unexpected error occurred.")
                            )

            commit_info = CommitInfo()
            commit_info.add_parent(command_context.selected_commit)
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
            object_to_tag = create_commit(clone_context, result, commit_info)
        else:
            object_to_tag = command_context.selected_commit

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
        push_command.append(
            repotools.ref_target(object_to_tag) + ':' + repotools.create_ref_name(const.LOCAL_BRANCH_PREFIX,
                                                                                  branch_name))
        # push the new version tag or fail if it exists
        push_command.extend(['--force-with-lease=' + repotools.create_ref_name(const.LOCAL_TAG_PREFIX, tag_name) + ':',
                             repotools.ref_target(object_to_tag) + ':' + repotools.create_ref_name(
                                 const.LOCAL_TAG_PREFIX, tag_name)])
        # push the new sequential version tag or fail if it exists
        if sequential_version_tag_name is not None:
            push_command.extend(['--force-with-lease=' + repotools.create_ref_name(const.LOCAL_TAG_PREFIX,
                                                                                   sequential_version_tag_name) + ':',
                                 repotools.ref_target(
                                     object_to_tag) + ':' + repotools.create_ref_name(const.LOCAL_TAG_PREFIX,
                                                                                      sequential_version_tag_name)])

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


def create_version_branch(command_context: CommandContext, operation: Callable[[VersionConfig, str], str]) -> Result:
    result = Result()
    context: Context = command_context.context

    if not command_context.selected_ref.name in [
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

    for history_commit in repotools.git_list_commits(context.repo, None, command_context.selected_commit):
        branch_refs = release_branch_merge_bases.get(history_commit)
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
        version_result = operation(context.config.version_config, latest_branch_version)
        result.add_subresult(version_result)

        new_version = version_result.value
        new_version_info = semver.parse_version_info(new_version)
    else:
        new_version_info = semver.parse_version_info(const.DEFAULT_INITIAL_VERSION)
        new_version = version.format_version_info(new_version_info)

    if context.config.sequential_versioning:
        new_sequential_version = create_sequence_number_for_version(context, new_version)
        sequential_version_tag_name = create_sequential_version_tag_name(context, new_sequential_version)
    else:
        new_sequential_version = None
        sequential_version_tag_name = None

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
            fail_title=_("Failed to create release branch based on {branch} in batch mode.")
                .format(branch=repr(command_context.selected_ref.name)),
            message=_("This operation disables version increments except for pre-release increments "
                      "on all existing branches.\n"
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

        clone_result = create_shared_clone_repository(context)
        result.add_subresult(clone_result)
        if result.has_errors():
            return result

        clone_context = clone_result.value

        has_local_commit = False

        if (context.config.commit_version_property and new_version is not None) \
                or (
                            context.config.commit_sequential_version_property and new_sequential_version is not None):
            # if commit != selected_ref.target.obj_name:
            #     result.fail(os.EX_DATAERR,
            #                 _("Failed to commit version update."),
            #                 _("The selected commit {commit} does not represent the tip of {branch}.")
            #                 .format(commit=commit, branch=repr(selected_ref.name))
            #                 )

            # run version change hooks on new release branch
            git_or_fail(clone_context, result, ['checkout', '--force',
                                                '-b', branch_name,
                                                command_context.selected_commit],
                        _("Failed to check out release branch."))

            commit_info = CommitInfo()
            commit_info.add_parent(command_context.selected_commit)
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
            object_to_tag = create_commit(clone_context, result, commit_info)
        else:
            object_to_tag = command_context.selected_commit

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
        # push the new sequential version tag or fail if it exists
        if sequential_version_tag_name is not None:
            push_command.extend(['--force-with-lease=' + repotools.create_ref_name(const.LOCAL_TAG_PREFIX,
                                                                                   sequential_version_tag_name) + ':',
                                 repotools.ref_target(object_to_tag) + ':' + repotools.create_ref_name(
                                     const.LOCAL_TAG_PREFIX, sequential_version_tag_name)])

        git_or_fail(clone_context, result, push_command, _("Failed to push."))

    return result


def call(context: Context, operation: Callable[[VersionConfig, str], str]) -> Result:
    command_context = get_command_context(
        context=context,
        object_arg=utils.get_or_default(context.args, '<object>', None)
    )

    check_requirements(command_context=command_context,
                       ref=command_context.selected_ref,
                       modifiable=True,
                       with_upstream=True,  # not context.config.push_to_local
                       in_sync_with_upstream=True,
                       fail_message=_("Version creation failed.")
                       )

    # determine the type of operation to be performed and run according subroutines
    if operation == version.version_bump_major \
            or operation == version.version_bump_minor:

        tag_result = create_version_branch(command_context, operation)
        command_context.add_subresult(tag_result)

    elif operation == version.version_bump_patch \
            or operation == version.version_bump_qualifier \
            or operation == version.version_bump_prerelease \
            or operation == version.version_bump_to_release:

        tag_result = create_version_tag(command_context, operation)
        command_context.add_subresult(tag_result)

    elif isinstance(operation, version.version_set):

        version_result = operation(context.config.version_config, None)
        command_context.add_subresult(version_result)
        new_version = version_result.value
        if new_version is None:
            command_context.fail(os.EX_USAGE,
                                 _("Illegal argument."),
                                 _("Failed to parse version.")
                                 )
        new_version_info = semver.parse_version_info(new_version)

        branch_name = get_branch_name_for_version(context, new_version_info)

        release_branch = repotools.get_branch_by_name(context.repo, branch_name, BranchSelection.BRANCH_PREFER_LOCAL)
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
        fetch_all_and_ff(context, command_context.result, context.config.remote_name)

    return command_context.result