import itertools
import os
import re
import shlex
import subprocess
import typing
from enum import Enum
from typing import Optional, Union, Callable, List

from gitflow import utils, cli, const


class RepoContext(object):
    git = 'git'
    dir = '.'
    tags = None  # dict
    verbose = const.ERROR_VERBOSITY  # TODO use parent context
    use_root_dir_arg = False


class Remote(object):
    name = None
    url = None


class Object(object):
    obj_type = None
    obj_name = None

    def __eq__(self, other):
        if isinstance(other, Object):
            return self.obj_name == other.obj_name
        else:
            return False

    def __ne__(self, other):
        return not self.__eq__(other)

    def __hash__(self):
        return hash(self.obj_name)

    def __repr__(self):
        if isinstance(self, Ref):
            target = self.target
            if target != self and isinstance(target, Ref):
                target_name = ref_name(target)
            else:
                target_name = ref_target(target)
            return ref_name(self) + ' => ' + target_name
        else:
            return self.obj_name

    def __str__(self):
        return self.__repr__()


class Commit(Object):
    parents = []

    def __init__(self, obj_name, parents: List[str]) -> None:
        super().__init__()
        self.obj_type = 'commit'
        self.obj_name = obj_name
        self.parents = parents


class Ref(Object):
    name = None
    dest = None
    upstream_name = None

    @property
    def target(self):
        return self.dest if self.obj_type == 'tag' else self

    @property
    def local_branch_name(self):
        if self.name.startswith(const.LOCAL_BRANCH_PREFIX):
            return self.name[len(const.LOCAL_BRANCH_PREFIX):]
        return None

    @property
    def unqualified_name(self):
        if self.name.startswith(const.LOCAL_BRANCH_PREFIX):
            return self.name[len(const.LOCAL_BRANCH_PREFIX):]
        if self.name.startswith(const.REMOTES_PREFIX):
            remote_branch_name = self.name[len(const.REMOTES_PREFIX):]
            unqualified_name_start = remote_branch_name.find('/')
            if unqualified_name_start < 0 or unqualified_name_start == 0:
                raise RuntimeError("invalid remote ref")
            remote_branch_name = remote_branch_name[unqualified_name_start + 1:]
            return remote_branch_name
        return None

    @property
    def remote_branch_name(self):
        if self.name.startswith(const.REMOTES_PREFIX):
            return self.name[len(const.REMOTES_PREFIX):]
        return None

    @property
    def local_tag_name(self):
        if self.name.startswith(const.LOCAL_TAG_PREFIX):
            return self.name[len(const.LOCAL_TAG_PREFIX):]
        return None

    @property
    def local_name(self):
        return self.local_branch_name or self.local_tag_name

    @property
    def short_name(self):
        return self.local_branch_name or self.local_tag_name or self.remote_branch_name

    @property
    def remote(self):
        if self.name.startswith(const.REMOTES_PREFIX):
            remote = self.name[len(const.REMOTES_PREFIX):]
            remote = remote[:remote.find('/')]
            return remote
        return None

    def __eq__(self, other):
        return isinstance(other, Ref) and self.name == other.name

    def __ne__(self, other):
        return not self.__eq__(other)


def ref_target(ref: Union[Object, str, list]):
    if isinstance(ref, str):
        return ref
    elif isinstance(ref, Ref):
        return ref.target.obj_name
    elif isinstance(ref, Object):
        return ref.obj_name
    elif isinstance(ref, list):
        return create_ref_name(*ref)
    else:
        raise ValueError('invalid type: ' + str(type(ref).__name__))


def ref_name(ref: Union[Ref, str, list]):
    if isinstance(ref, str):
        return ref
    elif isinstance(ref, Ref):
        return ref.name
    elif isinstance(ref, list):
        return create_ref_name(*ref)
    else:
        raise ValueError('invalid type: ' + str(type(ref).__name__))


def create_local_branch_name(name):
    elements = list(filter(lambda element: len(element) > 0, name.split('/')))
    if elements[:2] == ['refs', 'remotes']:
        return create_ref_name(*elements[3:])
    if elements[:2] == ['refs', 'heads']:
        return create_ref_name(*elements[2:])
    return None


