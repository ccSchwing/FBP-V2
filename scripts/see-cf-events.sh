#!/bin/bash

watch -n 5 aws cloudformation describe-stack-events \
  --stack-name fbp \
  --query "StackEvents[*].ResourceStatus" \
  --output table
