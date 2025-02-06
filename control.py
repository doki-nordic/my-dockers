
import os
import sys
import re
import pwd
import traceback
import subprocess
import grp
import hashlib
import time
import docker
import tempfile
from getpass import getpass
from docker.models.images import Image
from docker.models.containers import Container
from pathlib import Path
from textwrap import dedent
from git import Repo
from git.exc import InvalidGitRepositoryError
from git.diff import Diff
from common import error, warning, data_dir, ExpectedError, SilentError, UninitializedClass, uninitialized, get_command_path, C, create_command, root
from config_loader import load_config, ConfigEntry, config


client = docker.from_env()


commands: 'dict[str, Command]' = {}

class ContainerStatus:
    CREATED = 'created'
    RUNNING = 'running'
    PAUSED = 'paused'
    RESTARTING = 'restarting'
    REMOVING = 'removing'
    EXITED = 'exited'
    DEAD = 'dead'

pretty_status = {
    'created': f'{C.Blue}[Created]{C.N}',
    'running': f'{C.Green}[Running]{C.N}',
    'paused': f'{C.Yellow}[Paused]{C.N}',
    'restarting': f'{C.Yellow}[Restarting]{C.N}',
    'removing': f'{C.Yellow}[Removing]{C.N}',
    'exited': f'{C.Blue}[Exited]{C.N}',
    'dead': f'{C.Red}[Dead]{C.N}',
}

class Command:

    name: str
    dockerfile: Path
    share: list[Path]
    append: str
    options: dict
    prompt: 'dict[str, str]'
    password: 'dict[str, str]'
    prebuild: str
    postbuild: str
    line: int | None
    container: UninitializedClass | Container | None = uninitialized
    image: UninitializedClass | Image | None = uninitialized
    sources_hash: UninitializedClass | str = uninitialized

    def __init__(self, name: str, command_config: ConfigEntry):
        self.name = name
        self.dockerfile = command_config.dockerfile
        self.share = command_config.share
        self.append = command_config.append
        self.options = command_config.options
        self.prompt = command_config.prompt
        self.password = command_config.password
        self.prebuild = command_config.prebuild
        self.postbuild = command_config.postbuild
        self.line = command_config.line

    def get_tag(self):
        return 'my-dockers-' + self.name

    def get_image(self) -> Image | None:
        if self.image is not uninitialized:
            return self.image
        images = client.images.list(filters={ 'label': f'my_dockers_name={self.name}' })
        images = [ img for img in images if len(img.tags) > 0 ]
        if len(images) == 0:
            self.image = None
        else:
            self.image = images[0]
            for img in images:
                for tag in img.tags:
                    if tag.endswith(':latest'):
                        self.image = img
        return self.image
    
    def get_container(self) -> Container | None:
        if self.container is not uninitialized:
            return self.container
        containers = client.containers.list(all=True, filters={'label': [ f'my_dockers_name={self.name}' ]})
        if len(containers) == 0:
            self.container = None
        else:
            if len(containers) > 1:
                error(f'Too many containers assigned to command "{self.name}". Delete theirs containers to fix it: {self.name} -d')
            self.container = containers[0]
        return self.container

    def get_sources_hash(self) -> str:
        if self.sources_hash is not uninitialized:
            return self.sources_hash
        hash = hashlib.sha256()
        # Hash docker file (without empty lines)
        cnt = self.dockerfile.read_bytes()
        cnt = re.sub(rb'(\r?\n)(?:\s*(?:#[^\r\n]*)?\r?\n)+', b'\\1', cnt)
        cnt = cnt.strip()
        hash.update(cnt)
        # Hash docker file extended
        hash.update(self.append.encode())
        hash.update(self.prebuild.encode())
        hash.update(self.postbuild.encode())
        # Hash rest of the files based on git status
        try:
            # Create Repo object
            repo = Repo(self.dockerfile.parent, search_parent_directories=True)
            repo_root = Path(repo.working_dir)
            # Get checked out commit and hash its hash
            for commit in repo.iter_commits():
                break
            else:
                warning(f'Could not find any commit for "{self.dockerfile}".')
            hash.update(commit.binsha)
            # Get all touched and untracked files
            files_set: set[str] = set()
            files_set.update(repo.untracked_files)
            for base in (None, commit):
                for item in repo.index.diff(base):
                    item: Diff
                    if item.a_path is not None: files_set.add(item.a_path)
                    if item.b_path is not None: files_set.add(item.b_path)
            # Skip other docker files
            files = [ file for file in files_set if not file.lower().endswith('.dockerfile') ]
            # Sort to make the results consistent
            files.sort()
            # hash changed and untracked files
            for file in files:
                hash.update(b'<<<' + file.encode())
                file_path = Path(repo_root / file)
                if file_path.exists():
                    hash.update(b'+>>>')
                    with open(file_path, 'rb') as fd:
                        while True:
                            chunk = fd.read(1024 * 1024)
                            if len(chunk) == 0: break
                            hash.update(chunk)
                else:
                    hash.update(b'!>>>')
        except InvalidGitRepositoryError as ex:
            warning(f'File "{self.dockerfile}" is not tracked by the git. The "up to date" state may be inaccurate.', traceback.format_exc())
        except BaseException as ex:
            error(f'Unknown error when getting repository state: {ex}', traceback.format_exc())
        self.sources_hash = hash.hexdigest()
        return self.sources_hash


