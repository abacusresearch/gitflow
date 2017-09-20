from gitflow import utils, procedures, const
from gitflow.context import Context
from gitflow.procedures import get_command_context


def call(context: Context):
    command_context = get_command_context(
        context=context,
        object_arg=utils.get_or_default(context.args, '<object>', None)
    )

    procedures.execute_build_steps(command_context, context, [const.BUILD_STAGE_TYPE_ASSEMBLE])

    return command_context.result
