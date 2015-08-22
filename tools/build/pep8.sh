#!/usr/bin/env bash

scriptDir=$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )

printf "Nr of PEP 8 errors/warnings remaining to be fixed\n"
pep8 --count -qq --filename="*" ${scriptDir}/../../bin
pep8 --count -qq ${scriptDir}/../..

printf "Now looking for errors that will break the build\n"
# We will remove more and more errors over time. We don't want them all at one time to avoid mental overload.
exclude_errors="E121,E126,E127,E128,E129,E251,E265,E266,E303,E401,E402,E501,E703,E711,E712,E713,W291,W503,W601"

pep8 --count --statistics --filename="*" --ignore="${exclude_errors}" ${scriptDir}/../../bin
result1=$?
pep8 --count --statistics --ignore=${exclude_errors} ${scriptDir}/../..
result2=$?

if [ ${result1} != 0 ] || [ ${result2} != 0 ] ; then
    exit 1
fi