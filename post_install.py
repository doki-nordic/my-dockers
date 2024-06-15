
import common
from textwrap import dedent

common.create_command('my-dockers', 'main.py', 'main')

print(dedent('''
    Successful Installation

    You've successfully installed my-dockers. Run the following command
    to start the manager:

        my-dockers
'''))