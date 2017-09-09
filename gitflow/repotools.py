import itertools
import os
import re
import shlex
import subprocess
from enum import Enum
from typing import Union, Callable

from gitflow import const, utils

BRANCH_PATTERN = '(?P<parent>refs/heads/|refs/remotes/(?P<remote>[^/]+)/)(?P<name>.+)'


class RepoContext(object):
    git = 'git'
    dir = '.'
    tags = None  # dict
    verbose = False  # TODO use parent context


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


def ref_target(ref: Union[Object, str, list] or Object):
    if isinstance(ref, str):
        return ref
    elif isinstance(ref, Ref):
        return ref.target.obj_name
    elif isinstance(ref, Object):
        return ref.obj_name
    elif isinstance(ref, list):
        return utils.split_join('/', False, False, *ref)
    else:
        raise ValueError('invalid type: ' + str(type(ref).__name__))


def ref_name(ref: Union[Ref, str, list] or Object):
    if isinstance(ref, str):
        return ref
    elif isinstance(ref, Ref):
        return ref.name
    elif isinstance(ref, list):
        return utils.split_join('/', False, False, *ref)
    else:
        raise ValueError('invalid type: ' + str(type(ref).__name__))


def git(context: RepoContext, *args) -> subprocess.Popen:
    command = [context.git]
    if context.dir is not None:
        command.extend(['-C', context.dir])
    command.extend(args)
    for index, arg in enumerate(command):
        if isinstance(arg, Ref):
            command[index] = arg.name

    if context.verbose >= const.TRACE_VERBOSITY:
        print(' '.join(shlex.quote(token) for token in command))

    env = os.environ.copy()
    env["LANGUAGE"] = "C"
    env["LC_ALL"] = "C"
    if context.verbose >= const.TRACE_VERBOSITY:
        return subprocess.Popen(args=command,
                                stdin=subprocess.PIPE,
                                stdout=subprocess.PIPE,
                                env=env)
    else:
        return subprocess.Popen(args=command,
                                stdin=subprocess.PIPE,
                                stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE,
                                env=env)


def git_interactive(context: RepoContext, *args) -> subprocess.Popen:
    command = [context.git, '-C', context.dir]
    command.extend(args)
    for index, arg in enumerate(command):
        if isinstance(arg, Ref):
            command[index] = arg.name

    if context.verbose >= const.TRACE_VERBOSITY:
        print(' '.join(shlex.quote(token) for token in command))

    return subprocess.Popen(args=command)


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
    proc = git(repo, *command)
    proc.wait()

    if proc.returncode != os.EX_OK:
        return None

    repo.dir = target_dir

    return repo


def git_for_lines(context: RepoContext, *args):
    proc = git(context, *args)
    out, err = proc.communicate()

    if proc.returncode == os.EX_OK:
        return out.decode("utf-8").splitlines()
    return None


def git_for_line(context: RepoContext, *args):
    lines = git_for_lines(context, *args)
    return lines[0] if lines is not None and len(lines) == 1 else None


def git_version(context: RepoContext):
    line = git_for_line(context, '--version')
    if line is None:
        return None
    version_match = re.fullmatch(r'(?:(?:git|version|\s+)+?\s+)?(\d+(?:\.\d+)*[a-zA-Z0-9.+\-]*)\s*', line)
    if version_match is None:
        return None
    return version_match.group(1)


def git_get_remote(context: RepoContext, remote_name: str):
    proc = git(context, 'remote', 'get-url', remote_name)
    out, err = proc.communicate()

    if proc.returncode == os.EX_OK:
        lines = out.decode("utf-8").splitlines()
        if len(lines) == 1:
            remote_name = Remote()
            remote_name.name = remote_name
            remote_name.url = lines[0]
            return remote_name
    return None


class BranchSelection(Enum):
    BRANCH_PREFER_LOCAL = 0,
    BRANCH_LOCAL_ONLY = 1,
    BRANCH_PREFER_REMOTE = 2,
    BRANCH_REMOTE_ONLY = 3,


def get_branch_by_name(context: RepoContext, branch_name: str, search_mode: BranchSelection):
    candidate = None
    for branch in git_list_branches(context):
        match = re.fullmatch(BRANCH_PATTERN, branch.name)

        name = match.group('name')
        local = match.group('remote') is None

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


def git_list_refs(context: RepoContext, *args) -> list:
    """
    :rtype: list of Ref
    """

    proc = git(context, 'for-each-ref', '--format',
               '%(refname);%(objecttype);%(objectname);%(*objecttype);%(*objectname);%(upstream)',
               *args)
    out, err = proc.communicate()

    if proc.returncode == os.EX_OK:
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


