import os

import semver

from gitflow import utils, _, const, repotools, cli
from gitflow.common import Result
from gitflow.const import BranchClass
from gitflow.context import Context
from gitflow.procedures.common import get_command_context, check_requirements, WorkBranch, get_branch_info, \
    select_ref, git, git_or_fail, check_in_repo
from gitflow.repotools import BranchSelection


def call(context: Context) -> Result:
    arg_work_branch = context.args.get('<work-branch>')
    if arg_work_branch is None:
        branch_prefix = context.args['<supertype>']
        branch_type = context.args['<type>']
        branch_name = context.args['<name>']

        if branch_prefix is not None or branch_type is not None or branch_name is not None:
            arg_work_branch = repotools.create_ref_name(branch_prefix, branch_type, branch_name)

    command_context = get_command_context(
        context=context,
        object_arg=arg_work_branch
    )

    check_in_repo(command_context)

    base_command_context = get_command_context(
        context=context,
        object_arg=context.args['<base-object>']
    )

    check_requirements(command_context=command_context,
                       ref=command_context.selected_ref,
                       branch_classes=[BranchClass.WORK_DEV, BranchClass.WORK_PROD],
                       modifiable=True,
                       with_upstream=True,  # not context.config.push_to_local
                       in_sync_with_upstream=True,
                       fail_message=_("Version creation failed.")
                       )

    work_branch = None
    selected_ref_match = context.work_branch_matcher.fullmatch(command_context.selected_ref.name)
    if selected_ref_match is not None:
        work_branch = WorkBranch()
        work_branch.prefix = selected_ref_match.group('prefix')
        work_branch.type = selected_ref_match.group('type')
        work_branch.name = selected_ref_match.group('name')
    else:
        if command_context.selected_explicitly:
            context.fail(os.EX_USAGE,
                         _("The ref {branch} does not refer to a work branch.")
                         .format(branch=repr(command_context.selected_ref.name)),
                         None)

    work_branch_info = get_branch_info(command_context, work_branch.local_ref_name())
    if work_branch_info is None:
        context.fail(os.EX_USAGE,
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
            base_branch_info = get_branch_info(base_command_context,
                                               repotools.create_ref_name(const.LOCAL_BRANCH_PREFIX,
                                                                         context.config.release_branch_base))
            base_branch_ref, base_branch_class = select_ref(command_context.result,
                                                            base_branch_info,
                                                            BranchSelection.BRANCH_PREFER_LOCAL)
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
        context.fail(os.EX_USAGE,
                     _("The branch {branch} is not a valid base for {supertype} branches.")
                     .format(branch=repr(base_branch_ref.name),
                             supertype=repr(work_branch.prefix)),
                     None)

    if base_branch_ref is None:
        context.fail(os.EX_USAGE,
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
        return context.result

    # check for staged changes
    index_status = git(context, ['diff-index', 'HEAD', '--'])
    if index_status == 1:
        context.fail(os.EX_USAGE,
                     _("Branch creation aborted."),
                     _("You have staged changes in your workspace.\n"
                       "Unstage, commit or stash them and try again."))
    elif index_status != 0:
        context.fail(os.EX_DATAERR,
                     _("Failed to determine index status."),
                     None)

    if not context.dry_run and not command_context.has_errors():
        # perform merge
        local_branch_ref_name = repotools.create_local_branch_ref_name(base_branch_ref.name)
        local_branch_name = repotools.create_local_branch_name(base_branch_ref.name)
        if local_branch_ref_name == base_branch_ref.name:
            git_or_fail(context, command_context.result,
                        ['checkout', local_branch_name],
                        _("Failed to checkout branch {branch_name}.")
                        .format(branch_name=repr(base_branch_ref.short_name))
                        )
        else:
            git_or_fail(context, command_context.result,
                        ['checkout', '-b', local_branch_name, base_branch_ref.name],
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
                    ['push', context.config.remote_name, local_branch_name],
                    _("Failed to push branch {branch_name}.")
                    .format(branch_name=repr(base_branch_ref.short_name))
                    )

    return context.result
