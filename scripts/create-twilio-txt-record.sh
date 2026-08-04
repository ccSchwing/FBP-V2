#!/bin/bash

aws route53 change-resource-record-sets \
    --hosted-zone-id Z07749133PJ0CXM4DQCYA \
    --change-batch '{
        "Changes": [{
            "Action": "CREATE",
            "ResourceRecordSet": {
                "Name": "_twilio.my-fbp.com",
                "Type": "TXT",
                "TTL": 3600,
                "ResourceRecords": [{"Value": "\"twilio-domain-verification=30463feaac4e3f3e552e2fd4d4e43c7a\""}]
            }
        }]
    }'

