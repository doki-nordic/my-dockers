#!/bin/bash
set -e

SCRIPT_DIR=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )

cd $SCRIPT_DIR
rm -Rf .venv
python3 -m venv .venv
source $SCRIPT_DIR/.venv/bin/activate
pip install -r $SCRIPT_DIR/requirements.txt
python3 command_entry.py

echo Successful Installation
echo
echo You have successfully installed my-dockers. Run the following command
echo to start the manager:
echo
echo     my-dockers
echo
