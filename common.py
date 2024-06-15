
import os
import sys
import json
import hashlib
from pathlib import Path
from textwrap import dedent

root: Path = Path(__file__).parent.parent
data_dir: Path = Path(__file__).parent / 'data'
owner_hash: str = hashlib.sha256(str(Path(__file__).parent.resolve()).encode()).hexdigest()

class ExpectedError(Exception):
    code: int
    def __init__(self, message: str, code: int = 99):
        super().__init__(message)
        self.code = code

class SilentError(Exception):
    code: int
    def __init__(self, message: str, code: int = 98):
        super().__init__(message)
        self.code = code

class UninitializedClass:
    pass

uninitialized = UninitializedClass()

class C:
    Black = '\033[90m'
    Red = '\033[91m'
    Green = '\033[92m'
    Yellow = '\033[93m'
    Blue = '\033[94m'
    Magenta = '\033[95m'
    Cyan = '\033[96m'
    White = '\033[97m'
    N = '\033[0m'

def warning(text: str, details: 'str|None' = None):
    print(f'{C.Yellow}WARNING: {text}{C.N}', file=sys.stderr)

def error(text: str, details: 'str|None' = None):
    print(f'{C.Red}ERROR: {text}{C.N}', file=sys.stderr)

def get_bin_dirs() -> list[Path]:
    def best_name(a: Path):
        score = len(str(a)) + a[0] / 1000
        if a[1].name in ('bin', 'sbin'): score -= 1000
        if a[1].parent.name.endswith('local'): score -= 1000
        return score
    result: list[tuple[int, Path]] = []
    prefix = str(Path.home().resolve()) + os.sep
    for dirStr in os.environ['PATH'].split(':'):
        try:
            dir = Path(dirStr).resolve()
        except:
            continue
        if not str(dir).startswith(prefix): continue
        if str(dir).find('env') >= 0: continue
        result.append((len(result), dir))
    if len(result) == 0:
        raise FileNotFoundError("No bin directories in the home directory.") # TODO: Print how to solve it.
    result.sort(key=best_name)
    seen = set()
    result2: list[Path] = []
    for x in result:
        if x[1] not in seen:
            seen.add(x[1])
            result2.append(x[1])
    return result2

def get_command_path(name: str):
    dirs = get_bin_dirs()
    for dir in dirs:
        try:
            file = dir / name
            if file.exists():
                return file
        except:
            pass
    return None

def create_command(name: str, script_file: 'Path|str', function_name: 'str|None', *parameters):
    script_file = Path(script_file)
    code = dedent(f'''
        #!{sys.executable}
        #my-docker-generated#
        import sys
        import json
        import importlib.util
        sys.path.insert(0, '{script_file.absolute().parent}')
        spec = importlib.util.spec_from_file_location('{script_file.stem}', '{Path(script_file).absolute()}')
        if spec is None:
            print(f'Required script file not found: {Path(script_file).absolute()}', file=sys.stderr)
            exit(99)
        mod = importlib.util.module_from_spec(spec)
        sys.modules['{script_file.stem}'] = mod
        if spec.loader is None:
            print(f'Loader for script file not available: {Path(script_file).absolute()}', file=sys.stderr)
            exit(99)
        spec.loader.exec_module(mod)
    ''').strip() + '\n'
    if function_name is not None:
        code += f'mod.{function_name}(*json.loads("""{json.dumps(parameters)}"""))\n'
    dirs = get_bin_dirs()
    last_error = None
    for dir in dirs:
        try:
            file = dir / name
            if file.exists():
                dirs = [ dir ]
                break
        except:
            pass
    for dir in dirs:
        try:
            file = dir / name
            if file.exists():
                if not file.is_file():
                    raise IOError(f'Cannot override "{name}" in directory "{str(dir)}".')
                with open(file, 'rb') as f:
                    head = f.read(512)
                if head.count(b'\n#my-docker-generated#\n') == 0:
                    raise IOError(f'Cannot override file "{name}" that was not created by my-dockers tool in directory "{str(dir)}".')
            file.write_text(code, encoding='utf8')
            file.chmod(0o755)
            break
        except BaseException as ex:
            last_error = ex
    else:
        raise last_error
