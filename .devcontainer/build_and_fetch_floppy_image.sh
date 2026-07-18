#!/bin/sh
CONTAINER_IMAGE_TAG=nlmbuild:0.1
# Could be `docker`, `podman`, or perhaps others.
OCI_TOOL=podman

${OCI_TOOL} build -f Dockerfile . --progress=plain -t ${CONTAINER_IMAGE_TAG}

# With thanks t Igor Bukanov on StackOverflow, see https://stackoverflow.com/a/31316636
id=$(${OCI_TOOL} create ${CONTAINER_IMAGE_TAG})
${OCI_TOOL} cp "$id":/nlm_disk.img ~/Downloads/nlm_disk.img
sync
${OCI_TOOL} rm -v "$id"
