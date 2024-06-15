

import os
import re
import pwd
import yaml
import traceback
import subprocess
import grp
import hashlib
import time
import itertools
from docker.models.images import Image
from docker.models.containers import Container
from pathlib import Path
from textwrap import dedent
from enum import Enum
from docker_cache import client
from git import Repo
from git.exc import InvalidGitRepositoryError
from git.diff import Diff
from types import SimpleNamespace
from common import root, error, warning, owner_hash, data_dir
from pprint import pprint

YAML_COMMENT = dedent('''
    #
    # List of commands that will give you access do docker containers from
    # associated Dockerfile. The format is:
    #
    # command_name
    #   - /directory/to/mount
    #   - /second/directory/to/mount
    #   ...
    #
    # or simply (for one directory):
    #
    # command_name: /directory/to/mount
    #
    # You can also extend content of the associated Dockerfile. For example:
    #
    # EXTEND: |
    #   RUN sudo apt install -y zsh
    #   ENV SHELL /bin/zsh
    #   RUN chsh -s /bin/zsh
    #
    # WARNING!!! After modifying this file, remember to do update with
    # the following command:
    #
    #     my-dockers
    #
    ''').strip() + '\n\n'

class UndefinedClass:
    pass

Undefined = UndefinedClass()

class DockerfileState(Enum):
    READY = 0
    EMPTY = 1
    OUTDATED = 2

class CommandState(Enum):
    EMPTY = 0
    STOPPED = 1
    RUNNING = 2


class MyImage(SimpleNamespace):

    name: str
    docker_file: Path
    extend_dockerfile: str | None
    commands: 'dict[str, MyCommand]'
    docker_image: Image | UndefinedClass | None = Undefined
    sources_hash: str | UndefinedClass = Undefined

    def get_tag_name(self) -> str:
        return 'my-dockers-' + self.name.replace('/', '-')
    
    def get_docker_image(self) -> Image | None:
        if self.docker_image is not Undefined:
            return self.docker_image
        images = client.images.list(filters={ 'label': f'my_dockers_name={self.name}' })
        images = [ img for img in images if len(img.tags) > 0 ]
        if len(images) == 0:
            self.docker_image = None
        else:
            self.docker_image = images[0]
            for img in images:
                for tag in img.tags:
                    if tag.endswith(':latest'):
                        self.docker_image = img
        return self.docker_image
    
    def get_sources_hash(self) -> str:
        if self.sources_hash is not Undefined:
            return self.sources_hash
        hash = hashlib.sha256()
        # Hash docker file (without empty lines)
        cnt = self.docker_file.read_bytes()
        cnt = re.sub(rb'(\r?\n)(?:\s*(?:#[^\r\n]*)?\r?\n)+', b'\\1', cnt)
        cnt = cnt.strip()
        hash.update(cnt)
        # Hash docker file extended
        hash.update((self.extend_dockerfile or '').encode())
        # Hash rest of the files based on git status
        try:
            # Create Repo object
            repo = Repo(self.docker_file.parent, search_parent_directories=True)
            repo_root = Path(repo.working_dir)
            # Get checked out commit and hash its hash
            for commit in repo.iter_commits():
                break
            else:
                warning(f'Could not find any commit for "{self.docker_file}".')
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
            warning(f'File "{self.docker_file}" is not tracked by the git. The "up to date" state may be inaccurate.', traceback.format_exc())
        except BaseException as ex:
            error(f'Unknown error when getting repository state: {ex}', traceback.format_exc())
        self.sources_hash = hash.hexdigest()
        return self.sources_hash



