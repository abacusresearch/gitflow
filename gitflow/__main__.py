"""
Git Flow CLI

Usage:
 flow status [(-a|--all) | <object>]
        [--root=DIR] [--config=FILE] [-B|--batch] [-v|--verbose] [-p|--pretty]
 flow (bump-major|bump-minor) [-d|--dry-run] [-y|--assume-yes] [<object>]
        [--root=DIR] [--config=FILE] [-B|--batch] [-v|--verbose] [-p|--pretty]
 flow (bump-patch|bump-prerelease-type|bump-prerelease|bump-to-release) [-d|--dry-run] [-y|--assume-yes] [<object>]
        [--root=DIR] [--config=FILE] [-B|--batch] [-v|--verbose] [-p|--pretty]
 flow bump-to [-d|--dry-run] [-y|--assume-yes] <version> [<object>]
        [--root=DIR] [--config=FILE] [-B|--batch] [-v|--verbose] [-p|--pretty]
 flow discontinue [-d|--dry-run] [-y|--assume-yes] [--reintegrate|--no-reintegrate] [<object>]
        [--root=DIR] [--config=FILE] [-B|--batch] [-v|--verbose] [-p|--pretty]
 flow start [-d|--dry-run] [-y|--assume-yes] (<supertype> <type> <name>|<work-branch>) [<base-object>]
        [--root=DIR] [--config=FILE] [-B|--batch] [-v|--verbose] [-p|--pretty]
 flow finish [-d|--dry-run] [-y|--assume-yes] [(<supertype> <type> <name>|<work-branch>) [<base-object>]]
        [--root=DIR] [--config=FILE] [-B|--batch] [-v|--verbose] [-p|--pretty]
 flow log [<object>] [-- <git-arg>...]
        [--root=DIR] [--config=FILE] [-B|--batch] [-v|--verbose] [-p|--pretty]
 flow (assemble|test|integration-test) [-d|--dry-run] [--inplace| [<object>]]
        [--root=DIR] [--config=FILE] [-B|--batch] [-v|--verbose] [-p|--pretty]
 flow drop-cache [-d|--dry-run]
        [-B|--batch] [-v|--verbose] [-p|--pretty]
 flow (-h|--help)
 flow --version
 flow --hook=<hook-name> [<hook-args>...]

Options:
 -h --help              Shows this screen.
 --version              Shows version information.

Selection Options:
 -a --all               Select all branches

Workspace Options:
 --root=DIR             The working copy root.
 [default: .]
 --config=FILE          The configuration file relative to the working copy root.
 [default: gitflow.json]

Execution Mode Options:
 -B --batch             Disables interaction and output coloring.
 -y --assume-yes        Automatically answer yes for all questions.
 -d --dry-run           Prints actions without executing them.

Output Options:
 -v --verbose           Enables detailed output.
 -p --pretty            Enables formatted and colored output.

Hook Options:
--hook=<hook-name>      Sets the hook type. For use in Git hooks only.

"""

import os
import sys

import docopt

import gitflow.procedures.begin
import gitflow.procedures.build
import gitflow.procedures.create_version
import gitflow.procedures.discontinue_version
import gitflow.procedures.end
import gitflow.procedures.log
import gitflow.procedures.status
from gitflow import cli, repotools, _, hooks, filesystem
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
    return gitflow.procedures.create_version.call(context, version.version_bump_major)


def cmd_bump_minor(context):
    return gitflow.procedures.create_version.call(context, version.version_bump_minor)


def cmd_bump_patch(context):
    return gitflow.procedures.create_version.call(context, version.version_bump_patch)


def cmd_bump_prerelease_type(context):
    return gitflow.procedures.create_version.call(context, version.version_bump_qualifier)


def cmd_bump_prerelease(context):
    return gitflow.procedures.create_version.call(context, version.version_bump_prerelease)


def cmd_bump_to_release(context):
    return gitflow.procedures.create_version.call(context, version.version_bump_to_release)


def cmd_bump_to(context):
    return gitflow.procedures.create_version.call(context,
                                                  version.version_set(context.config.version,
                                                                      context.args['<version>']))


def cmd_discontinue(context):
    return gitflow.procedures.discontinue_version.call(context)


def cmd_start(context):
    return gitflow.procedures.begin.call(context)


def cmd_finish(context):
    return gitflow.procedures.end.call(context)


def cmd_log(context):
    return gitflow.procedures.log.call(context)


def cmd_status(context):
    return gitflow.procedures.status.call(context)


def cmd_build(context):
    return gitflow.procedures.build.call(context)


def cmd_drop_cache(context):
    result = Result()
    cache_root = filesystem.get_cache_root_dir()
    cli.print("dropping cache root: " + repr(cache_root))
    if not context.dry_run:
        filesystem.delete_all_cache_dirs()
    return result


# ========== hooks
# mapped by hook_<name>

def hook_pre_commit(context):
    return hooks.pre_commit(context)


def hook_pre_push(context):
    return hooks.pre_push(context)


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

            if args['--hook'] is not None:
                if context.verbose >= const.TRACE_VERBOSITY:
                    cli.print('hook=' + args['--hook'])

                hook_func = cli.get_cmd([
                    hook_pre_commit,
                    hook_pre_push,
                ], args['--hook'], 'hook_')

                try:
                    hook_result = hook_func(context)
                except GitFlowException as e:
                    hook_result = e.result
                result.errors.extend(hook_result.errors)
            else:
                commands = {
                    'status': cmd_status,
                    'bump-major': cmd_bump_major,
                    'bump-minor': cmd_bump_minor,
                    'bump-patch': cmd_bump_patch,
                    'bump-prerelease-type': cmd_bump_prerelease_type,
                    'bump-prerelease': cmd_bump_prerelease,
                    'bump-to-release': cmd_bump_to_release,
                    'bump-to': cmd_bump_to,
                    'discontinue': cmd_discontinue,
                    'start': cmd_start,
                    'finish': cmd_finish,
                    'log': cmd_log,
                    'assemble': cmd_build,
                    'test': cmd_build,
                    'integration-test': cmd_build,
                    'drop-cache': cmd_drop_cache,
                }

                command_funcs = list()

                for command_name, command_func in commands.items():
                    if args[command_name] is True:
                        command_funcs.append(command_func)

                if not len(command_funcs):
                    cli.fail(os.EX_SOFTWARE, "unimplemented command")

                if context.verbose >= const.TRACE_VERBOSITY:
                    cli.print("commands: " + repr(command_funcs))

                start_branch = repotools.git_get_current_branch(context.repo) if context.repo is not None else None

                for command_func in command_funcs:
                    try:
                        command_result = command_func(context)
                    except GitFlowException as e:
                        command_result = e.result
                    result.errors.extend(command_result.errors)
                    if result.has_errors():
                        break

                current_branch = repotools.git_get_current_branch(context.repo) if context.repo is not None else None
                if current_branch is not None and current_branch != start_branch:
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
