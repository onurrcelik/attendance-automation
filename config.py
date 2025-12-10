import os
from dotenv import load_dotenv

load_dotenv()

# Google Sheets Configuration
SHEET_NAME = "Exposure Attendance"  # Update this to your actual sheet name
# CREDENTIALS_FILE is no longer used for Service Account, we use client_id/secret for OAuth
CLIENT_ID = os.getenv("client_id")
CLIENT_SECRET = os.getenv("client_secret")
TOKEN_FILE = "token.json"
SCOPES = [
    'https://www.googleapis.com/auth/spreadsheets', 
    'https://www.googleapis.com/auth/drive',
    'https://www.googleapis.com/auth/gmail.send' 
]

# Drive Configuration - REPLACE WITH YOUR FOLDER IDs
DRIVE_FOLDER_ID = "1mJvEr6dRpghYc0JlP4_lhhZyuN56qgZ8"
PROCESSED_FOLDER_ID = "1xcop6WGvQ6MurP1Hw9VCsIgWufgHZt1J"

# Email Configuration
EMAIL_SHEET_NAME = "Exposure Members"
EMAIL_COL_HEADER = "E-mail"
MEETING_TIME_HOUR = 21 # 21:00 CET, so reminder at 19:00? User said 2 hours before.


# OCR Configuration

# OCR Configuration
# If tesseract is in your PATH, this might not be needed.
# Otherwise, uncomment and set the path:
# import pytesseract
# pytesseract.pytesseract.tesseract_cmd = r'/usr/local/bin/tesseract'

# Attendance Rules
CONSECUTIVE_MISS_LIMIT = 3
