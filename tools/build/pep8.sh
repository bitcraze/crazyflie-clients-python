#!/usr/bin/env bash

scriptDir=$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )

pep8 --count --statistics --filename="*" ${scriptDir}/../../bin
result1=$?
pep8 --count --statistics ${scriptDir}/../..
result2=$?

if [ ${result1} != 0 ] || [ ${result2} != 0 ] ; then
    echo "PEP-8 check fail"
    exit 1
else
    echo "PEP-8 check pass"
fi