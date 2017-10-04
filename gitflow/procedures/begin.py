import os

from gitflow import utils, _, const, repotools, cli
from gitflow.common import Result
from gitflow.context import Context
from gitflow.procedures.common import get_command_context, check_requirements, get_branch_class, get_branch_info, \
    select_ref, \
    git, git_or_fail, check_in_repo
from gitflow.repotools import BranchSelection


def call(context: Context) -> Result:
    command_context = get_command_context(
        context=context,
        object_arg=context.args['<base-object>']
    )

    check_in_repo(command_context)

    check_requirements(command_context=command_context,
                       ref=command_context.selected_ref,
                       branch_classes=None,
                       modifiable=True,
                       with_upstream=True,  # not context.config.push_to_local
                       in_sync_with_upstream=True,
                       fail_message=_("Version creation failed.")
                       )

    selected_work_branch = context.args.get('<work-branch>')
    if selected_work_branch is not None:
        selected_work_branch = repotools.create_ref_name(selected_work_branch)
        if not selected_work_branch.startswith(const.LOCAL_BRANCH_PREFIX):
            selected_work_branch = const.LOCAL_BRANCH_PREFIX + selected_work_branch
        branch_match = context.work_branch_matcher.fullmatch(selected_work_branch)
        if branch_match is None:
            command_context.fail(os.EX_USAGE,
                                 _("Invalid work branch: {branch}.")
                                 .format(branch=repr(selected_work_branch)),
                                 None)
        groups = branch_match.groupdict()

        branch_supertype = groups['prefix']
        branch_type = groups['type']
        branch_short_name = groups['name']
    else:
        branch_supertype = context.args['<supertype>']
        branch_type = context.args['<type>']
        branch_short_name = context.args['<name>']

    if branch_supertype not in [const.BRANCH_PREFIX_DEV, const.BRANCH_PREFIX_PROD]:
        command_context.fail(os.EX_USAGE,
                             _("Invalid branch super type: {supertype}.")
                             .format(supertype=repr(branch_supertype)),
                             None)

    work_branch_name = repotools.create_ref_name(branch_supertype, branch_type, branch_short_name)
    work_branch_ref_name = repotools.create_ref_name(const.LOCAL_BRANCH_PREFIX, work_branch_name)
    work_branch_class = get_branch_class(context, work_branch_ref_name)

    if True:
        work_branch_info = get_branch_info(command_context, work_branch_ref_name)
        if work_branch_info is not None:
            command_context.fail(os.EX_USAGE,
                                 _("The branch {branch} already exists locally or remotely.")
                                 .format(branch=repr(work_branch_name)),
                                 None)

    allowed_base_branch_class = const.BRANCHING[work_branch_class]

    base_branch, base_branch_class = select_ref(command_context.result, command_context.selected_branch,
                                                BranchSelection.BRANCH_PREFER_LOCAL)
    if not command_context.selected_explicitly and branch_supertype == const.BRANCH_PREFIX_DEV:
        base_branch_info = get_branch_info(command_context,
                                                 repotools.create_ref_name(const.LOCAL_BRANCH_PREFIX,
                                                                           context.config.release_branch_base))
        base_branch, base_branch_class = select_ref(command_context.result,
                                                    base_branch_info,
                                                                       BranchSelection.BRANCH_PREFER_LOCAL)

    if allowed_base_branch_class != base_branch_class:
        command_context.fail(os.EX_USAGE,
                             _("The branch {branch} is not a valid base for {supertype} branches.")
                             .format(branch=repr(base_branch.name),
                                     supertype=repr(branch_supertype)),
                             None)

    if base_branch is None:
        command_context.fail(os.EX_USAGE,
                             _("Base branch undetermined."),
                             None)

    if context.verbose:
        cli.print("branch_name: " + command_context.selected_ref.name)
        cli.print("work_branch_name: " + work_branch_name)
        cli.print("base_branch_name: " + base_branch.name)

    if not context.dry_run and not command_context.has_errors():
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

        git_or_fail(context, command_context.result,
                    ['update-ref', work_branch_ref_name, command_context.selected_commit, ''],
                    _("Failed to create branch {branch_name}.")
                    .format(branch_name=work_branch_name)
                    )
        git_or_fail(context, command_context.result,
                    ['checkout', work_branch_name],
                    _("Failed to checkout branch {branch_name}.")
                    .format(branch_name=work_branch_name)
                    )

    return command_context.result
