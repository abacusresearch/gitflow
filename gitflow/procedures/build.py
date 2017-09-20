import subprocess

from gitflow import utils
from gitflow.context import Context
from gitflow.procedures import get_command_context


def call(context: Context):
    command_context = get_command_context(
        context=context,
        object_arg=utils.get_or_default(context.args, '<object>', None)
    )

    for stage in context.config.build_stages:
        for step in stage.steps:
            for command in step.commands:
                proc = subprocess.Popen(args=command,
                                 stdin=subprocess.PIPE,
                                 cwd=context.root)
                proc.wait()

    return command_context.result
