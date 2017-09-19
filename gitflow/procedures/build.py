import os
import platform
import shutil
import subprocess
import tempfile

from gitflow import utils, _, repotools, cli, filesystem
from gitflow.context import Context
from gitflow.procedures import get_command_context, check_requirements, download_file


def call(context: Context):
    from urllib import parse
    import zipfile

    command_context = get_command_context(
        context=context,
        object_arg=utils.get_or_default(context.args, '<object>', None)
    )

    check_requirements(command_context=command_context,
                       ref=command_context.selected_ref,
                       modifiable=True,
                       with_upstream=True,  # not context.config.push_to_local
                       in_sync_with_upstream=True,
                       fail_message=_("Build failed.")
                       )

    remote = repotools.git_get_remote(context.repo, context.config.remote_name)
    if remote is None:
        cli.fail(os.EX_CONFIG, "missing remote \"" + context.config.remote_name + "\"")

    tempdir_path = tempfile.mkdtemp(prefix='gitflow_build_')
    os.chmod(path=tempdir_path, mode=0o700)

    cache_dir = filesystem.get_cache_dir(filesystem.build_tools_cache_dir)

    context.add_temp_dir(tempdir_path)

    gradle_module_name = 'gradle-3.5.1'
    gradle_dist_url = 'https://services.gradle.org/distributions/' + gradle_module_name + '-bin.zip'
    gradle_dist_hash_sha256 = '8dce35f52d4c7b4a4946df73aa2830e76ba7148850753d8b5e94c5dc325ceef8'

    repo_url = parse.urlparse(remote.url)
    repo_dir_name = repo_url.path.rsplit('/', 1)[-1]

    build_repo_path = os.path.join(tempdir_path, repo_dir_name)
    gradle_dist_archive_path = os.path.join(cache_dir, parse.urlparse(gradle_dist_url).path.rsplit('/', 1)[-1])

    gradle_dist_install_root = os.path.join(tempdir_path, 'buildtools')
    gradle_dist_install_path = os.path.join(gradle_dist_install_root, gradle_module_name)
    gradle_dist_bin_path = os.path.join(gradle_dist_install_path, 'bin')

    if os.path.exists(build_repo_path):
        shutil.rmtree(build_repo_path)

    repo = repotools.git_export(context.repo, build_repo_path, command_context.selected_ref)
    if repo is None:
        command_context.fail(os.EX_IOERR,
                    _("Failed to clone {remote}.")
                    .format(remote=repr(remote.url)),
                    None
                    )

    download_result = download_file(gradle_dist_url, gradle_dist_archive_path, gradle_dist_hash_sha256)
    command_context.add_subresult(download_result)

    if os.path.exists(gradle_dist_install_path):
        shutil.rmtree(gradle_dist_install_path)
    zip_ref = zipfile.ZipFile(gradle_dist_archive_path, 'r')
    zip_ref.extractall(gradle_dist_install_root)
    zip_ref.close()

    gradle_executable = os.path.join(gradle_dist_bin_path,
                                     "gradle.bat" if platform.system().lower() == "windows" else "gradle")

    st = os.stat(gradle_executable)
    os.chmod(gradle_executable, st.st_mode | 0o100)

    env = os.environ.copy()
    env['PATH'] += ':' + gradle_dist_bin_path

    gradle_command = [gradle_executable, '--no-daemon']
    if context.batch:
        gradle_command.append('--console=plain')
    if context.verbose:
        gradle_command.append('--info')
    gradle_command.append('app:assembleGenericDebug')

    gradle_process = subprocess.run(gradle_command,
                                    env=env,
                                    cwd=build_repo_path,
                                    # stdout=subprocess.PIPE,
                                    # stderr=subprocess.PIPE
                                    )
    # print(gradle_process.stdout)
    # print(gradle_process.stderr)


    return command_context.result