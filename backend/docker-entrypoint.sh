#!/bin/sh
set -eu

export SUMO_HOME="$(python -c 'import sumo; print(sumo.SUMO_HOME)')"
export PATH="$SUMO_HOME/bin:$PATH"

exec "$@"