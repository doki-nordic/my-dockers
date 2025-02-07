
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
    #   input:
    #     # Ask user for input before building the image. Key is the argument passed to the
    #     # Dockerfile, value is a prompt message that user will see. You can use it in Dockerfile,
    #     # post and pre build scripts, or any other configuration value. Configuration values allows Jinja2
    #     # templating, using <<{% ... %}>> for statements and <<{{ ... }}>> for expressions.
    #     DOWNLOAD_URL: Provide download URL
    #   password:
    #     # Ask user for password before building the image. Key is the secret id passed to the
    #     # Dockerfile, value is a prompt message that user will see.
    #     # Use "RUN --mount=type=secret" to get access to the secret.
    #     TOKEN: User token
    #   set:
    #     # Set any input to specific value. If value is set, user will not be asked for it.
    #     # Useful when you want to specify value in some different configuration file.
    #     # Load order of configuration files is significant, because the last one will overwrite
    #     # the previous ones.
    #     DOWNLOAD_URL: https://example.com/downloads/file.zip
    #   postbuild: |
    #     # Execute bash script after building the image. Available environment variables:
    #     # - MY_DOCKERS_COMMAND     The image is build for this my-dockers command.
    #     # - MY_DOCKERS_DOCKERFILE  The Dockerfile used.
    #     # - MY_DOCKERS_CONFIG      The "commands.yaml" file that contains this configuration.
    #     # - MY_DOCKERS_TAG         The output image tag.
    #     # - INPUT_*                The value from "input" input.
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
    #   load:
    #     # Load additional configuration file. If the file contains multiple entries, the entry
    #     # with the same name as the current command will be used. If just one, that one will be used.
    #     # There are two special values that can be used: "$dockerfile" will configuration from file
    #     # assigned to dockerfile entry, "$this" will load this configuration. If they are not provided,
    #     # the "$dockerfile" will be added to the beginning of the list, "$this" will be added to the end.
    #     - ./my-overrides.yaml
    #
    # WARNING!!! After modifying command names, remember to do update with
    # the following command:
    #
    #     my-dockers
    #
    ''').strip() + '\n\n\n'

class ConfigEntrySource:
    file: Path
    line: int

class ConfigEntry:
    dockerfile: Path
    share: list[Path]
    append: str
    options: dict
    input: 'dict[str, str]'
    password: 'dict[str, str]'
    prebuild: str
    postbuild: str
    set: 'dict[str, str]'
    load: list[str]
    sources: 'list[ConfigEntrySource]'


config: 'dict[str, ConfigEntry]' = {}


def validate_config_command(name, command):
    # Name is valid
    if not re.match(r'^[0-9a-z_](?:[0-9.a-z_-]*[0-9a-z_])?$', name, re.IGNORECASE):
        return f'Invalid command name: "{name}"'
    if 'dockerfile' in command:
        # Dockerfile is string
        if not isinstance(command['dockerfile'], str):
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
    # "input", "password", and "set" are dictionaries, empty by default
    for opt in ('input', 'password'):
        if opt not in command:
            command[opt] = dict()
        elif not isinstance(command[opt], dict):
            return f'Expecting object (dictionary) in "{opt}" entry in "{name}".'
        else:
            for value in command[opt].values():
                if not isinstance(value, str):
                    return f'Expecting string values in "{opt}" entry in "{name}".'
    # "load" is a list, empty by default
    if 'load' not in command:
    # There should be no "sources" at this point
    if 'sources' in command:
        raise ValueError(f'Unexpected "sources" entry in "{name}".')
    command['sources'] = []
    return None


def validate_config(config, config_text: str, yaml_file: Path):
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
            command['sources'].append({
                'file': yaml_file,
                'line': parts[0].count('\n') + 2
            })
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

def read_config_file(yaml_file: Path, command_name: 'str|None') -> 'dict[str, ConfigEntry]':
    try:
        # Read and parse yaml file
        with open(yaml_file, 'r') as fd:
            config_raw = yaml.load(fd, Loader=yaml.FullLoader)
        with open(yaml_file, 'r') as fd:
            config_text = fd.read()
        if config_raw is None:
            config_raw = {}
        # If specific command is requested, extract it
        if command_name is not None:
            if command_name in config_raw:
                config_raw = { command_name: config_raw[command_name] }
            elif len(config_raw) == 1:
                config_raw = { command_name: config_raw.popitem()[1] }
            else:
                error(f'Command "{command_name}" not found in "{yaml_file}".')
                raise ValueError()
        # Validate and convert to ConfigEntry
        config_raw = validate_config(config_raw, config_text, yaml_file)
        config = {}
        for key in config_raw.keys():
            config[key] = dict_to_simple_namespace(config_raw[key])
            config[key].options = config_raw[key]['options']
            config[key].input = config_raw[key]['input']
            config[key].password = config_raw[key]['password']
            config[key].set = config_raw[key]['set']
            config[key].load = config_raw[key]['load']
        return config
    except BaseException as ex:
        error(f'Cannot parse yaml file: {ex}', traceback.format_exc())
        raise

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
            config[key].input = config_raw[key]['input']
            config[key].password = config_raw[key]['password']
            config[key].set = config_raw[key]['set']
    except BaseException as ex:
        error(f'Cannot parse yaml file: {ex}', traceback.format_exc())
        raise
