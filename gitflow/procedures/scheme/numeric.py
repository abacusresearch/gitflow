import datetime
import json
import os
import re
from typing import Optional, Callable

import pytz as pytz
import semver

import gitflow.procedures.begin
import gitflow.procedures.end
from gitflow import _, const, repotools, utils, cli
from gitflow.common import Result
from gitflow.const import BranchClass
from gitflow.context import Context
from gitflow.procedures.common import get_command_context, check_in_repo, check_requirements, fetch_all_and_ff, \
    CommandContext, get_global_sequence_number, read_config_in_commit, read_properties_in_commit, git_or_fail, \
    clone_repository, CommitInfo, create_temp_context, update_project_property_file, execute_version_change_actions, \
    create_commit, prompt_for_confirmation
from gitflow.procedures.scheme.versioning_scheme import VersioningSchemeImpl
from gitflow.version import IncrementalVersionMatcher, VersionDelta, VersionConfig


class NumericVersioning(VersioningSchemeImpl):
    __initial_version: str = None

    def __init__(self, context: Context):
        self.__initial_version = context.config.version_config.initial_version

        remote_prefix = repotools.create_ref_name(const.REMOTES_PREFIX, context.config.remote_name)

        self.release_base_branch_matcher = IncrementalVersionMatcher(
            [const.LOCAL_BRANCH_PREFIX, remote_prefix],
            None,
            re.escape(context.config.release_branch_base),
        )

        self.release_branch_matcher = IncrementalVersionMatcher(
            [const.LOCAL_BRANCH_PREFIX, remote_prefix],
            None,
            context.config_properties.get(
                const.CONFIG_RELEASE_BRANCH_PATTERN,
                const.DEFAULT_CENTRAL_RELEASE_BRANCH_PATTERN),
        )

        self.work_branch_matcher = IncrementalVersionMatcher(
            [const.LOCAL_BRANCH_PREFIX, remote_prefix],
            [const.BRANCH_PREFIX_DEV, const.BRANCH_PREFIX_PROD],
            context.config_properties.get(
                const.CONFIG_WORK_BRANCH_PATTERN,
                const.DEFAULT_WORK_BRANCH_PATTERN),
        )

        self.version_tag_matcher = IncrementalVersionMatcher(
            [const.LOCAL_TAG_PREFIX],
            context.config_properties.get(
                const.CONFIG_VERSION_TAG_PREFIX,
                const.DEFAULT_VERSION_TAG_PREFIX),
            context.config_properties.get(
                const.CONFIG_VERSION_TAG_PATTERN,
                const.DEFAULT_NUMERIC_VERSION_TAG_PATTERN)
        )
        self.version_tag_matcher.group_unique_code = 'unique_code'

        self.discontinuation_tag_matcher = IncrementalVersionMatcher(
            [const.LOCAL_TAG_PREFIX],
            context.config_properties.get(
                const.CONFIG_DISCONTINUATION_TAG_PREFIX,
                const.DEFAULT_DISCONTINUATION_TAG_PREFIX),
            context.config_properties.get(
                const.CONFIG_DISCONTINUATION_TAG_PATTERN,
                const.DEFAULT_DISCONTINUATION_TAG_PATTERN),
            None
        )

    def get_initial_version(self):
        now = datetime.datetime.now(tz=pytz.timezone('UTC'))
        return "%d%d%d%d%d%d" % now.year, now.month, now.day, now.hour, now.minute, now.second

    def parse_version_info(self, version: str) -> semver.VersionInfo:
        return semver.VersionInfo(major=int(version.split('.')[0]), minor=0, patch=0)

    def format_version_info(self, version_info: semver.VersionInfo) -> str:
        return str(version_info.major)

    def compare_version(self, a: str, b: str) -> VersionDelta:
        delta = VersionDelta()

        delta.difference = int(a) - int(b)

        return delta

    def compare_version_info(self, a: semver.VersionInfo, b: semver.VersionInfo):
        # TODO avoid superfluous conversions
        return semver.compare(self.format_version_info(a), self.format_version_info(b))

    def get_tag_name_for_version(self, context: Context, version: str):
        return (context.version_tag_matcher.ref_name_infix or '') \
               + str(version)

    def cmd_bump_major(self, context: Context):
        command_context = get_command_context(
            context=context,
            object_arg=context.args['<object>']
        )

        check_in_repo(command_context)

        check_requirements(command_context=command_context,
                           ref=command_context.selected_ref,
                           branch_classes=[BranchClass.DEVELOPMENT_BASE],
                           modifiable=True,
                           in_sync_with_upstream=True,
                           fail_message=_("Version creation failed.")
                           )

        tag_result = create_branchless_version_tag(command_context, version_bump_integer)
        command_context.add_subresult(tag_result)

        if not command_context.has_errors() \
                and context.config.pull_after_bump \
                and not context.config.push_to_local:
            fetch_all_and_ff(context.repo, command_context.result, context.config.remote_name)

        return context.result

    def cmd_start(self, context: Context):
        return gitflow.procedures.begin.call(context)

    def cmd_finish(self, context: Context):
        return gitflow.procedures.end.call(context)