def create_local_branch_ref_name(name):
    elements = list(filter(lambda element: len(element) > 0, name.split('/')))
    if elements[:2] == ['refs', 'remotes']:
        return create_ref_name(*(['refs', 'heads'] + elements[3:]))
    if elements[:2] == ['refs', 'heads']:
        return create_ref_name(*elements)
    return None


def create_remote_branch_ref_name(remote: Optional[str], name: str):
    elements = list(filter(lambda element: len(element) > 0, name.split('/')))
    if elements[:2] == ['refs', 'remotes']:
        if remote is not None:
            return create_ref_name(*(['refs', 'remotes', remote] + elements[3:]))
        else:
            return create_ref_name(*elements)
    if elements[:2] == ['refs', 'heads']:
        if remote is not None:
            return create_ref_name(*(['refs', 'remotes', remote] + elements[2:]))
        else:
            return create_ref_name(*(['refs', 'remotes', remote] + elements[2:]))
    return None


def create_ref_name(*strings: str):
    return utils.split_join('/', False, False, *strings)


def git_raw(git: str, args: list, verbose: int, dir: str = None) -> typing.Tuple[int, bytes, bytes]:
    command = [git]
    if dir is not None:
        command.extend(['-C', dir])

    for index, arg in enumerate(args):
        if isinstance(arg, Ref):
            args[index] = arg.name

    command.extend(args)

    if verbose >= const.TRACE_VERBOSITY:
        cli.print(utils.command_to_str(command))

    env = os.environ.copy()
    env["LANGUAGE"] = "C"
    env["LC_ALL"] = "C"
    if verbose >= const.TRACE_VERBOSITY:
        proc = subprocess.Popen(args=command,
                                stdin=subprocess.PIPE,
                                stdout=subprocess.PIPE,
                                cwd=dir,
                                env=env)
    else:
        proc = subprocess.Popen(args=command,
                                stdin=subprocess.PIPE,
                                stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE,
                                cwd=dir,
                                env=env)

    out, err = proc.communicate()
    if proc.returncode != os.EX_OK:
        if verbose >= const.TRACE_VERBOSITY:
            cli.eprint("command failed: " + utils.command_to_str(command))
            cli.eprint("child process returned " + str(proc.returncode))
            if err is not None:
                cli.eprint(err.decode("utf-8"))
    return proc.returncode, out, err


def git(context: RepoContext, *args) -> typing.Tuple[int, bytes, bytes]:
    return git_raw(git=context.git, args=list(args), dir=context.dir, verbose=context.verbose)


def git_in_cwd(context: RepoContext, *args) -> typing.Tuple[int, bytes, bytes]:
    """executes git without an explicit location"""
    return git_raw(git=context.git, args=list(args), dir=None, verbose=context.verbose)


def git_interactive(context: RepoContext, *args) -> subprocess.Popen:
    command = [context.git]
    if context.use_root_dir_arg:
        command.extend(['-C', context.dir])
    command.extend(args)

    for index, arg in enumerate(command):
        if isinstance(arg, Ref):
            command[index] = arg.name

    if context.verbose >= const.TRACE_VERBOSITY:
        cli.print(' '.join(shlex.quote(token) for token in command))

    return subprocess.Popen(args=command,
                            cwd=context.dir if not context.use_root_dir_arg else None)


def git_clone(context: RepoContext, target_dir: str, remote: Remote = None, branch: Union[Ref, str] = None):
    if remote is None:
        remote = git_get_remote(context, 'origin')
    elif isinstance(remote, str):
        remote = git_get_remote(context, remote)

    if remote is None:
        return None

    command = ['clone', '--reference', context.dir]
    if branch is not None:
        command.extend(['--branch', branch.short_name if isinstance(branch, Ref) else branch])
    command.extend([remote.url, target_dir])

    repo = RepoContext()
    repo.verbose = context.verbose
    returncode, out, err = git(repo, *command)

    if returncode != os.EX_OK:
        return None

    repo.dir = target_dir

    return repo


