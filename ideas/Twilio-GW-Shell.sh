#!/bin/bash

#aws apigatewayv2 create-domain-name \
  #--domain-name my-fbp.com \
  #--domain-name-configurations CertificateArn=arn:aws:acm:us-east-1:768286545465:certificate/ec8fd596-14ff-4500-aadf-73aa9ec4975c \
  #--region us-east-1


#echo "Exiting after step 1"

#exit 0

echo "If you needed to rebuild the API, put the api-id below"
# aws apigatewayv2 create-api-mapping \
  # --domain-name my-fbp.com \
  # --api-id h0t2ze7abl \
  # --stage "prod" \
  # --region us-east-1
# 
# echo "exiting after step 2"
# exit 0

echo "Get the DNSName from the API Gateway console or using the AWS CLI"
# aws route53 change-resource-record-sets \
  # --hosted-zone-id Z07749133PJ0CXM4DQCYA \
  # --change-batch '{
    # "Changes": [{
      # "Action": "UPSERT",
      # "ResourceRecordSet": {
        # "Name": "my-fbp.com",
        # "Type": "A",
        # "AliasTarget": {
          # "HostedZoneId": "Z1UJRXOUMOOFQ8",
          # "DNSName": "d-n3lrkks01f.execute-api.us-east-1.amazonaws.com",
          # "EvaluateTargetHealth": false
        # }
      # }
    # }]
  # }'