def version_bump_integer(version_config: VersionConfig, version: Optional[str], global_seq: Optional[int]):
    result = Result()
    result.value = str(int(version) + 1)
    return result


def create_branchless_version_tag(command_context: CommandContext,
                       operation: Callable[[VersionConfig, Optional[str], Optional[int]], Result]) -> Result:
    result = Result()
    context: Context = command_context.context

    release_branches = command_context.context.get_release_branches(reverse=True)

    # TODO configuration
    allow_merge_base_tags = True  # context.config.allow_shared_release_branch_base

    selected_branch = command_context.selected_ref

    if context.release_branch_matcher.fullmatch(command_context.selected_ref.name) is None:
        result.fail(os.EX_USAGE,
                    _("Cannot bump version."),
                    _("{branch} is not a release branch.")
                    .format(branch=repr(command_context.selected_ref.name)))

    latest_version_tag = None
    preceding_version_tag = None
    preceding_branch_version_tag = None
    version_tags_on_same_commit = list()
    subsequent_version_tags = list()
    enclosing_versions = set()

    # abort scan, when a preceding commit for each tag type has been processed.
    # enclosing_versions now holds enough information for operation validation,
    # assuming the branch has not gone haywire in earlier commits
    # TODO evaluate upper and lower bound version for efficiency
    abort_version_scan = False

    for release_branch in release_branches:
        # fork_point = repotools.git_merge_base(context.repo, context.config.release_branch_base,
        #                                       command_context.selected_commit)
        # if fork_point is None:
        #     result.fail(os.EX_USAGE,
        #                 _("Cannot bump version."),
        #                 _("{branch} has no fork point on {base_branch}.")
        #                 .format(branch=repr(command_context.selected_ref.name),
        #                         base_branch=repr(context.config.release_branch_base)))
        fork_point = None

        on_selected_branch = False

        before_commit = False
        before_selected_branch = False

        branch_base_version = context.release_branch_matcher.format(release_branch.name)
        if branch_base_version is not None:
            branch_base_version_info = context.versioning_scheme.parse_version_info(branch_base_version)
        else:
            branch_base_version_info = None

        on_selected_branch = not before_selected_branch and release_branch.obj_name == selected_branch.obj_name

        for history_commit in repotools.git_list_commits(
                context=context.repo,
                start=fork_point,
                end=release_branch.obj_name,
                options=const.BRANCH_COMMIT_SCAN_OPTIONS):
            at_commit = not before_commit and on_selected_branch and history_commit.obj_name == command_context.selected_commit

            version_tag_refs = None

            assert not at_commit if before_commit else not before_commit

            for tag_ref in repotools.git_get_tags_by_referred_object(context.repo, history_commit.obj_name):
                version_info = context.version_tag_matcher.to_version_info(tag_ref.name)
                if version_info is not None:
                    tag_matches = branch_base_version_info is None or (version_info.major == branch_base_version_info.major \
                                  and version_info.minor == branch_base_version_info.minor)

                    if tag_matches:
                        if version_tag_refs is None:
                            version_tag_refs = list()
                        version_tag_refs.append(tag_ref)
                    else:
                        if fork_point is not None:
                            # fail stray tags on exclusive branch commits
                            result.fail(os.EX_DATAERR,
                                        _("Cannot bump version."),
                                        _("Found stray version tag: {version}.")
                                        .format(
                                            version=repr(context.versioning_scheme.format_version_info(version_info)))
                                        )
                        else:
                            # when no merge base is used, abort at the first mismatching tag
                            break

            if not abort_version_scan and version_tag_refs is not None and len(version_tag_refs):
                version_tag_refs.sort(
                    reverse=True,
                    key=utils.cmp_to_key(
                        lambda tag_ref_a, tag_ref_b: semver.compare(
                            context.version_tag_matcher.format(tag_ref_a.name),
                            context.version_tag_matcher.format(tag_ref_b.name)
                        )
                    )
                )
                if latest_version_tag is None:
                    latest_version_tag = version_tag_refs[0]
                if at_commit:
                    version_tags_on_same_commit.extend(version_tag_refs)
                if at_commit or before_commit:
                    if preceding_version_tag is None:
                        preceding_version_tag = version_tag_refs[0]
                    if on_selected_branch and preceding_branch_version_tag is None:
                        preceding_branch_version_tag = version_tag_refs[0]
                else:
                    subsequent_version_tags.extend(version_tag_refs)

                for tag_ref in version_tag_refs:
                    enclosing_versions.add(context.version_tag_matcher.format(tag_ref.name))

                if before_commit:
                    abort_version_scan = True

            if at_commit:
                before_commit = True

        if on_selected_branch:
            before_commit = True
            before_selected_branch = True

        if abort_version_scan:
            break

    if context.config.sequential_versioning and preceding_version_tag is not None:
        match = context.version_tag_matcher.fullmatch(preceding_version_tag.name)
        preceding_sequential_version = match.group(context.version_tag_matcher.group_unique_code)
    else:
        preceding_sequential_version = None
    if preceding_sequential_version is not None:
        preceding_sequential_version = int(preceding_sequential_version)

    if context.verbose:
        cli.print("Tags on selected commit:\n"
                  + '\n'.join(' - ' + repr(tag_ref.name) for tag_ref in version_tags_on_same_commit))

        cli.print("Tags in subsequent history:\n"
                  + '\n'.join(' - ' + repr(tag_ref.name) for tag_ref in subsequent_version_tags))

    if preceding_branch_version_tag is not None:
        latest_branch_version = context.version_tag_matcher.format(preceding_branch_version_tag.name)
    else:
        latest_branch_version = None

    global_sequence_number = get_global_sequence_number(context)
    if latest_branch_version is not None:
        version_result = operation(context.config.version_config, latest_branch_version, global_sequence_number)
        result.add_subresult(version_result)

        new_version = version_result.value
        if result.has_errors():
            return result
    else:
        new_version = '1'

    new_sequential_version = None

    try:
        config_in_selected_commit = read_config_in_commit(context.repo, command_context.selected_commit)
    except FileNotFoundError:
        config_in_selected_commit = dict()

    try:
        properties_in_selected_commit = read_properties_in_commit(context,
                                                                  context.repo,
                                                                  config_in_selected_commit,
                                                                  command_context.selected_commit)
    except FileNotFoundError:
        properties_in_selected_commit = dict()

    if context.verbose:
        print("properties in selected commit:")
        print(json.dumps(obj=properties_in_selected_commit, indent=2))

    valid_tag = False

    # validate the commit
    if len(version_tags_on_same_commit):
        if config_in_selected_commit is None:
            result.fail(os.EX_DATAERR,
                        _("Tag creation failed."),
                        _("The selected commit does not contain a configuration file.")
                        )

        version_property_name = config_in_selected_commit.get(const.CONFIG_VERSION_PROPERTY)
        if version_property_name is not None \
                and properties_in_selected_commit.get(version_property_name) is None:
            result.warn(_("Missing version info."),
                        _("The selected commit does not contain a version in property '{property_name}'.")
                        .format(property_name=version_property_name)
                        )

    if len(version_tags_on_same_commit):
        if context.config.allow_qualifier_increments_within_commit:
            preceding_commit_version = context.version_tag_matcher.format(
                version_tags_on_same_commit[0].name)
            prerelease_keywords_list = [context.config.version_config.qualifiers, 1]

            preceding_commit_version_ = preceding_commit_version
            new_commit_version_ = new_version
            version_delta = context.versioning_scheme.compare_version(preceding_commit_version_,
                                                            new_commit_version_
                                                            )

            valid_tag = True
        else:
            result.fail(os.EX_USAGE,
                        _("Tag creation failed."),
                        _("There are version tags pointing to the selected commit {commit}.\n"
                          "Consider reusing these versions or bumping them to stable."
                          "{listing}")
                        .format(commit=command_context.selected_commit,
                                listing='\n'.join(
                                    ' - ' + repr(tag_ref.name) for tag_ref in subsequent_version_tags))
                        )

    if not valid_tag:
        if len(subsequent_version_tags):
            result.fail(os.EX_USAGE,
                        _("Tag creation failed."),
                        _("There are version tags in branch history following the selected commit {commit}:\n"
                          "{listing}")
                        .format(commit=command_context.selected_commit,
                                listing='\n'.join(
                                    ' - ' + repr(tag_ref.name) for tag_ref in subsequent_version_tags))
                        )

    global_seq_number = global_sequence_number
    if context.config.tie_sequential_version_to_semantic_version \
            and global_seq_number is not None \
            and new_sequential_version is not None \
            and preceding_sequential_version != global_seq_number:
        result.fail(os.EX_USAGE,
                    _("Tag creation failed."),
                    _(
                        "The preceding sequential version {seq_val} "
                        "does not equal the global sequential version {global_seq_val}.")
                    .format(seq_val=preceding_sequential_version
                    if preceding_sequential_version is not None
                    else '<none>',
                            global_seq_val=global_seq_number)
                    )

    if not result.has_errors():
        if new_version is None:
            result.fail(os.EX_SOFTWARE,
                        _("Internal error."),
                        _("Missing result version.")
                        )
        if latest_branch_version is not None and context.versioning_scheme.compare_version(latest_branch_version, new_version).difference >= 0:
            result.fail(os.EX_DATAERR,
                        _("Failed to increment version from {current} to {new}.")
                        .format(current=repr(latest_branch_version), new=repr(new_version)),
                        _("The new version is lower than or equal to the current version.")
                        )

        if context.config.push_to_local \
                and command_context.current_branch.short_name == command_context.selected_ref.short_name:
            if context.verbose:
                cli.print(
                    _('Checking out {base_branch} in order to avoid failing the push to a checked-out release branch')
                        .format(base_branch=repr(context.config.release_branch_base)))

            git_or_fail(context.repo, result, ['checkout', context.config.release_branch_base])
            original_current_branch = command_context.current_branch
        else:
            original_current_branch = None

        tag_name = context.versioning_scheme.get_tag_name_for_version(context, new_version)

        clone_result = clone_repository(context, context.config.release_branch_base)
        cloned_repo = clone_result.value

        commit_info = CommitInfo()
        commit_info.add_message("#version: " + cli.if_none(new_version))

        # run version change hooks on release branch
        checkout_command = ['checkout', '--force', '--track', '-B', selected_branch.short_name,
                            repotools.create_ref_name(const.REMOTES_PREFIX,
                                                      'origin',
                                                      selected_branch.short_name)]
        returncode, out, err = repotools.git(cloned_repo, *checkout_command)
        if returncode != os.EX_OK:
            result.fail(os.EX_DATAERR,
                        _("Failed to check out release branch."),
                        _("An unexpected error occurred.")
                        )

        clone_context: Context = create_temp_context(context, result, cloned_repo.dir)
        clone_context.config.remote_name = 'origin'

        if (context.config.commit_version_property and new_version is not None) \
                or (context.config.commit_sequential_version_property and new_sequential_version is not None):

            update_result = update_project_property_file(clone_context,
                                                         properties_in_selected_commit,
                                                         new_version,
                                                         new_sequential_version,
                                                         commit_info)
            result.add_subresult(update_result)
            if result.has_errors():
                result.fail(os.EX_DATAERR,
                            _("Property update failed."),
                            _("An unexpected error occurred.")
                            )

        if new_version is not None:
            execute_version_change_actions(clone_context, latest_branch_version, new_version)

        if commit_info is not None:
            if command_context.selected_commit != command_context.selected_ref.target.obj_name:
                result.fail(os.EX_USAGE,
                            _("Failed to commit version update."),
                            _("The selected parent commit {commit} does not represent the tip of {branch}.")
                            .format(commit=command_context.selected_commit,
                                    branch=repr(command_context.selected_ref.name))
                            )

            # commit changes
            commit_info.add_parent(command_context.selected_commit)
            object_to_tag = create_commit(clone_context, result, commit_info)
            new_branch_ref_object = object_to_tag
        else:
            object_to_tag = command_context.selected_commit
            new_branch_ref_object = None

        # if command_context.selected_branch not in repotools.git_list_refs(context.repo,
        #                                                                   '--contains', object_to_tag,
        #                                                                   command_context.selected_branch.ref):

        # show info and prompt for confirmation
        cli.print("ref                 : " + cli.if_none(command_context.selected_ref.name))
        cli.print("ref_" + const.DEFAULT_VERSION_VAR_NAME + "         : " + cli.if_none(latest_branch_version))
        cli.print("new_tag             : " + cli.if_none(tag_name))
        cli.print("new_" + const.DEFAULT_VERSION_VAR_NAME + "         : " + cli.if_none(new_version))
        cli.print("selected object     : " + cli.if_none(command_context.selected_commit))
        cli.print("tagged object       : " + cli.if_none(object_to_tag))

        prompt_result = prompt_for_confirmation(
            context=context,
            fail_title=_("Failed to create release tag based on {branch}.")
                .format(branch=repr(command_context.selected_ref.name)),
            message=_("The tags are about to be pushed."),
            prompt=_("Continue?"),
        )
        result.add_subresult(prompt_result)
        if result.has_errors() or not prompt_result.value:
            return result

        # push atomically
        push_command = ['push', '--atomic']
        if context.dry_run:
            push_command.append('--dry-run')
        if context.verbose:
            push_command.append('--verbose')
        push_command.append(clone_context.config.remote_name)

        # push the release branch commit or its version increment commit
        if new_branch_ref_object is not None:
            push_command.append(
                new_branch_ref_object + ':' + repotools.create_ref_name(const.LOCAL_BRANCH_PREFIX, selected_branch.short_name))

        # check, if preceding tags exist on remote
        if preceding_version_tag is not None:
            push_command.append('--force-with-lease='
                                + preceding_version_tag.name + ':'
                                + preceding_version_tag.name)

        # push the new version tag or fail if it exists
        push_command.extend(['--force-with-lease=' + repotools.create_ref_name(const.LOCAL_TAG_PREFIX, tag_name) + ':',
                             repotools.ref_target(object_to_tag) + ':' + repotools.create_ref_name(
                                 const.LOCAL_TAG_PREFIX, tag_name)])

        returncode, out, err = repotools.git(clone_context.repo, *push_command)
        if returncode != os.EX_OK:
            result.fail(os.EX_DATAERR,
                        _("Failed to push."),
                        _("git push exited with " + str(returncode))
                        )

        if original_current_branch is not None:
            if context.verbose:
                cli.print(
                    _('Switching back to {original_branch} ')
                        .format(original_branch=repr(original_current_branch.name)))

            git_or_fail(context.repo, result, ['checkout', original_current_branch.short_name])

    return result