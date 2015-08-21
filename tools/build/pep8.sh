#!/usr/bin/env bash
set -e

scriptDir=$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )

# We will remove more and more errors over time. We don't want them all at one time to avoid mental overload.
exclude_errors="E111,E114,E122,E123,E126,E127,E128,E129,E201,E202,E203,E211,E222,E225,E226,E227,E228,E231,E241,E251,E261,E262,E265,E266,E301,E302,E303,E401,E402,E501,E701,E703,E711,E712,E713,W291,W292,W293,W391,W503,W601"

pep8 --statistics --filename="*" --ignore="${exclude_errors}" ${scriptDir}/../../bin
pep8 --statistics --ignore=${exclude_errors} ${scriptDir}/../..
