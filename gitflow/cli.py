import os
import sys
import types
from typing import TextIO

import colors

from gitflow.common import GitFlowException, Result

_ERROR_COLOR = colors.partial(colors.color, fg='red')
_WARN_COLOR = colors.partial(colors.color, fg='orange')

__enable_color = False


def set_allow_color(allow):
    global __enable_color
    __enable_color = allow and supports_color()


def supports_color():
    """
    Returns True if the running system's terminal supports color, and False
    otherwise.
    """
    plat = sys.platform
    supported_platform = plat != 'Pocket PC' and (plat != 'win32' or
                                                  'ANSICON' in os.environ)
    # isatty is not always implemented, #6223.
    is_a_tty = hasattr(sys.stdout, 'isatty') and sys.stdout.isatty()
    if not supported_platform or not is_a_tty:
        return False
    return True


def print(message):
    sys.stdout.write(message)
    if not message.endswith('\n'):
        sys.stdout.write('\n')


def fcwrite(out: TextIO, color, message: str):
    if __enable_color and color is not None:
        out.write(color(message))
    else:
        out.write(message)


def fcwriteln(out: TextIO, color, message: str = None):
    if message is not None:
        fcwrite(out, color, message + os.linesep)
    else:
        fcwrite(out, color, os.linesep)


def eprint(message: str):
    fcwriteln(sys.stderr, _ERROR_COLOR, message)


def warn(message: str):
    fcwriteln(sys.stderr, _WARN_COLOR, message)


def fail(exit_code, *message):
    # TODO remove
    for line in message:
        eprint(line)
    if exit_code == os.EX_OK:
        eprint("internal error")
        exit_code = os.EX_SOFTWARE
    result = Result()
    result.error(exit_code, os.linesep.join(message), None)
    raise GitFlowException(result)


def if_none(obj, default=""):
    if obj is None:
        return default
    return str(obj)


def shellquote(s):
    return "'" + s.replace("'", "'\\''") + "'"


def get_cmd(command_funcs, name: str, prefix: str):
    """
    :param command_funcs: a list of functions prefixed with 'cmd_'.
    Pattern: cmd_<command_name>, '_' in <command_name> translate to '-'.
    :param name: function name (sub-command)
    :param prefix: name prefix to add before searching for the function
    :return: the first function present in command_funcs.
    """
    for func in command_funcs:
        if not isinstance(func, types.FunctionType):
            fail(os.EX_SOFTWARE, "internal error")

        func_name = str.lower(func.__name__)
        if not func_name.startswith(prefix):
            fail(os.EX_SOFTWARE, "internal error")
        func_name = func_name[len(prefix):None]
        command_name = str.lower(func_name.replace('_', '-'))
        if name == command_name:
            return func
    return None


def query_yes_no(output_stream, question, default="yes"):
    """Ask a yes/no question via raw_input() and return their answer.

    "question" is a string that is presented to the user.
    "default" is the presumed answer if the user just hits <Enter>.
        It must be "yes" (the default), "no" or None (meaning
        an answer is required of the user).

    The "answer" return value is True for "yes" or False for "no".

    Source: https://stackoverflow.com/a/3041990
    """
    responses = {"yes": True, "y": True,
                 "no": False, "n": False}
    if default is None:
        prompt = " [y/n] "
    elif responses[default.lower()]:
        prompt = " [Y/n] "
    else:
        prompt = " [y/N] "

    while True:
        output_stream.write(question + prompt)
        choice = input().lower()
        if default is not None and choice == '':
            return responses[default]
        elif choice in responses:
            return responses[choice]
        else:
            output_stream.write("Please respond with 'yes' or 'no' "
                                "(or 'y' or 'n').\n")


def get_boolean_opt(args: dict, option: str) -> [bool, None]:
    """
    Follows the --option/--no-option convention
    :param args:
    :param option:
    :return: True, False or None, if neither of the option pair is set
    """
    tokens = option.split('--')
    if len(tokens) != 2 or len(tokens[0]) != 0:
        raise ValueError()
    value = args[option]
    disable_value = args['--no-' + tokens[1]]

    if disable_value:
        return False
    elif value:
        return value
    else:
        return None
