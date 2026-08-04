Don&#39;t make any code changes, but how do I add a PDF attachment to an outbound email in AdvancedMessagingService.py?

---

Let me look at the full file to understand the email sending implementation.

---


The key constraint is that `_send_one` currently uses `ses_client.send_email`, which doesn't support attachments. To add a PDF, you'd need to switch that call to `ses_client.send_raw_email` using a MIME multipart message.

Here's the approach for [_send_one](FBP/src/AdvancedMessagingService/src/AdvancedMessagingService.py#L243):

1. Add `email` (stdlib) imports — `from email.mime.multipart import MIMEMultipart`, `from email.mime.text import MIMEText`, `from email.mime.application import MIMEApplication`

2. Fetch the PDF bytes (e.g. from S3)

3. Build a MIME message and call `send_raw_email` instead of `send_email`:

```python
import boto3
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.application import MIMEApplication

def _send_one(self, recipient, content_generator, data, message_type, pdf_bytes=None, pdf_filename="attachment.pdf"):
    subject, html_content, text_content = content_generator(data)

    msg = MIMEMultipart('mixed')
    msg['Subject'] = subject
    msg['From'] = self.default_sender
    msg['To'] = recipient

    body = MIMEMultipart('alternative')
    body.attach(MIMEText(text_content, 'plain'))
    body.attach(MIMEText(html_content, 'html'))
    msg.attach(body)

    if pdf_bytes:
        part = MIMEApplication(pdf_bytes, Name=pdf_filename)
        part['Content-Disposition'] = f'attachment; filename="{pdf_filename}"'
        msg.attach(part)

    response = self.ses_client.send_raw_email(
        Source=self.default_sender,
        Destinations=[recipient],
        RawMessage={'Data': msg.as_string()}
    )
    # ... rest of logging unchanged
```

To fetch the PDF from S3 before calling `_send_one`:
```python
pdf_bytes = boto3.client('s3').get_object(Bucket=bucket, Key='myfile.pdf')['Body'].read()
```

The main things to keep in mind:
- `send_raw_email` replaces `send_email` entirely — you can't mix them
- SES has a 10MB raw message size limit
- You'd pass `pdf_bytes=None` for all existing call sites so they continue working without attachments, only passing bytes for the message type(s) that need the PDF