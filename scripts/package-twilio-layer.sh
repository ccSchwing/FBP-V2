#!/bin/bash

set -e

# Create the zip file
zip -r twilio-layer.zip python/

# Upload to S3 if needed
aws s3 cp twilio-layer.zip s3://my-fbp.com/layers/