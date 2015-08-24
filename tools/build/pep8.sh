#!/usr/bin/env bash

scriptDir=$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )

printf "Nr of PEP 8 errors/warnings remaining to be fixed\n"
pep8 --count -qq --filename="*" ${scriptDir}/../../bin
pep8 --count -qq ${scriptDir}/../..

printf "Now looking for errors that will break the build\n"
# We will remove more and more errors over time. We don't want them all at one time to avoid mental overload.
exclude_errors="E402,E712,E713,W291,W503,W601"

pep8 --count --statistics --filename="*" --ignore="${exclude_errors}" ${scriptDir}/../../bin
result1=$?
pep8 --count --statistics --ignore=${exclude_errors} ${scriptDir}/../..
result2=$?

if [ ${result1} != 0 ] || [ ${result2} != 0 ] ; then
    exit 1
fi