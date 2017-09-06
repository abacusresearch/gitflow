import os


class Error(object):
    exit_code = os.EX_SOFTWARE
    message = None
    reason = None

    def __init__(self, exit_code, message, reason):
        self.exit_code = exit_code
        self.message = message
        self.reason = reason


class GitFlowException(Exception):
    result = None

    def __init__(self, result):
        self.result = result


class Result(object):
    value = None
    errors = None

    def __init__(self):
        self.errors = list()

    def warn(self, message, reason):
        self.errors.append(Error(os.EX_OK, message, reason))

    def error(self, exit_code, message, reason):
        self.errors.append(Error(exit_code, message, reason))

    def fail(self, exit_code, message, reason):
        self.error(exit_code, message, reason)
        self.abort()

    def add_subresult(self, subresult):
        if subresult == self:
            raise ValueError("subresult == self")
        self.errors += subresult.errors
        if subresult.has_errors():
            self.abort()
        pass

    def has_errors(self):
        for error in self.errors:
            if error.exit_code != os.EX_OK:
                return True
        return False

    def abort_on_error(self):
        if self.has_errors():
            self.abort()

    def abort(self):
        raise GitFlowException(self)
