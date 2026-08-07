watch -n 10 aws cloudformation describe-stack-events   --stack-name fbp   --query "StackEvents[0].[Timestamp,ResourceStatus,ResourceType,LogicalResourceId]"   --output table
