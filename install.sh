#!/bin/bash
set -e

SCRIPT_DIR=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )

if [[ "$1" != "--OK" ]]; then
    if [[ "$(basename $SCRIPT_DIR)" != "scripts" ]]; then
        mv $SCRIPT_DIR $SCRIPT_DIR-_tmp_
        mkdir $SCRIPT_DIR
        mv $SCRIPT_DIR-_tmp_ $SCRIPT_DIR/scripts
        $SCRIPT_DIR/scripts/install.sh --OK
        exit
    fi
fi

cd $SCRIPT_DIR
rm -Rf .venv
python3 -m venv .venv
source $SCRIPT_DIR/.venv/bin/activate
pip install -r $SCRIPT_DIR/requirements.txt
python3 command_entry.py
mkdir -p $SCRIPT_DIR/data

echo Successful Installation
echo
echo You have successfully installed my-dockers. Edit the following file
echo to add your commands:
echo
echo     `realpath $SCRIPT_DIR/../commands.yaml`
echo
