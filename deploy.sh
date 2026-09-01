#!/usr/bin/env sh

METHOD="${1:-code}"
DEST="/run/media/matthewd/CIRCUITPY/"

if [ ! -d "$DEST" ]; then
    echo "Cannot find CIRCUITPY directory"
    echo "Looking for: $DEST"
    echo "(If this is wrong, please update $0)"
    exit 1
fi

if [ "$METHOD" = "code" ]; then
    cp ./src/*.py "$DEST"
fi

if [ "$METHOD" = "all" ]; then
   # sync everything except `code.py`
    rsync -rtv --delete --exclude='code.py' --modify-window=2 --inplace --size-only ./src/ "$DEST"
    sync

    # Now copy `code.py` to trigger reload
    cp ./src/code.py "$DEST"
fi