def git_export(context: RepoContext, target_dir: str, object: Union[Ref, str] = None) -> [RepoContext, None]:
    clone_command = ['clone', '--depth', '1', '--shallow-submodules', '--no-checkout', context.dir, target_dir]

    repo = RepoContext()
    repo.dir = target_dir
    repo.verbose = context.verbose
    returncode, out, err = git(repo, *clone_command)

    if returncode != os.EX_OK:
        return None

    checkout_command = ['checkout']
    if object is not None:
        checkout_command.extend([object])
    else:
        checkout_command.extend(['master'])

    returncode, out, err = git(repo, *checkout_command)

    if returncode != os.EX_OK:
        return None

    repo.dir = target_dir

    return repo


def git_for_lines(context: RepoContext, *args) -> Union[List[str], None]:
    returncode, out, err = git(context, *args)

    if returncode == os.EX_OK:
        return __extract_lines(context, out)
    return None


def git_for_line(context: RepoContext, *args):
    returncode, out, err = git(context, *args)

    if returncode == os.EX_OK:
        return __extract_line(context, out)
    return None


def __extract_lines(context, out):
    return out.decode("utf-8").splitlines()


def __extract_line(context, out):
    lines = __extract_lines(context, out)
    lines = [line for line in lines if line]
    if lines is not None and len(lines) == 1:
        return lines[0]
    else:
        if context.verbose >= const.TRACE_VERBOSITY and lines is not None:
            cli.eprint("Read an invalid number of lines: " + str(len(lines)))
        return None


def git_version(context: RepoContext):
    returncode, out, err = git_in_cwd(context, '--version')

    line = None
    if returncode == os.EX_OK:
        line = __extract_line(context, out)

    if line is None:
        return None
    version_match = re.fullmatch(r'(?:(?:git|version|\s+)+?\s+)?(\d+\.\d+\.\d+).*', line)
    if version_match is None:
        return None
    return version_match.group(1)


def git_get_remote(context: RepoContext, remote_name: str) -> Remote:
    returncode, out, err = git(context, 'remote', 'get-url', remote_name)

    if returncode == os.EX_OK:
        lines = out.decode("utf-8").splitlines()
        if len(lines) == 1:
            remote = Remote()
            remote.name = remote_name
            remote.url = lines[0]
            return remote


class BranchSelection(Enum):
    BRANCH_PREFER_LOCAL = 0,
    BRANCH_LOCAL_ONLY = 1,
    BRANCH_PREFER_REMOTE = 2,
    BRANCH_REMOTE_ONLY = 3,


def get_branch_by_name(context: RepoContext, remotes: typing.Set[str], branch_name: str,
                       search_mode: BranchSelection) -> Ref:
    candidate = None
    for branch in git_list_refs(context, *const.LOCAL_AND_REMOTE_BRANCH_PREFIXES):
        match = re.fullmatch(const.BRANCH_PATTERN, branch.name)

        name = match.group('name')
        remote = match.group('remote')

        if remote is not None and remotes is not None and remote not in remotes:
            continue

        local = remote is None

        if match and name == branch_name:
            if search_mode == BranchSelection.BRANCH_PREFER_LOCAL:
                candidate = branch
                if local:
                    break
            elif search_mode == BranchSelection.BRANCH_LOCAL_ONLY:
                if local:
                    candidate = branch
                    break
            if search_mode == BranchSelection.BRANCH_PREFER_REMOTE:
                candidate = branch
                if not local:
                    break
            elif search_mode == BranchSelection.BRANCH_REMOTE_ONLY:
                if not local:
                    candidate = branch
                    break

    return candidate


def git_get_current_branch(context: RepoContext) -> Ref:
    ref = Ref()
    ref.name = git_rev_parse(context, '--revs-only', '--symbolic-full-name', 'HEAD')
    ref.obj_type = 'commit'  # TODO always correct?
    ref.obj_name = git_rev_parse(context, 'HEAD')
    return ref if ref.name is not None else None


