from gitflow import procedures, utils, _
from gitflow.common import Result
from gitflow.context import Context


def pre_commit(context: Context) -> Result:
    result = Result()

    context_result = procedures.get_command_context(
        context=context,
        object_arg=utils.get_or_default(context.args, 'HEAD', None)
    )
    result.add_subresult(context_result)
    command_context = context_result.value

    procedures.check_requirements(result_out=result,
                                  command_context=command_context,
                                  ref=command_context.selected_ref,
                                  modifiable=True,
                                  with_upstream=False,
                                  in_sync_with_upstream=False,
                                  fail_message=_("Hook failed.")
                                  )

    return result
