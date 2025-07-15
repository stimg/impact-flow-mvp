import smtplib
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from types import SimpleNamespace

from pydantic_settings import BaseSettings


class EmailConfig(BaseSettings):
    SMTP_SERVER: str = "smtp.example.com"
    SMTP_PORT: int = 587
    SMTP_USERNAME: str = "your_username"
    SMTP_PASSWORD: str = "your_password"
    FROM_EMAIL: str = "noreply@yourdomain.com"
    ADMIN_EMAIL: str = "admin@yourdomain.com"

    class Config:
        env_file = ".env"

config = EmailConfig()

async def send_mail(from_addr, to_addrs, msg):
    # Connect to the SMTP server and send the email
    try:
        with smtplib.SMTP_SSL(config.SMTP_SERVER, config.SMTP_PORT, timeout=15) as server:
            # server.set_debuglevel(1)
            server.login(config.SMTP_USERNAME, config.SMTP_PASSWORD)
            server.send_message(msg, from_addr=from_addr, to_addrs=to_addrs)
            print(f"Email sent successfully.\n")

    except Exception as e:
        print(f"Send email error: {e}")

async def send_feedback_email(feedback, user):
    date = datetime.fromtimestamp(feedback.updated_at)
    formatted_date = date.strftime("%d.%m.%Y %H:%M")
    print(f"Sending feedback email to {config.ADMIN_EMAIL}...")
    try:
        if hasattr(feedback, 'data'):
            data = SimpleNamespace(**feedback.data)

        if hasattr(feedback, 'meta'):
            meta = SimpleNamespace(**feedback.meta)

        if hasattr(feedback, 'snapshot'):
            chat = SimpleNamespace(**feedback.snapshot["chat"])
            chat_title = chat.title
            messages = chat.chat["messages"]
            # Find assistant message by message id
            message = next((msg for msg in messages if msg["id"] == meta.message_id), None)
            # Find user request message by parent id
            user_message = next((msg for msg in messages if msg["id"] == message["parentId"]), None)

    except Exception as e:
        print(f"Error preparing email content: {e}")
        return


    # Create message
    msg = MIMEMultipart()
    msg['From'] = config.FROM_EMAIL
    msg['To'] = config.ADMIN_EMAIL
    msg['Subject'] = f"Neue Bewertung von {user.name}"

    # Create the email body
    try:
        body = f"""
Author: {user.name} ({user.email})
Geschrieben am: {formatted_date}
Bewertung: {data.details["rating"]}
Tags: {', '.join(data.tags)}

Kommentar:

{data.comment}

--------------------------------

Benutzeranfrage:

{user_message["content"]}

Mentora Antwort:

{message["content"]}

--------------------------------
Chat name: {chat_title}
Model: {data.model_id}
Feedback ID: {feedback.id}
Chat ID: {meta.chat_id}
Message ID: {meta.message_id}

Mit freundlichen Grüssen
Dein persönlicher Impact Flow Mailbot
        """
    except Exception as e:
        print(f"Error creating email body: {e}")

    msg.attach(MIMEText(body, 'plain', 'UTF-8'))
    recipients = config.ADMIN_EMAIL.split(',')

    await send_mail(config.FROM_EMAIL, recipients, msg)