def git_list_refs(context: RepoContext, *args):
    """
    :rtype: list of Ref
    """

    returncode, out, err = git(context, 'for-each-ref', '--format',
                               '%(refname);%(objecttype);%(objectname);%(*objecttype);%(*objectname);%(upstream)',
                               *args)

    if returncode == os.EX_OK:
        for ref_element in out.decode("utf-8").splitlines():
            ref_element = ref_element.split(';')

            ref = Ref()
            ref.name = ref_element[0]
            ref.obj_type = ref_element[1]
            ref.obj_name = ref_element[2]
            if len(ref_element[4]):
                ref.dest = Object()
                ref.dest.obj_type = ref_element[3] if len(ref_element[3]) else None
                ref.dest.obj_name = ref_element[4] if len(ref_element[4]) else None
            if len(ref_element[5]):
                ref.upstream_name = ref_element[5]
            yield ref


def get_ref_by_name(context: RepoContext, ref_name):
    refs = list(git_list_refs(context, ref_name))
    if len(refs) == 1:
        return refs[0]
    elif len(refs) == 0:
        return None
    else:
        raise ValueError("multiple refs")


def git_get_upstreams(context: RepoContext, *args) -> Optional[dict]:
    returncode, out, err = git(context, 'for-each-ref', '--format',
                               '%(refname);%(upstream)',
                               *args)

    if returncode == os.EX_OK:
        upstreams = dict()
        for ref_elements in out.decode("utf-8").splitlines():
            ref_elements = ref_elements.split(';')

            assert len(ref_elements[0])

            if ref_elements[0] in upstreams:
                raise KeyError
            upstreams[ref_elements[0]] = ref_elements[1] if len(ref_elements[1]) else None
        return upstreams
    return None


def git_rev_parse(context: RepoContext, *args) -> Optional[str]:
    command = ['rev-parse']
    command.extend(args)

    returncode, out, err = git(context, *command)

    lines = out.decode('utf-8').splitlines()

    if returncode == os.EX_OK and len(lines) == 1:
        return lines[0]
    return None


def git_list_remote_branches(context: RepoContext, remote: str) -> list:
    """
    :rtype: list of Ref
    """
    return git_list_refs(context, create_ref_name(const.REMOTES_PREFIX, remote))


def git_list_branches(context: RepoContext) -> list:
    """
    :rtype: list of Ref
    """
    return git_list_refs(context, *const.LOCAL_AND_REMOTE_BRANCH_PREFIXES)


def git_get_tag_map(context: RepoContext):
    if context.tags is None:
        context.tags = dict()
        for tag_ref in list(git_list_refs(context, const.LOCAL_TAG_PREFIX)):
            tagged_commit = tag_ref.target.obj_name
            commit_tags = context.tags.get(tagged_commit)
            if commit_tags is None:
                context.tags[tagged_commit] = commit_tags = list()
            commit_tags.append(tag_ref)
    return context.tags


def git_list_tags(context: RepoContext):
    return git_get_tag_map(context).values()


def git_get_tags_by_referred_object(context: RepoContext, obj_name: str) -> list:
    """
    :param context:
    :param obj_name:
    :rtype: list of Ref
    """
    commit_tags = git_get_tag_map(context).get(obj_name)
    return commit_tags if commit_tags is not None else []


def git_merge_base(context: RepoContext, base: Union[Object, str], ref: Optional[Union[Object, str]],
                   determine_fork_point=False) -> Optional[str]:
    command = ['merge-base']
    if determine_fork_point:
        command.append('--fork-point')
    command += [
        ref_target(base),
        ref_target(ref),
    ]

    returncode, out, err = git(context, *command)

    if returncode == os.EX_OK:
        lines = out.splitlines()
        if len(lines) == 1:
            return lines[0].decode('utf-8')
    return None


def git_list_commits(context: RepoContext, start: Union[Object, str, None], end: Union[Object, str], reverse=False,
                     options: list = None) -> typing.Iterable:
    """"
    :returns branch commits in reverse chronological order
    :rtype: list of str
    """

    args = ['rev-list']
    if reverse:
        args.append('--reverse')
    args.append('--parents')
    if options is not None:
        args.extend(options)
    args.append((ref_target(start) + '..' if start is not None else '') + ref_target(end))

    returncode, out, err = git(context, *args)

    def commit_line_to_object(line: str) -> Object:
        hashes = line.split()
        return Commit(hashes[0], hashes[1:] if len(hashes) > 1 else [])

    commits = [commit_line_to_object(line) for line in out.decode('utf-8').splitlines()]
    if start is not None:
        start_obj = Object()
        start_obj.obj_type = "commit"
        start_obj.obj_name = ref_target(start)
        if reverse:
            return itertools.chain([start_obj], commits)
        else:
            return itertools.chain(commits, [start_obj])
    else:
        return commits


