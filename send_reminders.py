import os
import base64
import datetime
from email.message import EmailMessage
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
import gspread
import config

def get_gmail_service():
    """Authenticates and returns the Gmail API service."""
    creds = None
    if os.path.exists(config.TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(config.TOKEN_FILE, config.SCOPES)
    
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
             # Re-auth needed for Gmail scope
            flow = InstalledAppFlow.from_client_config(
                {"installed": {
                    "client_id": config.CLIENT_ID, 
                    "client_secret": config.CLIENT_SECRET,
                    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                    "token_uri": "https://oauth2.googleapis.com/token",
                    "redirect_uris": ["http://localhost:8080/"]
                }}, config.SCOPES)
            creds = flow.run_local_server(port=8080)
            
        with open(config.TOKEN_FILE, 'w') as token:
            token.write(creds.to_json())

    return build('gmail', 'v1', credentials=creds)

def get_emails_from_sheet():
    """Fetches emails from the members sheet."""
    try:
        # Use existing auth logic or duplicate minimal needed
        service = get_gmail_service() # Just to reuse creds loading logic for gspread
        # Actually better to use gspread directly
        creds = Credentials.from_authorized_user_file(config.TOKEN_FILE, config.SCOPES)
        client = gspread.authorize(creds)
        
        sheet = client.open(config.EMAIL_SHEET_NAME).sheet1
        records = sheet.get_all_records() # Returns list of dicts using headers
        
        email_map = {}
        for row in records:
            # Flexible matching for 'Full Name' or 'Name'
            name_key = next((k for k in row.keys() if 'name' in k.lower()), None)
            email_key = config.EMAIL_COL_HEADER
            
            if name_key and email_key in row:
                name = row[name_key]
                email = row[email_key]
                if email and "@" in email: # Basic validation
                    email_map[name] = email
                    
        return email_map
    except Exception as e:
        print(f"Error fetching emails: {e}")
        return {}

def send_email(service, to_email, subject, body, test_mode=True):
    """Sends an email using Gmail API."""
    if test_mode:
        print(f"[TEST MODE] Would send email to: {to_email}")
        print(f"Subject: {subject}")
        print(f"Body: {body[:50]}...")
        return True

    try:
        message = EmailMessage()
        message['To'] = to_email
        message['Subject'] = subject
        
        # Set plain text content as fallback
        message.set_content(body)
        
        # Add HTML version (which allows control over line breaks)
        # We replace newlines with <br> for the HTML version so it looks similar
        html_body = f"""
        <html>
          <body style="font-family: Arial, sans-serif; font-size: 14px; color: #000000;">
            <p>{body.replace(chr(10), '<br>')}</p>
          </body>
        </html>
        """
        message.add_alternative(html_body, subtype='html')

        # encoded message
        encoded_message = base64.urlsafe_b64encode(message.as_bytes()).decode()

        create_message = {
            'raw': encoded_message
        }
        
        send_message = (service.users().messages().send
                        (userId="me", body=create_message).execute())
        print(f"Message Id: {send_message['id']} sent to {to_email}")
        return True
    except Exception as e:
        print(f"An error occurred sending to {to_email}: {e}")
        return False

def main():
    print("--- Weekly Reminder Service ---")
    
    # SAFETY: Default to TEST MODE. Change to False ONLY when ready.
    TEST_MODE = False 
    
    service = get_gmail_service()
    emails = get_emails_from_sheet()
    
    if not emails:
        print("No emails found.")
        return

    print(f"Found {len(emails)} emails.")
    
    subject = "Reminder: Exposure Meeting Tonight!"
    body = (
        "Hey there,\n\n"
        "Just a friendly reminder that we have our weekly Exposure meeting tonight at 23:00 Turkish Time.\n\n"
        "Zoom Link: https://aalto.zoom.us/j/61907902518\n\n"
        "See you there!\n\n"
        "Best,\n"
        "Exposure - Elite engineers and founders of the Turkish diaspora"
    )
    
    for name, email in emails.items():
        print(f"Processing {name}...")
        send_email(service, email, subject, body, test_mode=TEST_MODE)

if __name__ == "__main__":
    main()
