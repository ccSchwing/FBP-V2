#!/bin/bash

set -o errexit
set -o pipefail

if [ $# -ne 1 ]
then
	echo "Usage: $(basename $0) path to file -- e.g. schedule/2025-Schedule/week3-schedule.json"
	exit 1
fi

TARGET_BUCKET="my-fbp.com/schedule/2025-Schedule"
echo "Using TARGET_BUCKET: $TARGET_BUCKET"

fileName=$(basename $1)
echo "fileName:$fileName"
aws s3 cp ./$1 s3://$TARGET_BUCKET/$fileName \
  --content-type "application/json" \
  --cache-control "public, max-age=0, must-revalidate"