def reload():
    load_config()
    commands.clear()
    for command_name, command_config in config.items():
        commands[command_name] = Command(command_name, command_config)

def get_command(command_name: str) -> Command:
    if command_name not in commands:
        raise ExpectedError(f'Command "{command_name}" not found in the configuration.')
    return commands[command_name]

def prompt(message: str, question: str, options: str):
    message = dedent(message).strip()
    opt = list(options.lower())
    default = [ x.lower() for x in options if x == x.upper() ][0]
    print(message)
    res = ''
    while res not in opt:
        res = input(question + ' ') or default
        res = res[0].lower()
    return res

def run_bash_script(script: str, env: 'dict[str, str]'):
    if not script:
        return
    new_env = os.environ.copy()
    new_env.update(env)
    name = None
    with tempfile.NamedTemporaryFile(mode='w+t', delete=False) as temp_file:
        temp_file.write(f'#/bin/bash\nset -e\n{script}\n')
        temp_file.close()
        name = Path(temp_file.name)
        name.chmod(0o755)
        res = subprocess.run(['bash', str(name)], env=new_env)
    try:
        if name is not None: name.unlink()
    except:
        pass
    if res.returncode != 0:
        raise ExpectedError(f'Pre-build or post-build script failed with code {res.returncode}.', res.returncode)

