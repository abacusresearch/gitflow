import sys

from gitflow import _, cli, repotools
from gitflow.common import Result
from gitflow.context import Context
from gitflow.procedures import common


def pre_commit(context: Context) -> Result:
    result = Result()

    command_context = common.get_command_context(
        context=context,
        object_arg='HEAD'
    )

    target_ref = repotools.git_get_current_branch(context.repo)

    common.check_requirements(command_context=command_context,
                              ref=target_ref,
                              modifiable=True,
                              with_upstream=False,
                              in_sync_with_upstream=False,
                              fail_message=_("Commit rejected."),
                              throw=False
                              )

    return result


def pre_push(context: Context) -> Result:
    result = Result()

    for line in sys.stdin.readlines():
        tokens = line.split(' ')
        if len(tokens) != 4:
            raise ValueError()
        cli.print(line)

        local_ref = tokens[0]
        local_sha1 = tokens[1]
        remote_ref = tokens[2]
        remote_sha1 = tokens[3]

        command_context = common.get_command_context(
            context=context,
            object_arg=remote_ref
        )

        common.check_requirements(command_context=command_context,
                                  ref=command_context.selected_ref,
                                  modifiable=True,
                                  with_upstream=False,
                                  in_sync_with_upstream=False,
                                  fail_message=_("Push rejected."),
                                  throw=False
                                  )

    return result
