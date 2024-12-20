
import re
import sys
import yaml
import traceback
from pathlib import Path
from textwrap import dedent
from types import SimpleNamespace
from common import root, error, warning


YAML_COMMENT = dedent('''
    #
    # List of commands that will give you access to my-dockers containers.
    #
    # command_name: # This command will be available directly in the terminal.
    #   dockerfile: relative/path/to.Dockerfile
    #   share:
    #     # Optional. Can be also one string value instead of list.
    #     # The path will be mounted in docker at the same location as
    #     # in the host.
    #     - /path/to/shared/directory
    #     - /second/shared/directory
    #   append: |
    #     # Optional. String or list of strings that will be appended to
    #     # the end of Dockerfile. You can customize the docker with it.
    #     RUN git config --global user.name "Mona Lisa" && \\
    #         git config --global user.email Mona.Lisa@example.com
    #   options:
    #     # An object containing docker container run options.
    #     # See https://docker-py.readthedocs.io/en/stable/containers.html#docker.models.containers.ContainerCollection.run
    #     mem_limit: 2g
    #   prompt:
    #     # Ask user for input before building the image. Key is the argument passed to the
    #     # Dockerfile, value is a prompt message that user will see.
    #     DOWNLOAD_URL: Provide download URL
    #   password:
    #     # Ask user for password before building the image. Key is the secret id passed to the
    #     # Dockerfile, value is a prompt message that user will see.
    #     # Use "RUN --mount=type=secret" to get access to the secret.
    #     TOKEN: User token
    #   postbuild: |
    #     # Execute bash script after building the image. Available environment variables:
    #     # - MY_DOCKERS_COMMAND     The image is build for this my-dockers command.
    #     # - MY_DOCKERS_DOCKERFILE  The Dockerfile used.
    #     # - MY_DOCKERS_CONFIG      The "commands.yaml" file that contains this configuration.
    #     # - MY_DOCKERS_TAG         The output image tag.
    #     # - PROMPT_*               The value from "prompt" input.
    #     # - PASSWORD_*             The value from "password" input.
    #     # The current directory is not changed when script is executed.
    #     # If you want to make some changes to the image, create container from
    #     # $MY_DOCKERS_TAG image, execute commands in it and commit back as $MY_DOCKERS_TAG,
    #     $ for example:
    #     docker run --name tmp-cnt $MY_DOCKERS_TAG bash -c 'echo echo Docker started >> ~/.bashrc'
    #     docker commit tmp-cnt tmp-img
    #     docker container rm tmp-cnt
    #     docker rmi $MY_DOCKERS_TAG
    #     docker tag tmp-img $MY_DOCKERS_TAG
    #     docker rmi tmp-img
    #   prebuild: |
    #     # The same as "postbuild", but before the build.
    #     echo Starting image build...
    #
    # WARNING!!! After modifying command names, remember to do update with
    # the following command:
    #
    #     my-dockers
    #
    ''').strip() + '\n\n\n'


class ConfigEntry:
    dockerfile: Path
    share: list[Path]
    append: str
    options: dict
    prompt: 'dict[str, str]'
    password: 'dict[str, str]'
    prebuild: str
    postbuild: str


config: 'dict[str, ConfigEntry]' = {}


def validate_config_command(name, command):
    # Name is valid
    if not re.match(r'^[0-9a-z_](?:[0-9.a-z_-]*[0-9a-z_])?$', name, re.IGNORECASE):
        return f'Invalid command name: "{name}"'
    # Dockerfile entry exists and it is string
    if 'dockerfile' not in command or not isinstance(command['dockerfile'], str):
        return f'Invalid or missing "dockerfile" entry in "{name}".'
    # Dockerfile is existing file
    dockerfile: Path = root / command['dockerfile']
    if not dockerfile.is_file():
        return f'Dockerfile "{dockerfile}" from "{name}" not found.'
    command['dockerfile'] = dockerfile
    # "share" is a list, empty by default
    if 'share' not in command:
        command['share'] = []
    elif not isinstance(command['share'], list):
        command['share'] = [ command['share'] ]
    # "share" is a list of valid absolute existing directories
    new_share = []
    for dir in command['share']:
        if not isinstance(dir, str):
            return f'Expecting string or list of strings in "share" entry in "{name}".'
        path = Path(dir)
        if path.is_absolute() and path.is_dir():
            new_share.append(path)
        else:
            warning(f'Invalid share "{dir}" in "{name}".')
    command['share'] = new_share
    # "append", "prebuild" and "postbuild" are strings, empty by default, join list of strings if needed
    for opt in ('append', 'prebuild', 'postbuild'):
        if opt not in command:
            command[opt] = ''
        elif isinstance(command[opt], list):
            for line in command[opt]:
                if not isinstance(line, str):
                    return f'Expecting string or list of strings in "{opt}" entry in "{name}".'
            command[opt] = '\n'.join(command[opt])
        elif not isinstance(command[opt], str):
            return f'Expecting string or list of strings in "{opt}" entry in "{name}".'
    # "options" is a dictionary, empty by default
    if 'options' not in command:
        command['options'] = dict()
    elif not isinstance(command['options'], dict):
        return f'Expecting object (dictionary) in "options" entry in "{name}".'
    # "prompt" and "password" are dictionaries, empty by default
    for opt in ('prompt', 'password'):
        if opt not in command:
            command[opt] = dict()
        elif not isinstance(command[opt], dict):
            return f'Expecting object (dictionary) in "{opt}" entry in "{name}".'
        else:
            for value in command[opt].values():
                if not isinstance(value, str):
                    return f'Expecting string values in "{opt}" entry in "{name}".'
    return None


def validate_config(config, config_text):
    # Root is dict
    if not isinstance(config, dict):
        error('Expected a dictionary at top level of commands.yaml.')
        return {}
    new_config = {}
    for name, command in config.items():
        result = validate_config_command(name, command)
        if result is not None:
            error(result)
        else:
            new_config[name] = command
        parts = re.split(f'\n' + re.escape(name) + ':', config_text, 2)
        if len(parts) > 1:
            command['line'] = parts[0].count('\n') + 2
        else:
            command['line'] = None
    return new_config


def dict_to_simple_namespace(input):
    if isinstance(input, dict):
        new_dict = {}
        for key, value in input.items():
            new_dict[key] = dict_to_simple_namespace(value)
        return SimpleNamespace(**new_dict)
    type_construct = type(input)
    if type_construct in (set, list, tuple):
        return type_construct([dict_to_simple_namespace(x) for x in input])
    else:
        return input


def load_config():
    yaml_file = root / 'commands.yaml'
    if not yaml_file.exists():
        yaml_file.write_text(YAML_COMMENT)
    try:
        with open(yaml_file, 'r') as fd:
            config_raw = yaml.load(fd, Loader=yaml.FullLoader)
        with open(yaml_file, 'r') as fd:
            config_text = fd.read()
        if config_raw is None:
            print(f'No commands detected. Edit configuration in:\n{yaml_file}', file=sys.stderr)
            config_raw = {}
        config_raw = validate_config(config_raw, config_text)
        config.clear()
        for key in config_raw.keys():
            config[key] = dict_to_simple_namespace(config_raw[key])
            config[key].options = config_raw[key]['options']
            config[key].prompt = config_raw[key]['prompt']
            config[key].password = config_raw[key]['password']
    except BaseException as ex:
        error(f'Cannot parse yaml file: {ex}', traceback.format_exc())
        raise