def build(command_name: str, quiet_mode: bool):
    command = get_command(command_name)
    old_image = command.get_image()
    old_container = command.get_container()
    if old_container is not None and not quiet_mode:
        response = prompt(f'''
                The container for "{command_name}" exists. Building image will delete
                it and all its content.
                ''',
                'Do you want to continue [Y/n]?', 'Yn')
        if response == 'n':
            raise SilentError('Canceled by user.')
    docker_file_text = command.dockerfile.read_text() + '\n' + command.append
    dockerfile = (data_dir / (command.name + '.Dockerfile'))
    dockerfile.write_text(docker_file_text)
    prompt_args = []
    secret_kwargs = {}
    script_vars = {
        'MY_DOCKERS_COMMAND': command.name,
        'MY_DOCKERS_DOCKERFILE': command.dockerfile,
        'MY_DOCKERS_CONFIG': root / 'commands.yaml',
        'MY_DOCKERS_TAG': command.get_tag(),
    }
    for key, text in command.prompt.items():
        value = input(f'{text}: ')
        prompt_args.append('--build-arg')
        prompt_args.append(f'{key}={value}')
        script_vars[f'PROMPT_{key}'] = value
    for key, text in command.password.items():
        value = getpass(f'{text}: ')
        prompt_args.append('--secret')
        prompt_args.append(f'id={key},env=MY_DOCKER_SECRET_{key}')
        if 'env' not in secret_kwargs:
            secret_kwargs['env'] = os.environ.copy()
        secret_kwargs['env'][f'MY_DOCKER_SECRET_{key}'] = value
        script_vars[f'PASSWORD_{key}'] = value
    run_bash_script(command.prebuild, script_vars)
    res = subprocess.run([
        'docker', 'buildx', 'build',
        '-f', str(dockerfile),
        '-t', command.get_tag(),
        '--label', f'my_dockers_name={command.name}',
        '--label', f'my_dockers_hash={command.get_sources_hash()}',
        '--build-arg', f'UI={os.getuid()}',
        '--build-arg', f'UN={pwd.getpwuid(os.getuid()).pw_name}',
        '--build-arg', f'GI={os.getgid()}',
        '--build-arg', f'GN={grp.getgrgid(os.getgid()).gr_name}',
        *prompt_args,
        '.'
    ], cwd=command.dockerfile.parent, **secret_kwargs)
    if res.returncode != 0:
        raise ExpectedError(f'Build failed with code {res.returncode}.', res.returncode)
    run_bash_script(command.postbuild, script_vars)
    new_image = command.get_image()
    if old_container is not None:
        old_container.remove(force=True)
    if old_image is not None and new_image.id != old_image.id:
        old_image.remove(force=True)

def start(command_name: str, quiet_mode: bool):
    command = get_command(command_name)
    image = command.get_image()
    if image is None:
        build(command_name, quiet_mode)
        reload()
        command = get_command(command_name)
        image = command.get_image()
        if image is None:
            raise ExpectedError(f'Cannot get image for command "{command_name}".')
    container: 'Container | None' = command.get_container()
    if container is None:
        volumes = [ f'{dir}:{dir}' for dir in command.share ]
        volumes.append('/dev/bus/usb/:/dev/bus/usb')
        container = client.containers.run(
            image=image.id,
            command=[ 'sleep', 'infinity' ],
            privileged=True,
            detach=True,
            volumes=volumes,
            name=command.get_tag(),
            labels={ 'my_dockers_name': command.name },
            **command.options
            )
        subprocess.run([
            'docker', 'cp',
            str((Path(__file__).parent / 'my-dockers-start').absolute()),
            container.id + ':/usr/bin/my-dockers-start',
        ], check=True)
        container.exec_run(['chmod', '+x', '/usr/bin/my-dockers-start'])

    retry_count = 30
    while container.status == ContainerStatus.RESTARTING and retry_count > 0:
        time.sleep(300)
        retry_count -= 1

    if container.status == ContainerStatus.RUNNING:
        pass # Nothing to do, already running
    elif container.status in (ContainerStatus.CREATED, ContainerStatus.EXITED):
        container.start()
    elif container.status == ContainerStatus.PAUSED:
        container.unpause()
    else: # container.status in (restarting, removing, dead):
        raise ExpectedError(f'The container is {container.status}. Cannot be started now.')


def stop(command_name: str, quiet_mode: bool):
    command = get_command(command_name)
    container = command.get_container()
    if container is None:
        return

    retry_count = 30
    while container.status == ContainerStatus.RESTARTING and retry_count > 0:
        time.sleep(300)
        retry_count -= 1

    if container.status == ContainerStatus.PAUSED:
        container.unpause()
    if container.status in (ContainerStatus.RUNNING, ContainerStatus.PAUSED):
        container.stop(timeout=1)


def dispose(command_name: str, quiet_mode: bool):
    command = get_command(command_name)
    container = command.get_container()
    if container is None:
        return
    if not quiet_mode:
        response = prompt(f'''
                You will loose all changes made in the "{command_name}" container.
                ''',
                'Do you want to continue [Y/n]?', 'Yn')
        if response == 'n':
            raise SilentError('Canceled by user.')
    container.remove(force=True)

