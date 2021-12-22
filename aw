#!/usr/bin/bash

# First, find what directory this script truly lives in by following symlinks
self=$0
while [[ -L "$self" ]]; do
		self=$(readlink $self)
done
dir=$(dirname "$self")

# Go to that directory (where we'll find our module)
PYTHONPATH="$PYTHONPATH":$dir exec python3 -m activewatch "$@"


