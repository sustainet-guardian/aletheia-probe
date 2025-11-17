#!/bin/bash
#
# Runs cloc with the automatically generated files excluded

cloc --exclude-dir=.mypy_cache,htmlcov .
