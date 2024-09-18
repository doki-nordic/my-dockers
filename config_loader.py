
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
    # "append" is a string, empty by default, join list of strings if needed
    if 'append' not in command:
        command['append'] = ''
    elif isinstance(command['append'], list):
        for line in command['append']:
            if not isinstance(line, str):
                return f'Expecting string or list of strings in "append" entry in "{name}".'
        command['append'] = '\n'.join(command['append'])
    elif not isinstance(command['append'], str):
        return f'Expecting string or list of strings in "append" entry in "{name}".'
    # "options" is a dictionary, empty by default
    if 'options' not in command:
        command['options'] = dict()
    elif not isinstance(command['options'], dict):
        return f'Expecting object (dictionary) in "options" entry in "{name}".'
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
    except BaseException as ex:
        error(f'Cannot parse yaml file: {ex}', traceback.format_exc())
        raise
