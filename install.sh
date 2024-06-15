#!/bin/bash
set -e

SCRIPT_DIR=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )

cd $SCRIPT_DIR
rm -Rf .venv
rm -Rf scripts/tmp
python3 -m venv .venv
source $SCRIPT_DIR/.venv/bin/activate
pip install -r $SCRIPT_DIR/requirements.txt
python3 post_install.py
