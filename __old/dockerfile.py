
import os
import re
import pwd
import yaml
import traceback
import subprocess
import grp
import hashlib
import time
from docker.models.images import Image
from docker.models.containers import Container
from pathlib import Path
from textwrap import dedent
from enum import Enum
from docker_cache import client
from git import Repo
from git.exc import InvalidGitRepositoryError
from git.diff import Diff

from common import root, error, warning, owner_hash

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

class DockerfileState(Enum):
    READY = 0
    EMPTY = 1
    OUTDATED = 2

class CommandState(Enum):
    EMPTY = 0
    STOPPED = 1
    RUNNING = 2

class Command:

    name: str
    dockerfile: 'Dockerfile'
    directories: list[str]
    container: Container | None = None

    def __init__(self, name: str, dockerfile: 'Dockerfile', directories: list[str]):
        self.name = name
        self.dockerfile = dockerfile
        self.directories = directories
        containers = client.containers.list(all=True, filters={'label': [
            f'my_dockers_name={self.name}',
            f'my_dockers_owner={owner_hash}',
            ]})
        if len(containers) == 0:
            self.container = None
        else:
            if len(containers) > 1:
                error(f'Too many containers assigned to command "{self.name}". Dispose them to fix it.')
            self.container = containers[0]

    def get_state(self):
        if self.container is None:
            return CommandState.EMPTY
        status = self.container.status
        if status == 'exited':
            return CommandState.STOPPED
        elif status == 'paused': # TODO: maybe support pause?
            return CommandState.STOPPED
        else:
            return CommandState.RUNNING

    def start(self):
        if self.dockerfile.image is None:
            error(f'No image to use for this command. Build it first with:\n    {self.name} -build')
            return False
        if self.container is None:
            volumes = [ dir + ':' + dir for dir in self.directories ]
            volumes.append('/dev/bus/usb/:/dev/bus/usb')
            container: Container = client.containers.run(
                image=self.dockerfile.image,
                command=[ 'sleep', 'infinity' ],
                privileged=True,
                detach=True,
                volumes=volumes,
                name=self.name.replace('/', '_'),
                labels={
                    'my_dockers_name': self.name,
                    'my_dockers_owner': owner_hash,
                })
            subprocess.run([
                'docker', 'cp',
                str((Path(__file__).parent / 'my-dockers-start').absolute()),
                container.id + ':/usr/bin/my-dockers-start',
            ], check=True)
            self.container = container
            self.container.exec_run(['chmod', '+x', '/usr/bin/my-dockers-start'])
            status = 'running'

        status = self.container.status

        retry_count = 30
        while status == 'restarting' and retry_count > 0:
            time.sleep(300)
            retry_count -= 1

        if status in ('created', 'exited'):
            self.container.start()
        elif status == 'running':
            pass # Nothing to do, already running
        elif status == 'paused':
            self.container.unpause()
        else: # status in ('restarting', 'removing', 'dead'):
            error(f'The container is {status}. Cannot be started now.')
            return False
        return True


    def stop(self):
        if self.container is not None:
            self.container.stop()


    def exec(self, *args, **kwargs):
        if not self.start():
            return False
        if len(args) == 0:
            args = [ 'bash' ]
        run_args = [
            'docker', 'exec',
            '-it',
            '-e', f'_MY_DOCKERS_PWD={Path.cwd()}',
            self.container.id,
            'my-dockers-start',
        ]
        run_args.extend(args)
        print(run_args)
        try:
            res = subprocess.run(run_args)
        except:
            pass
        print('RES:::', res)
        return True

    def is_up_to_date(self): # TODO: Need to detect if directories have changed
        if self.container is None:
            return True
        if self.container.image is None:
            return False
        if self.dockerfile.image is None:
            return False
        return self.container.image.id == self.dockerfile.image.id

    def __str__(self) -> str:
        return f'{self.name} from {self.dockerfile.name} sharing {", ".join(self.directories)}'

    def __repr__(self) -> str:
        return f'<{self.__class__.__name__} {self.__str__()}>'

