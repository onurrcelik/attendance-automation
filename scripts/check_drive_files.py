import config
import os
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

def get_drive_service():
    creds = None
    if os.path.exists(config.TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(config.TOKEN_FILE, config.SCOPES)
    
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
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

def list_files():
    service = get_drive_service()
    folder_id = config.DRIVE_FOLDER_ID
    print(f"Checking folder: {folder_id}")
    
    # Query for ALL files in the folder
    query = f"'{folder_id}' in parents and trashed = false"
    
    results = service.files().list(
        q=query, 
        fields="files(id, name, mimeType, createdTime)",
        orderBy="createdTime desc",
        pageSize=20
    ).execute()
    
    files = results.get('files', [])

    if not files:
        print("No files found in this folder.")
    else:
        print(f"Found {len(files)} files (showing top 20):")
        print("-" * 80)
        print(f"{'Name':<40} | {'MimeType':<30} | {'Created Time'}")
        print("-" * 80)
        for f in files:
            print(f"{f['name']:<40} | {f['mimeType']:<30} | {f['createdTime']}")

if __name__ == "__main__":
    list_files()
