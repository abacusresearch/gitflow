from gitflow import utils, const
from gitflow.context import Context
from gitflow.procedures.common import get_command_context, execute_build_steps


def call(context: Context):
    command_context = get_command_context(
        context=context,
        object_arg=context.args['<object>']
    )

    selected_stages = list()

    for stage_type in const.BUILD_STAGE_TYPES:
        if context.args[stage_type.replace('_', '-')]:
            selected_stages.append(stage_type)

    execute_build_steps(command_context, context, selected_stages)

    return context.result
