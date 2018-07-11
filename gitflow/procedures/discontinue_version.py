import os

from gitflow import cli, repotools, _, const
from gitflow.common import Result
from gitflow.const import BranchClass
from gitflow.context import Context
from gitflow.procedures.common import get_command_context, get_branch_info, check_requirements, \
    get_discontinuation_tags, prompt_for_confirmation, create_shared_clone_repository, git_or_fail, fetch_all_and_ff, \
    check_in_repo, prompt, create_context
from gitflow.repotools import BranchSelection


def call(context: Context) -> Result:
    result: Result = context.result
    object_arg = context.args['<object>']

    reintegrate = cli.get_boolean_opt(context.args, '--reintegrate')

    command_context = get_command_context(
        context=context,
        object_arg=context.args['<object>']
    )

    check_in_repo(command_context)

    base_branch_ref = repotools.get_branch_by_name(context.repo, context.config.release_branch_base,
                                                   BranchSelection.BRANCH_PREFER_LOCAL)

    release_branch = command_context.selected_ref

    release_branch_info = get_branch_info(command_context, release_branch)

    check_requirements(command_context=command_context,
                       ref=release_branch,
                       branch_classes=[BranchClass.RELEASE],
                       modifiable=True,
                       with_upstream=True,  # not context.config.push_to_local
                       in_sync_with_upstream=True,
                       fail_message=_("Build failed.")
                       )

    if release_branch is None:
        command_context.fail(os.EX_USAGE,
                             _("Branch discontinuation failed."),
                             _("Failed to resolve an object for token {object}.")
                             .format(object=repr(object_arg))
                             )

    discontinuation_tags, discontinuation_tag_name = get_discontinuation_tags(context, release_branch)

    if discontinuation_tag_name is None:
        command_context.fail(os.EX_USAGE,
                             _("Branch discontinuation failed."),
                             _("{branch} cannot be discontinued.")
                             .format(branch=repr(release_branch.name))
                             )

    if context.verbose:
        cli.print("discontinuation tags:")
        for discontinuation_tag in discontinuation_tags:
            print(' - ' + discontinuation_tag.name)
        pass

    if len(discontinuation_tags):
        command_context.fail(os.EX_USAGE,
                             _("Branch discontinuation failed."),
                             _("The branch {branch} is already discontinued.")
                             .format(branch=repr(release_branch.name))
                             )
    # show info and prompt for confirmation
    print("discontinued_branch : " + cli.if_none(release_branch.name))

    if reintegrate is None:
        prompt_result = prompt(
            context=context,
            message=_("Branches may be reintegrated upon discontinuation."),
            prompt=_("Do you want to reintegrate {branch} into {base_branch}?")
                .format(branch=repr(release_branch.short_name),
                        base_branch=repr(base_branch_ref.short_name)),
        )
        command_context.add_subresult(prompt_result)
        if command_context.has_errors():
            return context.result

        reintegrate = prompt_result.value

    if not command_context.has_errors():
        # run merge on local clone

        clone_result = create_shared_clone_repository(context)
        clone_context = create_context(context, result, clone_result.value)

        changes = list()

        if reintegrate:
            git_or_fail(clone_context, command_context.result,
                        ['checkout', base_branch_ref.short_name],
                        _("Failed to checkout branch {branch_name}.")
                        .format(branch_name=repr(base_branch_ref.short_name))
                        )

            git_or_fail(clone_context, command_context.result,
                        ['merge', '--no-ff', release_branch_info.upstream.name],
                        _("Failed to merge work branch.\n"
                          "Rebase {work_branch} on {base_branch} and try again")
                        .format(work_branch=repr(release_branch.short_name),
                                base_branch=repr(base_branch_ref.short_name))
                        )
            changes.append(_("{branch} reintegrated into {base_branch}")
                           .format(branch=repr(release_branch.name), base_branch=repr(base_branch_ref.name)))

        changes.append(_("Discontinuation tag"))
        prompt_result = prompt_for_confirmation(
            context=context,
            fail_title=_("Failed to discontinue {branch}.")
                .format(branch=repr(release_branch.name)),
            message=(" - " + (os.linesep + " - ").join([_("Changes to be pushed:")] + changes)),
            prompt=_("Continue?"),
        )
        command_context.add_subresult(prompt_result)
        if command_context.has_errors() or not prompt_result.value:
            return context.result

        push_command = ['push', '--atomic']
        if context.dry_run:
            push_command.append('--dry-run')
        if context.verbose:
            push_command.append('--verbose')
        push_command.append(context.config.remote_name)

        push_command.append(base_branch_ref.name + ':' + repotools.create_ref_name(const.LOCAL_BRANCH_PREFIX,
                                                                                   base_branch_ref.short_name))
        push_command.append(
            '--force-with-lease=' + repotools.create_ref_name(const.LOCAL_TAG_PREFIX, discontinuation_tag_name) + ':')
        push_command.append(
            repotools.ref_target(release_branch) + ':' + repotools.create_ref_name(const.LOCAL_TAG_PREFIX,
                                                                                   discontinuation_tag_name))

        git_or_fail(clone_context, command_context.result, push_command)

        fetch_all_and_ff(context, command_context.result, context.config.remote_name)

    return context.result