def dispose_image(command_name: str, quiet_mode: bool):
    dispose(command_name, quiet_mode)
    reload()
    command = get_command(command_name)
    image = command.get_image()
    if image is not None:
        image.remove(force=True)

def execute(command_name: str, args: list[str], quiet_mode: bool):
    command = get_command(command_name)
    container = command.get_container()
    if container is None or container.status != ContainerStatus.RUNNING:
        start(command_name, quiet_mode)
        reload()
        command = get_command(command_name)
        container = command.get_container()
        if container is None:
            raise ExpectedError(f'Cannot find container associated with command "{command_name}".')
    if len(args) == 0:
        args = [ 'bash' ]
    run_args = [
        'docker', 'exec',
        '-it',
        '-e', f'_MY_DOCKERS_PWD={Path.cwd()}',
        container.id,
        'my-dockers-start',
    ]
    run_args.extend(args)
    res = subprocess.run(run_args)
    if res.returncode != 0:
        raise SilentError('', res.returncode)

def print_status():
    print(f'\nConfiguration file: {root / "commands.yaml"}')
    commands_to_update = []
    for command in commands.values():
        print()
        print(f'{command.name}')
        # Container
        container = command.get_container()
        if container is not None:
            print(f'        Container:  {pretty_status[container.status] if container.status in pretty_status else container.status} {container.short_id} {container.name}')
        else:
            print(f'        Container:  {C.Yellow}[Deleted]{C.N}')
        # Image
        image = command.get_image()
        if image is not None:
            if 'my_dockers_hash' not in image.labels or image.labels['my_dockers_hash'] != command.get_sources_hash():
                print(f'        Image:      {C.Red}[Outdated]{C.N} {image.short_id} {", ".join(image.tags)}')
                commands_to_update.append(command.name)
            else:
                print(f'        Image:      {C.Green}[Up-to-date]{C.N} {image.short_id} {", ".join(image.tags)}')
        else:
            print(f'        Image:      {C.Yellow}[Deleted]{C.N}')
        # Executable
        command_path = get_command_path(command.name)
        if command_path is not None:
            print(f'        Executable: {command_path}')
        else:
            print(f'        Executable: {C.Red}Unavailable{C.N}')
        # Dockerfile
        print(f'        Dockerfile: {command.dockerfile}{" (customized in yaml file)" if command.append else ""}')
        # Share
        label = 'Share:'
        for dir in command.share:
            print(f'        {label}      {dir}')
            label = '      '
        if command.line is not None:
            print(f'        Config:     {root / "commands.yaml"}:{command.line}')
        else:
            print(f'        Config:     {root / "commands.yaml"}')
    return commands_to_update


def global_status():
    try:
        create_command('my-dockers', Path(__file__).parent / 'command_entry.py', 'main')
    except ExpectedError as ex:
        error(str(ex))
    except:
        error(f'Error creating executable file for command "my-dockers".')
    for command in commands.values():
        try:
            create_command(command.name, Path(__file__).parent / 'command_entry.py', 'main', command.name)
        except ExpectedError as ex:
            error(str(ex))
        except:
            error(f'Error creating executable file for command "{command.name}".')

    commands_to_update = print_status()

    if len(commands_to_update) > 0:
        response = prompt(f'''
            You have some images that are out of date.
            ''',
            'Do you want to rebuild them [Y/n]?', 'Yn')
        if response == 'n':
            commands_to_update = []
        for command_name in commands_to_update:
            try:
                build(command_name, False)
                reload()
            except ExpectedError as ex:
                if len(str(ex)) > 0:
                    error(str(ex))
            except SilentError as ex:
                if len(str(ex)) > 0:
                    print(str(ex), file=sys.stderr)
        if len(commands_to_update) > 0:
            print_status()

reload()


if __name__ == '__main__':
    global_status()