class MyCommand(SimpleNamespace):

    name: str
    image: MyImage
    shared_dirs: list[Path]
    docker_container: Container | UndefinedClass | None = Undefined
    state: CommandState | UndefinedClass = Undefined

    def get_tag(self) -> str:
        return 'my-dockers-' + self.name

    def get_docker_container(self) -> Container | None:
        if self.docker_container is not Undefined:
            return self.docker_container
        containers = client.containers.list(all=True, filters={'label': [ f'my_dockers_name={self.name}' ]})
        if len(containers) == 0:
            self.docker_container = None
        else:
            if len(containers) > 1:
                error(f'Too many containers assigned to command "{self.name}". Dispose them to fix it.')
            self.docker_container = containers[0]
        return self.docker_container

    def get_state(self) -> CommandState:
        if self.state is not Undefined:
            return self.state
        container = self.get_docker_container()
        if container is None:
            self.state = CommandState.EMPTY
        elif container.status in ('exited', 'paused'):
            self.state = CommandState.STOPPED
        else:
            self.state = CommandState.RUNNING
        return self.state

all_images: dict[str, MyImage] = {}
all_commands: dict[str, MyCommand] = {}


def initialize():
    all_images.clear()
    all_commands.clear()
    for dir in root.glob('*'):
        if not dir.is_dir(): continue
        if dir == 'scripts': continue
        for file in itertools.chain(dir.glob('**/*.dockerfile'), dir.glob('**/*.Dockerfile')):
            # Make image name
            rel = str(file.relative_to(dir)).replace('\\', '/')
            rel = re.sub(r'\.Dockerfile$', '', rel, flags=re.IGNORECASE)
            name = dir.name + '/' + rel
            # Read YAML file
            yaml_path = dir / (rel + '.yaml')
            if not yaml_path.exists():
                yaml_path.write_text(YAML_COMMENT)
            try:
                with open(yaml_path, 'r') as fd:
                    cmd_dict = yaml.load(fd, Loader=yaml.FullLoader)
            except BaseException as ex:
                error(f'Cannot parse yaml file: {ex}', traceback.format_exc())
                continue
            # Get docker file extended text
            if 'EXTEND' in cmd_dict:
                extend_dockerfile = cmd_dict['EXTEND']
                del cmd_dict['EXTEND']
            else:
                extend_dockerfile = None
            # Prepare commands dictionary for this image
            image_commands = {}
            # Put the image into the dictionary
            all_images[name] = MyImage(
                name=name,
                docker_file=file,
                extend_dockerfile=extend_dockerfile,
                commands=image_commands,
            )
            # Iterate over the commands
            for command_name, shared_dirs in cmd_dict.items():
                # Make sure shared dirs is a list of strings
                if isinstance(shared_dirs, str):
                    shared_dirs: list[str] = [ shared_dirs ]
                if not isinstance(shared_dirs, list) or len([None for dir in shared_dirs if not isinstance(dir, str)]):
                    error(f'Invalid data types in "{yaml_path}"')
                    continue
                # Check for command duplicates
                if command_name in all_commands:
                    error(f'Duplicated command "{command_name}".')
                    continue
                # Create command
                command = MyCommand(
                    name=command_name,
                    image=all_images[name],
                    shared_dirs=[ Path(dir) for dir in shared_dirs ],
                )
                # And put it into the dictionaries
                all_commands[command_name] = command
                image_commands[command_name] = command


def get_image(image_name: str) -> MyImage:
    if image_name not in all_images:
        error(f'Image name "{image_name}" not found.')
        raise ValueError('Image not found') # TODO: specific error type
    return all_images[image_name]

def get_command(command_name: str) -> MyCommand:
    if command_name not in all_commands:
        error(f'Command "{command_name}" not found.')
        raise ValueError('Image not found') # TODO: specific error type
    return all_commands[command_name]

