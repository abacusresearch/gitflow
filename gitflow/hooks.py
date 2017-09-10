import sys

from gitflow import procedures, _, cli, repotools
from gitflow.common import Result
from gitflow.context import Context


def pre_commit(context: Context) -> Result:
    result = Result()

    context_result = procedures.get_command_context(
        context=context,
        object_arg='HEAD'
    )
    result.add_subresult(context_result)
    command_context = context_result.value

    target_ref = repotools.git_get_current_branch(context.repo)

    procedures.check_requirements(result_out=result,
                                  command_context=command_context,
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

        context_result = procedures.get_command_context(
            context=context,
            object_arg=remote_ref
        )
        result.add_subresult(context_result)
        command_context = context_result.value

        procedures.check_requirements(result_out=result,
                                      command_context=command_context,
                                      ref=command_context.selected_ref,
                                      modifiable=True,
                                      with_upstream=False,
                                      in_sync_with_upstream=False,
                                      fail_message=_("Push rejected."),
                                      throw=False
                                      )

    return result
