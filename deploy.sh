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
    rsync -av --delete ./src/ "$DEST"

    # Copy this again to retrigger reload
    cp ./src/*.py "$DEST"
fi