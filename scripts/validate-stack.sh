#!/bin/bash
STACK_NAME="fbp"
TEMPLATE="template.yaml"

# Get logical IDs from the stack
echo "=== Resources in Stack ==="
aws cloudformation list-stack-resources \
  --stack-name $STACK_NAME \
  --query "StackResourceSummaries[].LogicalResourceId" \
  --output text | tr '\t' '\n' | sort > /tmp/stack_resources.txt
cat /tmp/stack_resources.txt

# Get logical IDs from template.yaml (looks for lines ending in ":")
echo ""
echo "=== Resources in Template ==="
yq '.Resources | keys[]' $TEMPLATE | sort > /tmp/template_resources.txt
# Compare
echo ""
echo "=== In Template but NOT in Stack ==="
comm -23 /tmp/template_resources.txt /tmp/stack_resources.txt

echo ""
echo "=== In Stack but NOT in Template ==="
comm -13 /tmp/template_resources.txt /tmp/stack_resources.txt
