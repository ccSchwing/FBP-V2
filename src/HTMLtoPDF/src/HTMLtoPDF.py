import json
import boto3
import os
import tempfile
from weasyprint import HTML
from botocore.client import Config as CORSConfig
from aws_lambda_powertools.event_handler import APIGatewayHttpResolver, Response
from aws_lambda_powertools.event_handler.api_gateway import CORSConfig

cors_config = CORSConfig(
    allow_origin="*",  # Or specify your domain like "https://yourdomain.com"
    allow_headers=["Content-Type", "X-Amz-Date", "Authorization", "X-Api-Key", "X-Amz-Security-Token"],
    max_age=86400,  # Cache preflight for 24 hours
    allow_credentials=False
)

app=APIGatewayHttpResolver(cors=cors_config)

s3_client = boto3.client('s3')
BUCKET_NAME = os.environ.get('S3BucketName', 'my-fbp.com')
CLOUDFRONT_DOMAIN = os.environ.get('CloudFrontDomain')
PDF_DIR="pdfs"

@app.post("/htmlToPdf")
def htmlToPdf():
    request_body = app.current_event.json_body
    url = request_body.get('url')
    html_content = request_body.get('html')
    output_key = request_body.get('filename', 'output.pdf')
    destination = f'{PDF_DIR}/{output_key}'
    tmp_pdf_path = f'/tmp/{output_key}'

    if url:
        HTML(url=url).write_pdf(tmp_pdf_path)
    elif html_content:
        HTML(string=html_content).write_pdf(tmp_pdf_path)
    else:
        return {'statusCode': 400, 'body': json.dumps({'error': 'Provide either url or html'})}

    # Upload PDF to S3
    s3_client.upload_file(
        tmp_pdf_path,
        BUCKET_NAME,
        Key=destination,
        ExtraArgs={'ContentType': 'application/pdf'}
    )

    download_url = f'https://{CLOUDFRONT_DOMAIN}/{destination}'

    return {
        'statusCode': 200,
        'body': json.dumps({
            'message': 'PDF generated successfully!',
            'download_url': download_url,
            's3_key': destination
        })
    }

def lambda_handler(event, context):
    return app.resolve(event, context)