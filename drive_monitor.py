import time
import os
import io
import datetime
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from google.auth.exceptions import RefreshError
import json
import re
import config
import main as attendance_script  # Import existing logic

def parse_date_from_filename(filename):
    """
    Tries to parse a date from the filename in DD.MM.YYYY format.
    Returns a datetime.date object or None if no match found.
    """
    # Regex for DD.MM.YYYY
    match = re.search(r"(\d{2})\.(\d{2})\.(\d{4})", filename)
    if match:
        day, month, year = map(int, match.groups())
        try:
            return datetime.date(year, month, day)
        except ValueError:
            return None
    return None

def get_drive_service():
    """Authenticates and returns the Drive API service."""
    creds = None
    if os.path.exists(config.TOKEN_FILE):
        try:
            creds = Credentials.from_authorized_user_file(config.TOKEN_FILE, config.SCOPES)
        except (ValueError, json.JSONDecodeError):
            print("Token file corrupted. Re-authenticating...")
            creds = None
    
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
            except RefreshError:
                print("Token expired and refresh failed. Re-authenticating...")
                creds = None
        else:
             # This should be handled by main.py first run usually, but good to have
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

    return build('drive', 'v3', credentials=creds)

def get_latest_thursday(date_obj):
    """
    Returns the date of the Thursday of the given week.
    If date_obj is Thursday, returns date_obj.
    If date_obj is Friday-Wednesday, returns the *previous* Thursday.
    """
    # Weekday: Mon=0, Tue=1, Wed=2, Thu=3, Fri=4, Sat=5, Sun=6
    weekday = date_obj.weekday()
    
    # Calculate days to subtract to get to Thursday (3)
    if weekday >= 3:
        days_to_subtract = weekday - 3
    else:
        # If Mon(0), Tue(1), Wed(2), we go back to previous week's Thursday
        days_to_subtract = weekday + 4
        
    target_date = date_obj - datetime.timedelta(days=days_to_subtract)
    return target_date

def check_for_files(service):
    """Checks for image files in the specific folder."""
    if config.DRIVE_FOLDER_ID == "REPLACE_WITH_SOURCE_FOLDER_ID":
        print("Error: Please set DRIVE_FOLDER_ID in config.py")
        return

    # Query: In folder, not trashed, is image
    query = f"'{config.DRIVE_FOLDER_ID}' in parents and mimeType contains 'image/' and trashed = false"
    
    results = service.files().list(q=query, fields="files(id, name, createdTime)").execute()
    files = results.get('files', [])

    if not files:
        print("No new files found.")
    else:
        print(f"Found {len(files)} new files.")
        for file in files:
            process_drive_file(service, file)

def process_drive_file(service, file_meta):
    file_id = file_meta['id']
    file_name = file_meta['name']
    created_time_str = file_meta['createdTime'] # ISO 8601 string
    
    print(f"Processing {file_name}...")
    
    # 1. Download File
    request = service.files().get_media(fileId=file_id)
    fh = io.BytesIO()
    downloader = MediaIoBaseDownload(fh, request)
    done = False
    while done is False:
        status, done = downloader.next_chunk()
    
    # Save locally to temp path
    local_path = f"temp_{file_name}"
    with open(local_path, "wb") as f:
        f.write(fh.getbuffer())
        
    # 2. Determine Attendance Date
    # First, try to parse from filename (e.g., 04.12.2025.png)
    parsed_date = parse_date_from_filename(file_name)
    
    if parsed_date:
        meeting_thursday = parsed_date
        print(f"Parsed date from filename: {meeting_thursday}")
    else:
        # Fallback: Parse createdTime (e.g., 2025-12-10T17:48:08.000Z)
        # We strip 'Z' and typically handle UTC. For simplicity, we treat as naive or assume UTC.
        upload_dt = datetime.datetime.fromisoformat(created_time_str.replace('Z', '+00:00'))
        upload_date = upload_dt.date()
        
        meeting_thursday = get_latest_thursday(upload_date)
        print(f"File uploaded on {upload_date}. Assigning to meeting on Thursday {meeting_thursday}.")
    
    # 3. Process Attendance
    success = attendance_script.process_single_image(local_path, target_date=meeting_thursday)
    
    # Cleanup local file
    if os.path.exists(local_path):
        os.remove(local_path)
    
    # 4. Move to Processed Folder
    if success:
        if config.PROCESSED_FOLDER_ID != "REPLACE_WITH_PROCESSED_FOLDER_ID":
            # Retrieve existing parents to remove them
            file = service.files().get(fileId=file_id, fields='parents').execute()
            previous_parents = ",".join(file.get('parents'))
            
            # Move file
            service.files().update(
                fileId=file_id,
                addParents=config.PROCESSED_FOLDER_ID,
                removeParents=previous_parents,
                fields='id, parents'
            ).execute()
            print(f"Moved {file_name} to Processed folder.")
        else:
            print("Warning: PROCESSED_FOLDER_ID not set. File remains in source folder.")
    else:
        print(f"Failed to process {file_name}. Left in source folder.")

def start_monitoring():
    print("Starting Drive Monitor...", flush=True)
    print("Press Ctrl+C to stop.", flush=True)
    service = get_drive_service()
    
    sheet_client = attendance_script.get_google_sheet_client()

    while True:
        try:
            check_for_files(service)
            
            # Also sync sheet streaks (handle manual updates)
            if sheet_client:
                 attendance_script.recalculate_missed_streaks(sheet_client)
            else:
                 # Try to reconnect if client failed initially or expired? 
                 # get_google_sheet_client handles auth refresh internally usually if using gspread properly
                 # but here we just retry getting it
                 sheet_client = attendance_script.get_google_sheet_client()

            # Sleep for 1 minute (60 seconds)
            time.sleep(60)
        except KeyboardInterrupt:
            print("Stopping...", flush=True)
            break
        except Exception as e:
            print(f"Error in monitoring loop: {e}", flush=True)
            time.sleep(60)

if __name__ == "__main__":
    # Force unbuffered stdout just in case
    import sys
    sys.stdout.reconfigure(line_buffering=True)
    start_monitoring()
