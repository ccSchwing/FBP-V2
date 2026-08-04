#!/bin/bash
#
#
set -e

AWS_PROFILE="${AWS_PROFILE:-ccs}"
export AWS_PROFILE

require_aws_credentials() {
	if ! aws sts get-caller-identity --profile "$AWS_PROFILE" >/dev/null 2>&1
	then
		echo "AWS credentials are not available for profile: $AWS_PROFILE"
		echo "Configure the ccs profile in this Codespace, or set AWS_PROFILE to another configured profile before running this script."
		exit 1
	fi
}

if [ $# -ne 1 ]
then
	echo "Usage: $(basename $0) schedule-file.csv"
	exit 1
else
	schedFile=$1
fi

require_aws_credentials

BUCKET="my-fbp.com"
SCHED_DIR="../schedule/2025-Schedule"

ls -l ${SCHED_DIR}

cd $SCHED_DIR

if [ -f $schedFile ]
then
	echo "Running aws cp on $schedFile to $BUCKET"
	aws s3 cp $schedFile s3://$BUCKET/schedule/2025-Schedule/$schedFile
	if [ $? -eq 0 ]
	then
		echo "$schedFile copied to s3 bucket: $BUCKET/schedule/2025-Schedule/$schedFile"
		exit 0
	else
		echo "aws s3 cp failed."
		exit 1
	fi
else
	echo "$(basename $0) cannot open $schedFile"
	exit 1
fi

