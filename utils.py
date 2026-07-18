import os
import smtplib
import secrets
import string
from datetime import datetime

from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from dotenv import load_dotenv

load_dotenv()

SMTP_EMAIL = os.getenv('SMTP_EMAIL')
SMTP_PASSWORD = os.getenv('SMTP_PASSWORD')

def send_email(to_email, subject, body, is_html=False):
    if not SMTP_EMAIL or not SMTP_PASSWORD:
        print("SMTP Credentials not set. Email not sent.")
        return False
    
    try:
        msg = MIMEMultipart('alternative')
        msg['From'] = SMTP_EMAIL
        msg['To'] = to_email
        msg['Subject'] = subject

        if is_html:
            html_content = f"""
            <html>
            <head>
                <style>
                    body {{ font-family: 'Helvetica', 'Arial', sans-serif; background-color: #050505; color: #e0e0e0; padding: 20px; }}
                    .container {{ max-width: 600px; margin: 0 auto; background-color: #111111; padding: 30px; border-radius: 16px; border: 1px solid #333; }}
                    .header {{ text-align: center; border-bottom: 2px solid #00ff88; padding-bottom: 20px; margin-bottom: 20px; }}
                    .logo {{ font-size: 26px; font-weight: bold; color: #ffffff; text-decoration: none; }}
                    .logo span {{ color: #00ff88; }}
                    .content {{ line-height: 1.6; color: #cccccc; }}
                    .otp-box {{ background-color: #1a1a1a; padding: 15px; text-align: center; border-radius: 8px; font-size: 28px; letter-spacing: 5px; font-weight: bold; color: #00ff88; border: 1px solid #00ff88; margin: 25px 0; }}
                    strong {{ color: #ffffff; }}
                    .footer {{ margin-top: 40px; text-align: center; font-size: 12px; color: #666666; border-top: 1px solid #222; padding-top: 20px; }}
                </style>
            </head>
            <body>
                <div class="container">
                    <div class="header">
                        <a href="#" class="logo">Eco- <span>Recycling</span></a>
                    </div>
                    <div class="content">
                        {body}
                    </div>
                    <div class="footer">
                        &copy; 2026 Eco - Recycling. Making the world greener.<br>
                        This is an automated message, please do not reply.
                    </div>
                </div>
            </body>
            </html>
            """
            msg.attach(MIMEText(html_content, 'html'))
        else:
            msg.attach(MIMEText(body, 'plain'))

        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(SMTP_EMAIL, SMTP_PASSWORD)
        text = msg.as_string()
        server.sendmail(SMTP_EMAIL, to_email, text)
        server.quit()
        return True
    except Exception as e:
        print(f"Failed to send email: {e}")
        return False

def generate_otp():
    return str(secrets.randbelow(1000000)).zfill(6)

def generate_order_id():
    """Generates an Order ID like EVO-20231027-X9Z1"""
    date_str = datetime.now().strftime("%Y%m%d")
    random_str = ''.join(secrets.choice(string.ascii_uppercase + string.digits) for _ in range(4))
    return f"EVO-{date_str}-{random_str}"

def generate_batch_id():
    """Generates a Batch ID like BATCH-20231027-A1B2"""
    date_str = datetime.now().strftime("%Y%m%d")
    random_str = ''.join(secrets.choice(string.ascii_uppercase + string.digits) for _ in range(4))
    return f"BATCH-{date_str}-{random_str}"