def git_get_upstreams(context: RepoContext, *args) -> dict:
    proc = git(context, 'for-each-ref', '--format',
               '%(refname);%(upstream)',
               *args)
    out, err = proc.communicate()

    if proc.returncode == os.EX_OK:
        upstreams = dict()
        for ref_elements in out.decode("utf-8").splitlines():
            ref_elements = ref_elements.split(';')

            assert len(ref_elements[0])

            if ref_elements[0] in upstreams:
                raise KeyError
            if not len(ref_elements[1]):
                ref_elements[1] = None
            upstreams[ref_elements[0]] = ref_elements[1]
        return upstreams
    return None


def git_rev_parse(context: RepoContext, *args) -> str:
    command = ['rev-parse']
    command.extend(args)

    proc = git(context, *command)
    out, err = proc.communicate()

    lines = out.decode('utf-8').splitlines()

    if proc.returncode == os.EX_OK and len(lines) == 1:
        return lines[0]
    return None


def git_list_remote_branches(context: RepoContext, remote: str) -> list:
    """
    :rtype: list of Ref
    """
    return git_list_refs(context, 'refs/remotes/' + remote + '/')


def git_list_branches(context: RepoContext) -> list:
    """
    :rtype: list of Ref
    """
    return git_list_refs(context, 'refs/remotes/', 'refs/heads/')


def git_get_tag_map(context: RepoContext):
    if context.tags is None:
        context.tags = dict()
        for tag_ref in list(git_list_refs(context, 'refs/tags/')):
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


def git_merge_base(context: RepoContext, base: Union[Object, str], ref: Union[Object, str],
                   determine_fork_point=False) -> str:
    command = ['merge-base']
    if determine_fork_point:
        command.append('--fork-point')
    command += [
        ref_target(base),
        ref_target(ref),
    ]

    proc = git(context, *command)
    out, err = proc.communicate()

    if proc.returncode == os.EX_OK:
        lines = out.splitlines()
        if len(lines) == 1:
            return lines[0].decode('utf-8')
    return None


def git_list_commits(context: RepoContext, start: Union[Object, str], end: Union[Object, str], reverse=False):
    """"
    :returns branch commits in reverse chronological order
    :rtype: list of str
    """

    args = ['rev-list']
    if reverse:
        args.append('--reverse')
    args.append((ref_target(start) + '..' if start is not None else '') + ref_target(end))

    proc = git(context, *args)
    out, err = proc.communicate()

    commits = out.decode('utf-8').splitlines()
    if start is not None:
        if reverse:
            return itertools.chain([ref_target(start)], commits)
        else:
            return itertools.chain(commits, [ref_target(start)])
    else:
        return commits


def git_get_branch_commits(context: RepoContext, base: Union[Object, str], obj: Union[Object, str],
                           from_fork_point=False, reverse=False) -> list:
    """"
    :returns branch commits in reverse chronological order
    :rtype: list of str
    """

    merge_base = git_merge_base(context, base, obj, from_fork_point)

    if merge_base is None:
        return []

    return git_list_commits(context, merge_base, obj, reverse)


def git_get_branch_tags(context: RepoContext,
                        base: Union[Object, str],
                        dest: Union[Object, str],
                        from_fork_point=False,
                        reverse=False,
                        tag_filter: Callable[[Ref, Ref], int] = None,
                        commit_tag_comparator: Callable[[Ref, Ref], int] = None):
    for commit in git_get_branch_commits(context, base, dest, from_fork_point, reverse):
        tag_refs = git_get_tags_by_referred_object(context, commit)

        if commit_tag_comparator is not None:
            # copy and sort
            tag_refs = list(tag_refs)
            tag_refs.sort(key=utils.cmp_to_key(commit_tag_comparator), reverse=False)

        if tag_refs is not None:
            for tag_ref in tag_refs:
                if tag_ref is not None and (tag_filter is None or tag_filter(tag_ref)):
                    yield tag_ref


def git_tag(context: RepoContext, tag_name: str, obj: Union[Object, str]) -> bool:
    proc = git(context, 'tag', tag_name, ref_target(obj))
    out, err = proc.communicate()

    # invalidate cached tags
    context.tags = None

    return proc.returncode == os.EX_OK


def git_branch(context: RepoContext, tag_name: str, obj: Union[Object, str]) -> bool:
    proc = git(context, 'branch', tag_name, ref_target(obj))
    out, err = proc.communicate()

    return proc.returncode == os.EX_OK
