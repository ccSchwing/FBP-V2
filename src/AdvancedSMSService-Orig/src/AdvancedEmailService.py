import json
import boto3
import os
from typing import Dict, Any, Optional
from enum import Enum
from dataclasses import dataclass, asdict
from botocore.exceptions import ClientError
from aws_lambda_powertools import Logger, Tracer, Metrics
from aws_lambda_powertools.metrics import MetricUnit
from fbplib.fbpLog import fbpLog

logger = Logger()
tracer = Tracer()
metrics = Metrics()

class EmailType(Enum):
    WELCOME = "welcome"
    REMINDER = "reminder"
    # Add more email types as you migrate from templates...

@dataclass
class EmailResponse:
    success: bool
    message_id: Optional[str] = None
    error: Optional[str] = None
    email_type: Optional[str] = None
    recipient: Optional[str] = None

class EmailService:
    """Production email service for Lambda chaining"""

    def __init__(self):
        self.ses_client = boto3.client('ses')
        self.default_sender = os.environ.get('FROM_EMAIL', 'fbpadmin@my-fbp.com')
        self.company_name = os.environ.get('COMPANY_NAME', 'FBP')
        self.base_url = os.environ.get('BASE_URL', 'https://my-fbp.com')
        self.support_email = os.environ.get('SUPPORT_EMAIL', 'fbpadmin@my-fbp.com')

    @tracer.capture_method
    def _send_single_email(self, recipient: str, content_generator, data: Dict[str, Any], 
                           reply_to: Optional[str], tags: Optional[Dict[str, str]], 
                           email_type: str) -> EmailResponse:
        """Send a single email and return response"""
        subject, html_content, text_content = content_generator(data)

        message_id = self._send_ses_email(
            recipient=recipient,
            subject=subject,
            html_content=html_content,
            text_content=text_content,
            reply_to=reply_to,
            tags=tags,
            email_type=email_type
        )

        return EmailResponse(
            success=True,
            message_id=message_id,
            email_type=email_type,
            recipient=recipient
        )

    @tracer.capture_method
    def send_email(self, email_type: str, recipient: str, data: Dict[str, Any], 
                   reply_to: Optional[str] = None, 
                   tags: Optional[Dict[str, str]] = None) -> EmailResponse:
        """Main entry point for sending emails"""

        try:
            # Validate inputs
            if not recipient or '@' not in recipient:
                raise ValueError("Valid recipient email is required")

            if not data:
                data = {}

            # Get email content generator
            content_generator = self._get_content_generator(EmailType(email_type))

            # Handle different email types
            ##
            # The welcome email is the only one that goes to an individual.
            # The rest go to either all users, or those who have opted in.
            # Each case can gather different recipients and send to them.
            ##
            match email_type:
                case EmailType.WELCOME.value:
                    # Handle welcome email - single recipient
                    return self._send_single_email(recipient, content_generator, data, reply_to, tags, email_type)
                case EmailType.REMINDER.value:
                    # Reminder emails are normally sent to opted-in users from DynamoDB.
                    # For local testing (or missing table config), fall back to provided recipient.
                    reminder_users = []
                    users_table_name = os.environ.get('FBPUSERS_TABLE_NAME')

                    if users_table_name:
                        try:
                            users_table = boto3.resource('dynamodb').Table(users_table_name)
                            email_addrs = users_table.scan(
                                ProjectionExpression='email, firstName, emailReminders'
                            ).get("Items", [])
                            reminder_users = [
                                user for user in email_addrs
                                if user.get('emailReminders') is True and user.get('email')
                            ]
                        except Exception as scan_error:
                            logger.warning(
                                "Failed to query reminder users from DynamoDB; using fallback recipient",
                                extra={"error": str(scan_error), "table_name": users_table_name}
                            )
                    else:
                        logger.info(
                            "FBP_USERS_TABLE_NAME is not set; using fallback recipient for reminder"
                        )

                    ##
                    # If no reminder users are found, fall back to sending to the provided recipient.
                    # No.
                    # If you don't find any reminder users, that's okay.
                    if not reminder_users:
                        logger.info(
                            "No reminder users found -- This could be the case if no users have opted in for reminders"
                        )

                    for user in reminder_users:
                        user_data = dict(data)
                        user_data["user_name"] = user.get("firstName") or user.get("email")
                        self._send_single_email(
                            user["email"],
                            content_generator,
                            user_data,
                            reply_to,
                            tags,
                            email_type,
                        )

                    return EmailResponse(
                        success=True,
                        message_id=f"bulk:{len(reminder_users)}",
                        email_type=email_type,
                        recipient=recipient
                    )
                case _:
                    logger.error("Invalid request type")
                    fbpLog("fbpadmin@my-fbp.com", "GetFBPUser", "Invalid request type", "ERROR")
                    return EmailResponse(
                        success=False,
                        error="Invalid request type",
                        email_type=email_type,
                        recipient=recipient
                    )
                
        except Exception as e:
            logger.error("Failed to send email", extra={
                "error": str(e),
                "email_type": email_type,
                "recipient": recipient
            })

            return EmailResponse(
                success=False,
                error=str(e),
                email_type=email_type,
                recipient=recipient
            )

    def _get_content_generator(self, email_type: EmailType):
        """Get the appropriate content generator for email type"""

        generators = {
            EmailType.WELCOME: self._generate_welcome_content,
            EmailType.REMINDER: self._generate_reminder_content,
            # Add more generators as you migrate from templates...
        }

        generator = generators.get(email_type)
        if not generator:
            raise ValueError(f"Unsupported email type: {email_type.value}")

        return generator

    def _generate_welcome_content(self, data: Dict[str, Any]) -> tuple:
        """Generate welcome email content"""
        user_name = data.get('user_name', 'User')

        subject = f"Welcome to FBP -- Your Account is Ready"

        html_content = f"""
        <html>
        <body>
            <h1>Welcome to {self.company_name}, {user_name}!</h1>
            <p>Many thanks for joining {self.company_name}! Your account has been created successfully.</p>
            <p>Quick Start Guide:</p>
            <p>When you click on the FBP Home link, you'll be taken to the login screen.  Enter the email address
            and your password and you'll be directed to the home page.</p>
            <p>In the unlikely event that you've forgotten your password, don't panic.  You can easily reset it
            at the login page itself.</p>
            <ul>
                <li>FBP Home: <a href="{self.base_url}">FBP Home</a></li>
                <li>To pay for your membership: <a href="{self.base_url}/makepayment.html">Membership Payment Options</a></li>
                <li>See the FAQ at <a href="{self.base_url}/faq.html">FAQ</a></li>
            </ul>
            <p>Need help? Contact us at <a href="mailto:{self.support_email}"><b>{self.support_email}</b></a></p>
            <p>Best regards,<br>The {self.company_name} Team</p>
        </body>
        </html>
        """

        text_content = f"""
Hello {user_name} --\n\nWelcome to {self.company_name}! Your {self.company_name} account has been successfully created.\n\n
Next Steps:\n
1.  Go to {self.base_url}\n
2. Make a payment for your membership: {self.base_url}/makepayment.html\n
3. See the FAQ at {self.base_url}/faq.html\n
Questions? Contact us at {self.support_email}.\n\n
Best regards,\n
The FBP Team
        """

        return subject, html_content, text_content

    def _generate_reminder_content(self, data: Dict[str, Any]) -> tuple:
        """Generate reminder email content"""
        user_name = data.get('user_name', 'User')

        subject = f"Reminder from {self.company_name}"

        html_content = f"""
        <html>
        <body>
            <h1>Reminder from {self.company_name}, {user_name}!</h1>
            <p>This is a friendly reminder from {self.company_name}.</p>
            <p>You still have time to make your {self.company_name} picks for the week.</p>
            <p>Visit the {self.company_name} Home page to make your picks: <a href="{self.base_url}">{self.company_name} Home</a></p>
            <p>If you have questions, contact us at <a href="mailto:{self.support_email}"><b>{self.support_email}</b></a></p>
            <p>Best regards,<br>The {self.company_name} Team</p>
        </body>
        </html>
        """

        text_content = f"""
Hello {user_name} --\n\nThis is a friendly reminder from {self.company_name}.\n\n
You still have time to make your {self.company_name} picks for the week.\n
Visit the {self.company_name} Home page to make your picks: {self.base_url}\n
If you have questions, contact us at {self.support_email}.\n\n
Best regards,\n
The {self.company_name} Team
        """

        return subject, html_content, text_content

    @tracer.capture_method
    def _send_ses_email(self, recipient: str, subject: str, html_content: str, 
                       text_content: str, email_type: str, reply_to: Optional[str] = None,
                       tags: Optional[Dict[str, str]] = None) -> str:
        """Send email via SES"""

        send_args = {
            'Source': self.default_sender,
            'Destination': {'ToAddresses': [recipient]},
            'Message': {
                'Subject': {'Data': subject, 'Charset': 'UTF-8'},
                'Body': {
                    'Html': {'Data': html_content, 'Charset': 'UTF-8'},
                    'Text': {'Data': text_content, 'Charset': 'UTF-8'}
                }
            }
        }

        if reply_to:
            send_args['ReplyToAddresses'] = [reply_to]
        if tags:
            send_args['Tags'] = [{'Name': k, 'Value': v} for k, v in tags.items()]

        response = self.ses_client.send_email(**send_args)
        message_id = response['MessageId']

        logger.info("Email sent successfully", extra={
            "message_id": message_id,
            "recipient": recipient,
            "email_type": email_type
        })

        metrics.add_metric(name="EmailsSent", unit=MetricUnit.Count, value=1)
        metrics.add_metadata(key="email_type", value=email_type)

        return message_id

