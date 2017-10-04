import os
import sys

import colors
import semver

from gitflow import repotools, const, cli, _, utils, version
from gitflow.common import Result
from gitflow.procedures.common import get_branch_version_component_for_version, get_discontinuation_tags, \
    update_branch_info, get_command_context, check_in_repo


def call(context) -> Result:
    command_context = get_command_context(
        context=context,
        object_arg=context.args['<work-branch>']
    )

    check_in_repo(command_context)

    unique_codes = set()
    unique_version_codes = list()

    upstreams = repotools.git_get_upstreams(context.repo)
    branch_info_dict = dict()

    for branch_ref in repotools.git_list_refs(context.repo, repotools.create_ref_name(const.REMOTES_PREFIX,
                                                                                      context.config.remote_name)):
        branch_match = context.release_branch_matcher.fullmatch(branch_ref.name)
        if branch_match:
            branch_version = context.release_branch_matcher.to_version(branch_ref.name)

            branch_version_string = get_branch_version_component_for_version(context, branch_version)

            discontinuation_tags, discontinuation_tag_name = get_discontinuation_tags(context, branch_ref)

            update_branch_info(context, branch_info_dict, upstreams, branch_ref)

            branch_info = branch_info_dict.get(branch_ref.name)
            discontinued = len(discontinuation_tags)

            if discontinued:
                status_color = colors.partial(colors.color, fg='gray')
                status_error_color = colors.partial(colors.color, fg='red')
                status_local_color = colors.partial(colors.color, fg='blue')
                status_remote_color = colors.partial(colors.color, fg='green')
            else:
                status_color = colors.partial(colors.color, fg='white', style='bold')
                status_error_color = colors.partial(colors.color, fg='red', style='bold')
                status_local_color = colors.partial(colors.color, fg='blue', style='bold')
                status_remote_color = colors.partial(colors.color, fg='green', style='bold')

            error_color = colors.partial(colors.color, fg='white', bg='red', style='bold')

            cli.fcwrite(sys.stdout, status_color, "version: " + branch_version_string + ' [')
            if branch_info.local is not None:
                local_branch_color = status_local_color
                if not branch_info.upstream.short_name.endswith('/' + branch_info.local.short_name):
                    command_context.error(os.EX_DATAERR,
                                          _("Local and upstream branch have a mismatching short name."),
                                          None)
                    local_branch_color = error_color
                if context.verbose:
                    cli.fcwrite(sys.stdout, local_branch_color, branch_info.local.name)
                else:
                    cli.fcwrite(sys.stdout, local_branch_color, branch_info.local.short_name)
            if branch_info.upstream is not None:
                if branch_info.local is not None:
                    cli.fcwrite(sys.stdout, status_color, ' => ')
                if context.verbose:
                    cli.fcwrite(sys.stdout, status_remote_color, branch_info.upstream.name)
                else:
                    cli.fcwrite(sys.stdout, status_remote_color, branch_info.upstream.short_name)
            cli.fcwrite(sys.stdout, status_color, "]")
            if discontinued:
                cli.fcwrite(sys.stdout, status_color, ' (' + _('discontinued') + ')')

            cli.fcwriteln(sys.stdout, status_color)

            tags = repotools.git_get_branch_tags(context=context.repo,
                                                 base=context.config.release_branch_base,
                                                 dest=branch_ref.name,
                                                 from_fork_point=False,
                                                 reverse=True,
                                                 tag_filter=None,
                                                 commit_tag_comparator=lambda a, b:
                                                 -1 if context.sequential_version_tag_matcher.fullmatch(
                                                     a.name) is not None
                                                 else 1)

            tags = list(tags)

            for branch_tag_ref in tags:
                # print the sequential version tag
                tag_match = context.sequential_version_tag_matcher.fullmatch(branch_tag_ref.name)
                if tag_match:
                    unique_code = tag_match.group(
                        context.sequential_version_tag_matcher.group_unique_code)
                    version_string = unique_code

                    unique_version_codes.append(int(unique_code))

                    if unique_code in unique_codes:
                        command_context.error(os.EX_DATAERR,
                                              _("Invalid sequential version tag {tag}.")
                                              .format(tag=branch_tag_ref.name),
                                              _("The code element of version {version_string} is not unique.")
                                              .format(version_string=version_string)
                                              )
                    else:
                        unique_codes.add(unique_code)

                    cli.fcwriteln(sys.stdout, status_color, "  code: " + version_string)

                # print the version tag
                version_string = context.version_tag_matcher.format(branch_tag_ref.name)
                if version_string:
                    version_info = semver.parse_version_info(version_string)
                    if version_info.major == branch_version.major and version_info.minor == branch_version.minor:
                        cli.fcwriteln(sys.stdout, status_color, "    " + version_string)
                    else:
                        command_context.error(os.EX_DATAERR,
                                              _("Invalid version tag {tag}.")
                                              .format(tag=repr(branch_tag_ref.name)),
                                              _("The major.minor part of the new version {new_version}"
                                                " does not match the branch version {branch_version}.")
                                              .format(new_version=repr(version_string),
                                                      branch_version=repr(branch_version_string))
                                              )
                        cli.fcwriteln(sys.stdout, status_error_color, "    " + version_string)

    unique_version_codes.sort(key=utils.cmp_to_key(lambda a, b: version.cmp_alnum_token(a, b)))

    last_unique_code = None
    for unique_code in unique_version_codes:
        if not (last_unique_code is None or unique_code > last_unique_code):
            command_context.error(os.EX_DATAERR,
                                  _("Version {version} breaks the sequence.")
                                  .format(version=unique_code),
                                  None
                                  )
        last_unique_code = unique_code

    return context.result