def git_get_branch_commits(context: RepoContext,
                           base_branch: Union[Object, str],
                           branch_commit: Union[Object, str]) -> typing.Generator[Commit, None, None]:
    """"
    :returns branch commits in reverse chronological order
    :rtype: list of str
    """

    # TODO optimize
    base_branch_commits = git_list_commits(context=context, start=None, end=base_branch, options=['--first-parent'])
    base_branch_commits = set([commit.obj_name for commit in base_branch_commits])

    commit_buffer = []

    for commit in git_list_commits(context=context,
                                   start=None,
                                   end=branch_commit,
                                   reverse=False,
                                   options=const.BRANCH_COMMIT_SCAN_OPTIONS):

        commit_buffer.append(commit)

        # a candidate for the original fork point has a parent that is reachable
        # from the base branch through first parents.
        if any(parent_commit in base_branch_commits for parent_commit in commit.parents):
            # yield all buffered commits
            yield from commit_buffer
            commit_buffer.clear()


def git_get_branch_tags(context: RepoContext,
                        base_branch: Union[Object, str],
                        branch: Union[Object, str],
                        tag_filter: Callable[[Ref, Ref], int] = None,
                        commit_tag_comparator: Callable[[Ref, Ref], int] = None) \
        -> typing.Generator[typing.Tuple[Commit, typing.List[Ref]], None, None]:
    for commit in git_get_branch_commits(
            context=context,
            base_branch=base_branch,
            branch_commit=branch):
        tag_refs = git_get_tags_by_referred_object(context, commit.obj_name)

        if commit_tag_comparator is not None:
            # copy and sort
            tag_refs = list(tag_refs)
            tag_refs.sort(key=utils.cmp_to_key(commit_tag_comparator), reverse=False)

        if tag_refs is not None:
            selected_tag_refs = list()
            for tag_ref in tag_refs:
                if tag_ref is not None and (tag_filter is None or tag_filter(tag_ref)):
                    selected_tag_refs.append(tag_ref)

            yield commit, selected_tag_refs


def git_tag(context: RepoContext, tag_name: str, obj: Union[Object, str]) -> bool:
    returncode, out, err = git(context, 'tag', tag_name, ref_target(obj))

    # invalidate cached tags
    context.tags = None

    return returncode == os.EX_OK


def git_branch(context: RepoContext, tag_name: str, obj: Union[Object, str]) -> bool:
    returncode, out, err = git(context, 'branch', tag_name, ref_target(obj))

    return returncode == os.EX_OK


class TreeEntry(object):
    file_flags: str
    object_type: str
    object_hash: str
    object_size: str
    file_path: str


def get_file_entry(context: RepoContext, object: Object, path: str) -> TreeEntry:
    files = git_for_lines(context, *['ls-tree', '-rlz', object, path])

    if files is None:
        raise RuntimeError("File lookup failed")

    if len(files) == 0:
        raise FileNotFoundError("Not such file: " + path)
    elif len(files) > 1:
        raise FileNotFoundError("Not a unique regular file: " + path)
    else:
        entry = TreeEntry()

        parts = files[0].split('\t')
        assert len(parts) == 2

        attrs = parts[0].split()
        assert len(attrs) == 4

        assert parts[1][-1] == '\0'
        parts[1] = parts[1][:-1]

        entry.file_flags = attrs[0]
        entry.object_type = attrs[1]
        entry.object_hash = attrs[2]
        entry.object_size = attrs[3]
        entry.file_path = parts[1]

        return entry


def get_file_entry_contents(context: RepoContext, tree_entry: TreeEntry):
    returncode, out, err = git(context, *['cat-file', 'blob', tree_entry.object_hash])

    return out if returncode == os.EX_OK else None


def get_file_contents(context: RepoContext, commit_object: Union[Object, str], file_path: str):
    entry = get_file_entry(context, commit_object, file_path)
    if entry is None:
        return None

    return get_file_entry_contents(context, entry)
