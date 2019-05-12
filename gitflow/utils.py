import shlex
from typing import Callable


def cmp_to_key(comparator: Callable):
    class KeyCmpWrapper:
        def __init__(self, obj, *args):
            self.obj = obj

        def __lt__(self, other):
            return comparator(self.obj, other.obj) < 0

        def __gt__(self, other):
            return comparator(self.obj, other.obj) > 0

        def __eq__(self, other):
            return comparator(self.obj, other.obj) == 0

        def __le__(self, other):
            return comparator(self.obj, other.obj) <= 0

        def __ge__(self, other):
            return comparator(self.obj, other.obj) >= 0

        def __ne__(self, other):
            return comparator(self.obj, other.obj) != 0

    return KeyCmpWrapper


def get_or_default(map: dict, key, default):
    if key is None:
        return default
    value = map.get(key)
    if value is None:
        return default
    return value


def split_join(delimiter: str, delimit_start=True, delimit_end=True, *tokens):
    """
    Splits individual tokens by a delimiter and rejoins all of them separated by delimiter.
    :param delimiter: delimiter to split at and join with
    :param delimit_start: add a separator to the beginning of the result
    :param delimit_end: add a separator to the end of the result
    :rtype: str
    """
    result = ''
    delim_at_end = False

    if delimit_start:
        result += delimiter
        delim_at_end = True

    for token in tokens:
        for subtoken in token.split(delimiter):
            if subtoken is not None and len(subtoken):
                if len(result) and not delim_at_end:
                    result += delimiter
                    delim_at_end = True
                result += subtoken
                delim_at_end = False

    if delimit_end and not delim_at_end:
        result += delimiter

    return result


def quote(string, quote_char) -> str:
    return quote_char + string.replace(quote_char, '\\' + quote_char) + quote_char


def command_to_str(command):
    return ' '.join(shlex.quote(token) for token in command)
