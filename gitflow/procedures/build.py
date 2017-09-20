import os
import subprocess

from gitflow import utils, _
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
                try:
                    proc = subprocess.Popen(args=command,
                                            stdin=subprocess.PIPE,
                                            cwd=context.root)
                    proc.wait()
                    if proc.returncode != os.EX_OK:
                        command_context.fail(os.EX_DATAERR,
                                             _("Build failed."),
                                             _("Stage {stage}:{step} returned with an error.")
                                             .format(stage=stage.name, step=step.name))
                except FileNotFoundError as e:
                    command_context.fail(os.EX_DATAERR,
                                         _("Build failed."),
                                         _("Stage {stage}:{step} could not be executed.")
                                         .format(stage=stage.name, step=step.name))

    return command_context.result
