from gitflow import utils, procedures, const
from gitflow.context import Context
from gitflow.procedures import get_command_context


def call(context: Context):
    command_context = get_command_context(
        context=context,
        object_arg=utils.get_or_default(context.args, '<object>', None)
    )

    selected_stages = list()

    for stage_type in const.BUILD_STAGE_TYPES:
        if context.args[stage_type.replace('_', '-')]:
            selected_stages.append(stage_type)

    procedures.execute_build_steps(command_context, context, selected_stages)

    return command_context.result
