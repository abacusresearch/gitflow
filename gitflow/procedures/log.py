import os

from gitflow import _, repotools
from gitflow.common import Result
from gitflow.context import Context
from gitflow.procedures.common import get_branch_by_branch_name_or_version_tag, get_command_context, check_in_repo
from gitflow.repotools import BranchSelection


def call(context: Context) -> Result:
    command_context = get_command_context(
        context=context,
        object_arg=context.args['<work-branch>']
    )

    check_in_repo(command_context)

    object_arg = context.args['<object>']
    args = context.args['<git-arg>']

    if object_arg is not None:
        selected_branch = get_branch_by_branch_name_or_version_tag(context, object_arg,
                                                                   BranchSelection.BRANCH_PREFER_LOCAL)
        if selected_branch is None:
            command_context.fail(os.EX_USAGE,
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

    return context.result
