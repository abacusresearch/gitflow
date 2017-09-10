"""
Git Flow CLI

Usage:
 flow status
        [--root=DIR] [--config=FILE] [-B|--batch] [-v|--verbose]... [-p|--pretty]
 flow (bump-major|bump-minor) [-d|--dry-run] [-y|--assume-yes] [<object>]
        [--root=DIR] [--config=FILE] [-B|--batch] [-v|--verbose]... [-p|--pretty]
 flow (bump-patch|bump-prerelease-type|bump-prerelease|bump-to-release) [-d|--dry-run] [-y|--assume-yes] [<object>]
        [--root=DIR] [--config=FILE] [-B|--batch] [-v|--verbose]... [-p|--pretty]
 flow bump-to [-d|--dry-run] [-y|--assume-yes] <version> [<object>]
        [--root=DIR] [--config=FILE] [-B|--batch] [-v|--verbose]... [-p|--pretty]
 flow discontinue [-d|--dry-run] [-y|--assume-yes] [--reintegrate|--no-reintegrate] [<object>]
        [--root=DIR] [--config=FILE] [-B|--batch] [-v|--verbose]... [-p|--pretty]
 flow start [-d|--dry-run] [-y|--assume-yes] (<supertype> <type> <name>|<work-branch>) [<base-branch>]
        [--root=DIR] [--config=FILE] [-B|--batch] [-v|--verbose]... [-p|--pretty]
 flow finish [-d|--dry-run] [-y|--assume-yes] [(<supertype> <type> <name>|<work-branch>) [<base-branch>]]
        [--root=DIR] [--config=FILE] [-B|--batch] [-v|--verbose]... [-p|--pretty]
 flow log [<object>] [-- [<git-arg>]]...
        [--root=DIR] [--config=FILE] [-B|--batch] [-v|--verbose]... [-p|--pretty]
 flow build [-d|--dry-run] [<object>]
        [--root=DIR] [--config=FILE] [-B|--batch] [-v|--verbose]... [-p|--pretty]
 flow (-h|--help)
 flow --version

Options:
 -h --help              Shows this screen.
 --version              Shows version information.

Workspace Options:
 --root=DIR                         The working copy root.
 [default: .]
 --config=FILE                      The configuration file relative to the working copy root.
 [default: gitflow.properties]

Execution Mode Options:
 -B --batch             Disables interaction and output coloring.
 -y --assume-yes        Automatically answer yes for all questions.
 -d --dry-run           Prints actions without executing them.

Output Options:
 -v --verbose           Enables detailed output.
                        This option can be specified twice to enable the output of underlying commands.
 -p --pretty            Enables formatted and colored output.

"""

import os
import sys

import docopt

from gitflow import cli, procedures, repotools, _
from gitflow import const
from gitflow import version
from gitflow.common import GitFlowException, Result
from gitflow.context import Context

# project_env = os.path.normpath(os.path.join(os.path.dirname(__file__), '..'))
# print('project_env: ' + project_env)
# sys.path.insert(0, project_env)

ENABLE_PROFILER = False


# ========== commands
# mapped by cmd_<name>

def cmd_bump_major(context):
    return procedures.create_version(context, version.version_bump_major)


def cmd_bump_minor(context):
    return procedures.create_version(context, version.version_bump_minor)


def cmd_bump_patch(context):
    return procedures.create_version(context, version.version_bump_patch)


def cmd_bump_prerelease_type(context):
    return procedures.create_version(context, version.version_bump_qualifier)


def cmd_bump_prerelease(context):
    return procedures.create_version(context, version.version_bump_prerelease)


def cmd_bump_to_release(context):
    return procedures.create_version(context, version.version_bump_to_release)


def cmd_bump_to(context):
    return procedures.create_version(context,
                                     version.version_set(context.parsed_config.version, context.args['<version>']))


def cmd_discontinue(context):
    return procedures.discontinue_version(context)


def cmd_start(context):
    return procedures.begin(context)


def cmd_finish(context):
    return procedures.end(context)


def cmd_log(context):
    return procedures.log(context)


def cmd_status(context):
    return procedures.status(context)


def cmd_build(context):
    return procedures.build(context)


# ========== entry point

def main(argv: list = sys.argv) -> int:
    if ENABLE_PROFILER:
        import cProfile
        profiler = cProfile.Profile()
        profiler.enable()
    else:
        profiler = None

    result = Result()

    args = docopt.docopt(argv=argv[1:], doc=__doc__, version=const.VERSION, help=True, options_first=False)
    try:
        context = Context.create(args, result)
    except GitFlowException as e:
        context = None
        pass  # errors are in result
    if context is not None:
        try:
            if context.verbose >= const.TRACE_VERBOSITY:
                cli.print("cwd: " + os.getcwd())

            if context.verbose >= const.TRACE_VERBOSITY:
                cli.print("Python version:\n" + sys.version + "\n")

            command_func = cli.get_cmd([
                cmd_status,
                cmd_bump_major,
                cmd_bump_minor,
                cmd_bump_patch,
                cmd_bump_prerelease_type,
                cmd_bump_prerelease,
                cmd_bump_to_release,
                cmd_bump_to,
                cmd_discontinue,
                cmd_start,
                cmd_finish,
                cmd_log,
                cmd_build,
            ], context.args)

            if command_func is None:
                cli.fail(os.EX_SOFTWARE, "unimplemented command")

            if context.verbose >= const.TRACE_VERBOSITY:
                cli.print("command: " + cli.if_none(command_func))

            start_branch = repotools.git_get_current_branch(context.repo)

            try:
                command_result = command_func(context)
            except GitFlowException as e:
                command_result = e.result
            result.errors.extend(command_result.errors)

            current_branch = repotools.git_get_current_branch(context.repo)
            if current_branch != start_branch:
                cli.print(_("You are now on {branch}.")
                          .format(branch=repr(current_branch.short_name) if current_branch is not None else '-'))
        finally:
            context.cleanup()

    exit_code = os.EX_OK
    if len(result.errors):
        sys.stderr.flush()
        sys.stdout.flush()

        for error in result.errors:
            if error.exit_code != os.EX_OK and exit_code != os.EX_SOFTWARE:
                exit_code = error.exit_code
            cli.eprint('\n'.join(filter(None, [error.message, error.reason])))

    # print dry run status, if possible
    if context is not None:
        if exit_code == os.EX_OK:
            if context.dry_run:
                cli.print('')
                cli.print("dry run succeeded")
            else:
                pass
        else:
            if context.dry_run:
                cli.print('')
                cli.eprint("dry run failed")
            else:
                pass

    if profiler is not None:
        profiler.disable()
        # pr.dump_stats('profile.pstat')
        profiler.print_stats(sort="calls")

    return exit_code


if __name__ == "__main__":
    __exit_code = main(sys.argv)
    sys.exit(__exit_code)
