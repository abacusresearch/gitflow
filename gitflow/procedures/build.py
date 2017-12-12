from tempfile import TemporaryDirectory

from gitflow import const, repotools, _
from gitflow.context import Context
from gitflow.procedures.common import get_command_context, execute_build_steps, check_requirements


def call(context: Context):
    command_context = get_command_context(
        context=context,
        object_arg=context.args['<object>']
    )

    if context.repo is not None:
        if context.args['--inplace']:
            build_context = context
            build_command_context = command_context
        else:
            temp_dir = TemporaryDirectory()

            exported_repo = repotools.git_export(context=context.repo,
                                                 target_dir=temp_dir.name,
                                                 object=command_context.selected_commit)
            build_context = Context.create({**context.args, **{
                '--root': exported_repo.dir,

                '--config': context.args['--config'],  # no override here

                '--batch': context.batch,
                '--dry-run': context.dry_run,

                '--verbose': context.verbose,
                '--pretty': context.pretty,
            }}, context.result)
            build_command_context = get_command_context(
                context=build_context,
                object_arg=build_context.args['<object>']
            )

        check_requirements(command_context=build_command_context,
                           ref=build_command_context.selected_ref,
                           branch_classes=None,
                           modifiable=True,
                           with_upstream=True,  # not context.config.push_to_local
                           in_sync_with_upstream=True,
                           fail_message=_("Build failed."),
                           allow_unversioned_changes=False
                           )
    else:
        build_context = context
        build_command_context = command_context

    selected_stages = list()

    for stage_type in const.BUILD_STAGE_TYPES:
        if build_context.args[stage_type.replace('_', '-')]:
            selected_stages.append(stage_type)

    execute_build_steps(build_command_context, selected_stages)

    return context.result
