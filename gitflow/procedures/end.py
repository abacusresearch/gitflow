import os

import semver

from gitflow import utils, _, const, repotools, cli
from gitflow.common import Result
from gitflow.context import Context
from gitflow.procedures import get_command_context, check_requirements, WorkBranch, get_branch_info, select_ref, git, \
    git_or_fail
from gitflow.repotools import BranchSelection


def call(context: Context) -> Result:
    command_context = get_command_context(
        context=context,
        object_arg=utils.get_or_default(context.args, '<work-branch>', None)
    )

    base_command_context = get_command_context(
        context=context,
        object_arg=utils.get_or_default(context.args, '<base-branch>', None)
    )

    check_requirements(command_context=command_context,
                       ref=command_context.selected_ref,
                       modifiable=True,
                       with_upstream=True,  # not context.config.push_to_local
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
            command_context.fail(os.EX_USAGE,
                        _("Invalid branch super type: {supertype}.")
                        .format(supertype=repr(arg_work_branch.prefix)),
                        None)

    else:
        arg_work_branch = None

    ref_work_branch = WorkBranch()
    selected_ref_match = context.work_branch_matcher.fullmatch(command_context.selected_ref.name)
    if selected_ref_match is not None:
        ref_work_branch.prefix = selected_ref_match.group('prefix')
        ref_work_branch.type = selected_ref_match.group('type')
        ref_work_branch.name = selected_ref_match.group('name')
    else:
        ref_work_branch = None

        if command_context.selected_explicitly:
            command_context.fail(os.EX_USAGE,
                        _("The ref {branch} does not refer to a work branch.")
                        .format(branch=repr(command_context.selected_ref.name)),
                        None)

    work_branch = ref_work_branch or arg_work_branch

    work_branch_info = get_branch_info(command_context, work_branch.local_ref_name())
    if work_branch_info is None:
        command_context.fail(os.EX_USAGE,
                    _("The branch {branch} does neither exist locally nor remotely.")
                    .format(branch=repr(work_branch.branch_name())),
                    None)

    work_branch_ref, work_branch_class = select_ref(command_context.result,
                                                    work_branch_info,
                                                    BranchSelection.BRANCH_PREFER_LOCAL)

    allowed_base_branch_class = const.BRANCHING[work_branch_class]

    base_branch_info = get_branch_info(base_command_context,
                                       base_command_context.selected_ref)

    base_branch_ref, base_branch_class = select_ref(command_context.result,
                                                    base_branch_info,
                                                    BranchSelection.BRANCH_PREFER_LOCAL)
    if not base_command_context.selected_explicitly:
        if work_branch.prefix == const.BRANCH_PREFIX_DEV:
            fixed_base_branch_info = get_branch_info(base_command_context,
                                                     repotools.create_ref_name(const.LOCAL_BRANCH_PREFIX,
                                                                               context.config.release_branch_base))
            fixed_base_branch, fixed_destination_branch_class = select_ref(command_context.result,
                                                                           fixed_base_branch_info,
                                                                           BranchSelection.BRANCH_PREFER_LOCAL)

            base_branch_ref, base_branch_class = fixed_base_branch, fixed_destination_branch_class
        elif work_branch.prefix == const.BRANCH_PREFIX_PROD:
            # discover closest merge base in release branches

            release_branches = repotools.git_list_refs(context.repo,
                                                       repotools.create_ref_name(const.REMOTES_PREFIX,
                                                                                 context.config.remote_name,
                                                                                 'release'))
            release_branches = list(release_branches)
            release_branches.sort(reverse=True, key=utils.cmp_to_key(lambda ref_a, ref_b: semver.compare(
                context.release_branch_matcher.format(ref_a.name),
                context.release_branch_matcher.format(ref_b.name)
            )))
            for release_branch_ref in release_branches:
                merge_base = repotools.git_merge_base(context.repo, base_branch_ref, work_branch_ref.name)
                if merge_base is not None:
                    base_branch_info = get_branch_info(base_command_context, release_branch_ref)

                    base_branch_ref, base_branch_class = select_ref(command_context.result,
                                                                    base_branch_info,
                                                                    BranchSelection.BRANCH_PREFER_LOCAL)
                    break

    if allowed_base_branch_class != base_branch_class:
        command_context.fail(os.EX_USAGE,
                    _("The branch {branch} is not a valid base for {supertype} branches.")
                    .format(branch=repr(base_branch_ref.name),
                            supertype=repr(work_branch.prefix)),
                    None)

    if base_branch_ref is None:
        command_context.fail(os.EX_USAGE,
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
        return command_context.result

    # check for staged changes
    index_status = git(context, ['diff-index', 'HEAD', '--'])
    if index_status == 1:
        command_context.fail(os.EX_USAGE,
                    _("Branch creation aborted."),
                    _("You have staged changes in your workspace.\n"
                      "Unstage, commit or stash them and try again."))
    elif index_status != 0:
        command_context.fail(os.EX_DATAERR,
                    _("Failed to determine index status."),
                    None)

    if not context.dry_run and not command_context.has_errors():
        # run merge
        git_or_fail(context, command_context.result,
                    ['checkout', base_branch_ref.short_name],
                    _("Failed to checkout branch {branch_name}.")
                    .format(branch_name=repr(base_branch_ref.short_name))
                    )

        git_or_fail(context, command_context.result,
                    ['merge', '--no-ff', work_branch_ref],
                    _("Failed to merge work branch.\n"
                      "Rebase {work_branch} on {base_branch} and try again")
                    .format(work_branch=repr(work_branch_ref.short_name),
                            base_branch=repr(base_branch_ref.short_name))
                    )

        git_or_fail(context, command_context.result,
                    ['push', context.config.remote_name, base_branch_ref.short_name],
                    _("Failed to push branch {branch_name}.")
                    .format(branch_name=repr(base_branch_ref.short_name))
                    )

    return command_context.result