#!/bin/bash

echo '***WARNING*** This script is deprecated (use PyTest instead!)'

rm \
    *.interp \
    *.tokens \
    *.class \
    *.java \
    2> /dev/null  # ignore errors (e.g. when there is no such file or dir)