# Initialize service
email_service = EmailService()

@logger.inject_lambda_context
@tracer.capture_lambda_handler  
@metrics.log_metrics
def lambda_handler(event: Dict[str, Any], context) -> Dict[str, Any]:
    """Lambda handler - receives event and sends email"""
    
    try:
        # Support both direct invocation events and API Gateway proxy events.
        payload = event
        if isinstance(event, dict) and "body" in event:
            body = event.get("body")
            if isinstance(body, str):
                payload = json.loads(body) if body else {}
            elif isinstance(body, dict):
                payload = body

        # Validate required fields
        recipient = payload.get('recipient')
        email_type = payload.get('email_type')
        
        if not recipient or not isinstance(recipient, str):
            raise ValueError("Valid recipient email is required")
        if not email_type or not isinstance(email_type, str):
            raise ValueError("Valid email_type is required")
        
        # Send email using the event data
        data = payload.get('data', {})
        if not isinstance(data, dict):
            data = {}

        result = email_service.send_email(
            email_type=email_type,
            recipient=recipient,
            data=data,
            reply_to=payload.get('reply_to') or data.get('reply_to'),
            tags=payload.get('tags')
        )
        
        # Return the result as a dict for your Lambda chain
        return asdict(result)
        
    except Exception as e:
        logger.error("Lambda handler error", extra={"error": str(e)})
        return {
            'success': False,
            'error': str(e)
        }
