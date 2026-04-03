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
    Tries to parse a date from the filename.
    Supports:
      - DD.MM.YYYY (e.g. 02.04.2026.png)
      - YYYY-MM-DD (e.g. Screenshot 2026-04-02 at 21.21.46.png)
    Returns a datetime.date object or None if no match found.
    """
    # Try YYYY-MM-DD first (macOS screenshot format)
    match = re.search(r"(\d{4})-(\d{2})-(\d{2})", filename)
    if match:
        year, month, day = map(int, match.groups())
        try:
            return datetime.date(year, month, day)
        except ValueError:
            pass

    # Try DD.MM.YYYY
    match = re.search(r"(\d{2})\.(\d{2})\.(\d{4})", filename)
    if match:
        day, month, year = map(int, match.groups())
        try:
            return datetime.date(year, month, day)
        except ValueError:
            pass

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
    created_time_str = file_meta['createdTime']

    print(f"Processing {file_name}...")

    # 1. Download file
    request = service.files().get_media(fileId=file_id)
    fh = io.BytesIO()
    downloader = MediaIoBaseDownload(fh, request)
    done = False
    while not done:
        _, done = downloader.next_chunk()

    local_path = f"temp_{file_name}"
    with open(local_path, "wb") as f:
        f.write(fh.getbuffer())

    # 2. Determine attendance date
    parsed_date = parse_date_from_filename(file_name)
    if parsed_date:
        meeting_date = parsed_date
        print(f"Parsed date from filename: {meeting_date}")
    else:
        upload_dt = datetime.datetime.fromisoformat(created_time_str.replace('Z', '+00:00'))
        upload_date = upload_dt.date()
        meeting_date = get_latest_thursday(upload_date)
        print(f"File uploaded on {upload_date}. Assigning to Thursday {meeting_date}.")

    # 3. Process attendance — always clean up temp file regardless of outcome
    success = False
    try:
        success = attendance_script.process_single_image(local_path, target_date=meeting_date)
    finally:
        if os.path.exists(local_path):
            os.remove(local_path)

    # 4. Move to Processed only if sheet was actually updated
    if success:
        if config.PROCESSED_FOLDER_ID and config.PROCESSED_FOLDER_ID != "REPLACE_WITH_PROCESSED_FOLDER_ID":
            file = service.files().get(fileId=file_id, fields='parents').execute()
            previous_parents = ",".join(file.get('parents'))
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
        print(f"Failed to process {file_name}. Left in source folder for retry.")

LOCAL_SCREENSHOTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "screenshots")
LOCAL_PROCESSED_DIR = os.path.join(LOCAL_SCREENSHOTS_DIR, "processed")

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}

def check_local_screenshots_folder():
    """Processes any new images in the local screenshots/ folder."""
    if not os.path.isdir(LOCAL_SCREENSHOTS_DIR):
        return

    os.makedirs(LOCAL_PROCESSED_DIR, exist_ok=True)

    for fname in sorted(os.listdir(LOCAL_SCREENSHOTS_DIR)):
        fpath = os.path.join(LOCAL_SCREENSHOTS_DIR, fname)
        if not os.path.isfile(fpath):
            continue
        if os.path.splitext(fname)[1].lower() not in IMAGE_EXTENSIONS:
            continue

        print(f"[Local] Processing {fname}...", flush=True)
        try:
            parsed_date = parse_date_from_filename(fname)
            if parsed_date:
                meeting_date = parsed_date
                print(f"[Local] Parsed date from filename: {meeting_date}", flush=True)
            else:
                meeting_date = get_latest_thursday(datetime.date.today())
                print(f"[Local] No date in filename. Using {meeting_date}.", flush=True)

            success = attendance_script.process_single_image(fpath, target_date=meeting_date)

            if success:
                dest = os.path.join(LOCAL_PROCESSED_DIR, fname)
                os.rename(fpath, dest)
                print(f"[Local] Moved {fname} to processed/", flush=True)
            else:
                print(f"[Local] Failed to process {fname}. Left in screenshots/ for retry.", flush=True)
        except Exception as e:
            print(f"[Local] Error processing {fname}: {e}. Skipping.", flush=True)


def cleanup_stale_temp_files():
    """Remove any leftover temp_* files from previous crashes."""
    work_dir = os.path.dirname(os.path.abspath(__file__))
    for fname in os.listdir(work_dir):
        if fname.startswith("temp_") and os.path.splitext(fname)[1].lower() in IMAGE_EXTENSIONS:
            fpath = os.path.join(work_dir, fname)
            try:
                os.remove(fpath)
                print(f"Cleaned up stale temp file: {fname}", flush=True)
            except Exception as e:
                print(f"Could not remove stale temp file {fname}: {e}", flush=True)


def start_monitoring():
    print("Starting Drive Monitor...", flush=True)
    print("Press Ctrl+C to stop.", flush=True)
    cleanup_stale_temp_files()
    service = get_drive_service()

    sheet_client = attendance_script.get_google_sheet_client()

    while True:
        try:
            check_for_files(service)
            check_local_screenshots_folder()

            # Also sync sheet streaks (handle manual updates)
            if sheet_client:
                 attendance_script.recalculate_missed_streaks(sheet_client)
            else:
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
