#!/usr/bin/env bash
set -e

scriptDir=$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )

# We will add more and more errors over time. We don't want them all at one time to avoid mental overload.
included_errors="E231"

pep8 --filename=* --statistics --select=${included_errors} ${scriptDir}/../../bin
pep8 --filename=**/bin/cfclient --statistics --select=${included_errors} ${scriptDir}/../..
