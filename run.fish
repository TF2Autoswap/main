#!/usr/bin/env fish
#
# run.fish — run TF2autoswap from the project's own virtualenv.
#
# Usage:
#     ./run.fish [any arguments accepted by tf2autoswap.py]
#
# Creates the virtualenv on first use and installs the project into it, then
# passes every argument straight through. It runs the virtualenv interpreter
# directly rather than activating the environment. Activation in fish means
# sourcing a script, which is not what the bash instructions in most guides
# describe, and running the interpreter avoids the question entirely.

set -l script_dir (path resolve (dirname (status current-filename)))
set -l venv_dir $script_dir/venv
set -l venv_python $venv_dir/bin/python

if not test -x $venv_python
    echo "No virtualenv found; creating one in $venv_dir ..."
    if not python3 -m venv $venv_dir
        echo "Could not create a virtualenv. Is python3 available?" >&2
        exit 1
    end
    if not $venv_python -m pip install -q -e $script_dir
        echo "Could not install the project into $venv_dir." >&2
        exit 1
    end
end

# A virtualenv can predate the declared dependencies, so check rather than
# assume: an environment built before they were declared would otherwise fail
# later inside tf2_core with a missing 'vpk' and no obvious cause.
if not $venv_python -c "import vpk" >/dev/null 2>&1
    echo "Installing dependencies into $venv_dir ..."
    if not $venv_python -m pip install -q -e $script_dir
        echo "Could not install dependencies into $venv_dir." >&2
        exit 1
    end
end

exec $venv_python $script_dir/tf2autoswap.py $argv