def build_image(image_name: str) -> int:
    image = get_image(image_name)
    docker_file = image.docker_file
    if image.extend_dockerfile is not None:
        cnt = docker_file.read_text()
        cnt += '\n' + image.extend_dockerfile
        docker_file = (data_dir / (image.name + '.Dockerfile'))
        docker_file.write_text(cnt)
    res = subprocess.run([
        'docker', 'build',
        '-f', str(docker_file),
        '-t', image.get_tag_name(),
        '--label', f'my_dockers_name={image.name}',
        '--label', f'my_dockers_hash={image.get_sources_hash()}',
        '--build-arg', f'UI={os.getuid()}',
        '--build-arg', f'UN={pwd.getpwuid(os.getuid()).pw_name}',
        '--build-arg', f'GI={os.getgid()}',
        '--build-arg', f'GN={grp.getgrgid(os.getgid()).gr_name}',
        '.'
    ], cwd=image.docker_file.parent)
    initialize()
    image = get_image(image_name)
    if res.returncode != 0:
        error(f'Build failed with code {res.returncode}.')
        return res.returncode
    outdated_commands = []
    for command in image.commands.values():
        if command.get_state() != CommandState.EMPTY:
            outdated_commands.append(command.name)
    answer = '?'
    while len(outdated_commands) > 0 and answer not in ('y', 'n'):
        if len(outdated_commands) > 1:
            print(dedent(f'''
                The following commands are using previous version of the image:
                { ", ".join(outdated_commands) }
                Do you want to dispose them all now [Y/n]?'''), end='')
        else:
            print(dedent(f'''
                The "{outdated_commands[0]}" command is using previous version of the image.
                Do you want to dispose it now [Y/n]?'''), end='')
        answer = (input().lower().strip() + '?')[0]
    if answer == 'y':
        for command_name in outdated_commands:
            dispose_command(command_name)
        initialize()
    return 0


def dispose_command(command_name: str):
    command = get_command(command_name)
    container = command.get_docker_container()
    if container is not None:
        container.remove(force=True)

def stop_command(command_name: str):
    command = get_command(command_name)
    container = command.get_docker_container()
    if container is not None:
        container.stop(timeout=1)

def start_command(command_name: str):
    command = get_command(command_name)
    docker_image = command.image.get_docker_image()
    if docker_image is None:
        build_from_command(command_name)
        command = get_command(command_name)
        docker_image = command.image.get_docker_image()
        if docker_image is None:
            error(f'Cannot get image for command "{command_name}".')
            return False
    container = command.get_docker_container()
    if container is None:
        volumes = [ f'{dir}:{dir}' for dir in command.shared_dirs ]
        volumes.append('/dev/bus/usb/:/dev/bus/usb')
        container: Container = client.containers.run(
            image=command.image.get_docker_image().id,
            command=[ 'sleep', 'infinity' ],
            privileged=True,
            detach=True,
            volumes=volumes,
            name=command.get_tag(),
            labels={ 'my_dockers_name': command.name })
        subprocess.run([
            'docker', 'cp',
            str((Path(__file__).parent / 'my-dockers-start').absolute()),
            container.id + ':/usr/bin/my-dockers-start',
        ], check=True)
        container.exec_run(['chmod', '+x', '/usr/bin/my-dockers-start'])
        # "created" "running" "paused" "restarting" "removing" "exited" "dead"

    retry_count = 30
    while container.status == 'restarting' and retry_count > 0:
        time.sleep(300)
        retry_count -= 1

    if container.status == 'running':
        pass # Nothing to do, already running
    elif container.status in ('created', 'exited'):
        container.start()
    elif container.status == 'paused':
        container.unpause()
    else: # container.status in ('restarting', 'removing', 'dead'):
        error(f'The container is {container.status}. Cannot be started now.')
        return False
    return True

def exec_command(command_name: str, args: list[str]) -> int:
    command = get_command(command_name)
    if command.get_state() != CommandState.RUNNING:
        if not start_command(command_name):
            return 99
        initialize()
    command = get_command(command_name)
    container = command.get_docker_container()
    if container is None:
        error('Cannot find container associated with command "{command_name}"')
        return 99
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
    return res.returncode


def build_from_command(command_name: str):
    command = get_command(command_name)
    return build_image(command.image.name)

initialize()
dispose_command('ncs')
#print(exec_command('ncs', ['ls', 'sdfgsd']))