class Dockerfile:

    docker_path: Path
    yaml_path: Path
    name: str
    commands: list[Command] | None = None
    image: Image | None = None
    sources_hash: str | None = None

    def __init__(self, name: str, docker_path: Path, yaml_path: Path):
        self.name = name
        self.docker_path = docker_path
        self.yaml_path = yaml_path
        if not yaml_path.exists():
            yaml_path.write_text(YAML_COMMENT)
        images = client.images.list(filters={ 'label': f'my_dockers_name={name}' }) # TODO: filter also by owner hash
        images = [ img for img in images if len(img.tags) > 0 ]
        if len(images) == 0:
            self.image = None
        else:
            self.image = images[0]
            for img in images:
                for tag in img.tags:
                    if tag.endswith(':latest'):
                        self.image = img

    def list_commands(self):
        if self.commands is None:
            self.commands = []
            try:
                with open(self.yaml_path, 'r') as f:
                    cmd_dict = yaml.load(f, Loader=yaml.FullLoader)
            except BaseException as ex:
                warning(f'Cannot parse yaml file: {ex}', traceback.format_exc())
                return []
            if cmd_dict is None:
                return []
            if not isinstance(cmd_dict, dict):
                warning(f'The yaml file "{self.yaml_path}" must contains a dictionary at top level.')
                return []
            for name, directories in cmd_dict.items():
                if isinstance(directories, str):
                    directories = [ directories ]
                self.commands.append(Command(name, self, directories))
        return self.commands

    def get_sources_hash(self): # TODO: Hash also "EXTEND" section of yaml
        if self.sources_hash is None:
            hash = hashlib.sha256()
            # hash of docker file
            cnt = self.docker_path.read_bytes()
            cnt = re.sub(rb'(\r?\n)(?:\s*(?:#[^\r\n]*)?\r?\n)+', b'\\1', cnt)
            cnt = cnt.strip()
            hash.update(cnt)
            try:
                repo = Repo(self.docker_path.parent / 'scripts', search_parent_directories=True)
                repo_root = Path(repo.working_dir)
                for commit in repo.iter_commits():
                    break
                else:
                    warning(f'Could not find any commit for "{self.docker_path}".')
                files_set: set[str] = set()
                for base in (None, commit):
                    for item in repo.index.diff(base):
                        item: Diff
                        if item.a_path is not None: files_set.add(item.a_path)
                        if item.b_path is not None: files_set.add(item.b_path)
                files_set.update(repo.untracked_files)
                files = [ file for file in files_set if not file.lower().endswith('.dockerfile') ]
                files.sort()
                # hash commit hash
                hash.update(commit.binsha)
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
                warning(f'File "{self.docker_path}" is not tracked by the git. The "up to date" may be inaccurate.', traceback.format_exc())
            except BaseException as ex:
                error(f'Unknown error when getting repository state: {ex}', traceback.format_exc())
            self.sources_hash = hash.hexdigest()
        return self.sources_hash

    def get_state(self) -> DockerfileState:
        if self.image is None:
            return DockerfileState.EMPTY
        if ('my_dockers_hash' not in self.image.labels) or (self.image.labels['my_dockers_hash'] != self.get_sources_hash()):
            return DockerfileState.OUTDATED
        return DockerfileState.READY # TODO: outdated

    def build(self):
        res = subprocess.run([
            'docker', 'build',
            '-f', str(self.docker_path),
            '-t', self.name.replace('/', '_'),
            '--label', f'my_dockers_name={self.name}',
            '--label', f'my_dockers_owner={owner_hash}',
            '--label', f'my_dockers_hash={self.get_sources_hash()}',
            '--build-arg', f'UI={os.getuid()}',
            '--build-arg', f'UN={pwd.getpwuid(os.getuid()).pw_name}',
            '--build-arg', f'GI={os.getgid()}',
            '--build-arg', f'GN={grp.getgrgid(os.getgid()).gr_name}',
            '.'
        ], cwd=self.docker_path.parent)
        if res.returncode != 0:
            error(f'Build failed with {res.returncode}')
            return False
        Dockerfile.prune()
        return True

    def __str__(self) -> str:
        return f'{self.name} from {self.docker_path}'

    def __repr__(self) -> str:
        return f'<{self.__class__.__name__} {self.__str__()}>'

    @staticmethod
    def prune():
        pass # TODO: delete all images that are not used by any dockerfile or container

    @staticmethod
    def list():
        result: list[Dockerfile] = []
        for dir in root.glob('*'):
            if not dir.is_dir(): continue
            if dir == 'scripts': continue
            for file in Dockerfile._list_from_dir(dir):
                rel = str(file.relative_to(dir)).replace('\\', '/')
                rel = re.sub(r'\.Dockerfile$', '', rel, flags=re.IGNORECASE)
                yaml_path = dir / (rel + '.yaml')
                name = dir.name + '/' + rel
                result.append(Dockerfile(name, file, yaml_path))
        return result

    @staticmethod
    def _list_from_dir(dir: Path):
        file_list: list[Path] = []
        for file in dir.glob('**/*'):
            if not file.name.lower().endswith('.dockerfile'): continue
            file_list.append(file)
        return file_list

def _test():
    for d in Dockerfile.list():
        print(d)
        print(d.get_state())
        print(d.get_sources_hash())
        for c in d.list_commands():
            print('COMMAND:', c)
            print('get_state', c.get_state())
            print('is_up_to_date', c.is_up_to_date())
            print(c.stop())
            break
        break

if __name__ == '__main__':
    _test()