#!/usr/bin/env bash
set -e

scriptDir=$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )

# Static code ananlysis
. ${scriptDir}/pep8.sh

# Unit tests
# TODO

# Packaging
# TODO