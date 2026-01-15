#!/bin/bash
#
# This creates a tar.gz file for the submission to arxiv.
#

set -e

BNAME=AletheiaProbe-short

TMPDIR=$(mktemp -d -t arXiv.XXXXXXX)
echo "Current temporary directory [${TMPDIR}]"

if test -z "${TMPDIR}"; then
    echo "*** PANIC: cannot create temp dir"
    exit
fi

bash build.sh

F2COPY="${BNAME}.tex
${BNAME}.bbl
${BNAME}.bib
SelfArx.cls"
cp ${F2COPY} ${TMPDIR}

GITVERSION=$(git describe --long --dirty --abbrev=16 --always)
TIMESTAMP=$(date "+%Y%m%d-%H%M%S")

echo "% Git Version: ${GITVERSION}" >>${TMPDIR}/${BNAME}.tex
echo "% Timestamp: ${TIMESTAMP}" >>${TMPDIR}/${BNAME}.tex

TARGET_NAME=arXiv-${TIMESTAMP}-${GITVERSION}.tar
tar -cf ${TARGET_NAME} -C ${TMPDIR} .
gzip -9 ${TARGET_NAME}

echo "Remove temporary directory [${TMPDIR}]"
rm -fr ${TMPDIR}
