
import sys
from common import ExpectedError, SilentError, error
from control import build, stop, dispose, dispose_image, execute, global_status


class Action:
    EXECUTE = '[execute]'
    BUILD = '-build'
    STOP = '-stop'
    DISPOSE = '-dispose'
    DISPOSE_IMAGE = '-dispose-image'


def run_action(command_name: str, action: str, args: list[str], quiet_mode: bool):
    if action == Action.EXECUTE:
        execute(command_name, args, quiet_mode)
    elif action == Action.BUILD:
        build(command_name, quiet_mode)
    elif action == Action.STOP:
        stop(command_name, quiet_mode)
    elif action == Action.DISPOSE:
        dispose(command_name, quiet_mode)
    elif action == Action.DISPOSE_IMAGE:
        dispose_image(command_name, quiet_mode)


def main(command_name: str = ''):

    try:
        if command_name == '':
            global_status()
        else:
            quiet_mode: bool = False
            action: str = Action.EXECUTE
            arg_index = 1
            for arg_index in range(1, len(sys.argv)):
                arg = sys.argv[arg_index]
                if not arg.startswith('-'):
                    break
                if arg.startswith('--'):
                    arg = arg[1:]
                if arg == '-q':
                    quiet_mode = True
                elif arg in ('-d', '-del', '-delete'):
                    action = Action.DISPOSE
                elif arg in ('-del-img', '-delete-img', '-del-image', '-delete-image'):
                    action = Action.DISPOSE_IMAGE
                elif arg in ('-s', '-stop'):
                    action = Action.STOP
                elif arg in ('-b', '-build'):
                    action = Action.BUILD
                else:
                    raise SilentError(f'Unknown option "{arg}".')
            args = sys.argv[arg_index:]
            run_action(command_name, action, args, quiet_mode)
    except ExpectedError as ex:
        if len(str(ex)) > 0:
            error(str(ex))
        exit(ex.code)
    except SilentError as ex:
        if len(str(ex)) > 0:
            print(str(ex), file=sys.stderr)
        exit(ex.code)


if __name__ == '__main__':
    main()
