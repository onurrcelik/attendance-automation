import sys
import os
import json
import datetime
from PIL import Image
import pytesseract
from thefuzz import process
import gspread
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
import config

def get_google_sheet_client():
    """Authenticates and returns the Google Sheets client using OAuth2."""
    creds = None
    
    # The file token.json stores the user's access and refresh tokens, and is
    # created automatically when the authorization flow completes for the first time.
    if os.path.exists(config.TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(config.TOKEN_FILE, config.SCOPES)
        
    # If there are no (valid) credentials available, let the user log in.
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            # Create client config from env vars
            if not config.CLIENT_ID or not config.CLIENT_SECRET:
                print("Error: Missing client_id or client_secret in .env")
                return None
                
            client_config = {
                "installed": {
                    "client_id": config.CLIENT_ID,
                    "client_secret": config.CLIENT_SECRET,
                    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                    "token_uri": "https://oauth2.googleapis.com/token",
                    "redirect_uris": ["http://localhost"]
                }
            }
            
            flow = InstalledAppFlow.from_client_config(client_config, config.SCOPES)
            # Use fixed port 8080 to match the GCP Console "Authorized redirect URI"
            creds = flow.run_local_server(port=8080)
            
        # Save the credentials for the next run
        with open(config.TOKEN_FILE, 'w') as token:
            token.write(creds.to_json())

    client = gspread.authorize(creds)
    return client

def get_members(sheet=None):
    """Retrieves members from the local JSON or Google Sheet."""
    if sheet:
        try:
            # Assuming names are in the first column
            worksheet = sheet.get_worksheet(0)
            names = worksheet.col_values(1)[1:] # Skip header
            # Update local cache
            with open('members.json', 'w') as f:
                json.dump(names, f, indent=4)
            return names
        except Exception as e:
            print(f"Warning: Could not fetch members from sheet ({e}). Using local cache.")
    
    # Fallback to local cache
    if os.path.exists('members.json'):
        with open('members.json', 'r') as f:
            return json.load(f)
    return []

def extract_text_from_image(image_path):
    """Extracts text from the given image using Tesseract OCR."""
    try:
        image = Image.open(image_path)
        text = pytesseract.image_to_string(image)
        return text
    except Exception as e:
        print(f"Error reading image: {e}")
        return ""

def match_attendance(ocr_text, members):
    """Matches OCR text against member list using fuzzy matching."""
    present_members = []
    # Split text into lines/words and try to find member names
    # This is a naive approach; we might need more sophisticated line parsing
    # depending on the screenshot layout (e.g. grid of names vs list)
    
    # Strategy: Iterate through each member and check if their name (or close match) is in the text
    # This works better if the text is noisy
    
    for member in members:
        # Check for partial match or best match in the text
        # We can scan the text line by line
        # Or just check if the member name exists in the blob with high confidence
        
        # Simple check: is the member name (or reasonably close) in the text?
        # unique_names in text
        
        # Let's try searching for the member in the full text
        # If the member name is "Onur Celik", find "Onur Celik" in text
        
        if not member.strip():
            continue
            
        best_match = process.extractOne(member, ocr_text.split('\n'))
        if best_match and best_match[1] > 80: # Confidence threshold
             present_members.append(member)
             print(f"Matched: {member} (Found: '{best_match[0]}', Score: {best_match[1]})")
        else:
            # Fallback for "Firstname" only or similar variations if needed
            pass
            
    return present_members

def update_sheet_attendance(client, present_members, target_date=None):
    """Updates the Google Sheet with attendance."""
    if not client:
        return

    try:
        sheet = client.open(config.SHEET_NAME).sheet1
        
        # Get all values to map headers and rows
        all_records = sheet.get_all_values()
        headers = all_records[0]
        
        # Use provided date or today
        if target_date:
            date_str = target_date.strftime("%d/%m/%Y")
        else:
            date_str = datetime.date.today().strftime("%d/%m/%Y")
        
        try:
            col_index = headers.index(date_str) + 1
        except ValueError:
            print(f"Error: Column for date ({date_str}) not found in specific format DD/MM/YYYY.")
            print(f"Existing headers: {headers}")
            return

        # Prepare column update
        member_name_col_index = 0 # Assuming first column
        
        # Prepare updates list for batching
        cells_to_update = []
        
        print(f"Updating attendance for {date_str} in column {col_index}...")
        
        for i, row in enumerate(all_records[1:]): # Skip header
            member_name = row[member_name_col_index]
            row_num = i + 2 
            
            is_present = member_name in present_members
            current_val = row[col_index - 1] # 0-based index
            
            # Optimization: Only update if changed (comparing string representations)
            # Checkbox TRUE is often 'TRUE', FALSE is 'FALSE'
            # But let's just force update to be safe or check carefully
            
            status_val = True if is_present else False
            # Create cell object
            cells_to_update.append(gspread.Cell(row_num, col_index, status_val))
            
        if cells_to_update:
            sheet.update_cells(cells_to_update)
            print(f"Attendance for {date_str} updated successfully ({len(cells_to_update)} cells).")
        else:
             print("No updates needed.")
        
        # Update "Meetings Missed in a Row" column
        missed_col_name = "# of Meetings Missed in a Row"
        missed_col_index = -1
        
        for idx, h in enumerate(headers):
             if missed_col_name in h:
                 missed_col_index = idx + 1
                 break
        
        if missed_col_index != -1:
             print(f"Updating '{missed_col_name}' column (Index: {missed_col_index})...")
             
             # Re-fetch all data to ensure we have the latest checkbox states
             updated_records = sheet.get_all_values()
             
             # Identify date columns again
             date_indices = []
             for idx, header in enumerate(headers):
                try:
                    dt = datetime.datetime.strptime(header, "%d/%m/%Y")
                    date_indices.append((idx, dt))
                except ValueError:
                    continue
             
             # Sort by date
             date_indices.sort(key=lambda x: x[1])
             
             # Filter out future dates: keep dates <= target_date (or today)
             cutoff_date = target_date if target_date else datetime.date.today()
             # Ensure cutoff_date is datetime for comparison if needed, or convert dt to date
             if isinstance(cutoff_date, datetime.datetime):
                 cutoff_date = cutoff_date.date()
                 
             valid_date_indices = []
             for idx, dt in date_indices:
                 if dt.date() <= cutoff_date:
                     valid_date_indices.append(idx)
             
             # Iterate backwards through VALID dates
             for i, row in enumerate(updated_records[1:]): # Skip header
                 row_num = i + 2
                 
                 consecutive_misses = 0
                 # Iterate backwards
                 for col_idx in reversed(valid_date_indices):
                     val = row[col_idx]
                     str_val = str(val).strip().upper()
                     
                     # Check if present
                     is_present = str_val in ["TRUE", "1", "YES"]
                     
                     if not is_present:
                         consecutive_misses += 1
                     else:
                         # Found a meeting they attended, reset/stop counting
                         break
                 
                 # Cap at 3 for the dropdown options (0, 1, 2, 3)
                 dropdown_val = min(consecutive_misses, 3)
                 
                 # Optimization: Only update if changed (requires reading current val, but we have `row`)
                 # But `row` data might be slightly stale for the missed_col if we didn't fetch it specifically?
                 # We fetched `updated_records`, so it should be fine.
                 current_miss_val = row[missed_col_index - 1]
                 
                 # Check if update needed
                 if str(current_miss_val) != str(dropdown_val):
                     sheet.update_cell(row_num, missed_col_index, dropdown_val)
                     if dropdown_val == 3:
                         print(f"Member '{row[0]}' has reached 3 consecutive misses.")

        else:
            print(f"Warning: Column '{missed_col_name}' not found.")

    except Exception as e:
        print(f"Error updating sheet: {e}")

def process_single_image(image_path, target_date=None):
    """Main processing logic callable from other scripts."""
    print("Initializing...")
    client = get_google_sheet_client()
    
    # Get members
    members = get_members(client.open(config.SHEET_NAME) if client else None)
    
    if not members:
        print("No members found.")
        return False

    print(f"Found {len(members)} members.")
    print("Processing image...")
    text = extract_text_from_image(image_path)
    
    print("Matching names...")
    present_members = match_attendance(text, members)
    
    print(f"Identified {len(present_members)} attendees: {present_members}")
    
    if client:
        print("Updating Google Sheet...")
        update_sheet_attendance(client, present_members, target_date)
        return True
    else:
        print("Skipping Sheet update (No credentials).")
        return False

def main():
    if len(sys.argv) < 2:
        print("Usage: python3 main.py <screenshot_path>")
        sys.exit(1)
        
    image_path = sys.argv[1]
    process_single_image(image_path)

if __name__ == "__main__":
    main()
