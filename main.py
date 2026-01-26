import sys
import os
import json
import datetime
from PIL import Image
import pytesseract
from thefuzz import process, fuzz
import gspread
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
import unicodedata
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
            creds = flow.run_local_server(port=8080, prompt='consent')
            
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

def normalize_text(text):
    """
    Normalizes text by removing diacritics and converting to lowercase.
    e.g., "Şan Fikri Köktas" -> "san fikri koktas"
    """
    if not text:
        return ""
    # Normalize unicode characters to closest ASCII equivalent
    text = unicodedata.normalize('NFKD', text).encode('ascii', 'ignore').decode('utf-8')
    return text.lower().strip()

def clean_line(text):
    """
    Removes common noise from OCR lines.
    """
    if not text:
        return ""
    # Lowercase first
    text = text.lower()
    
    # Remove specific noise terms
    noise_terms = ["(me)", "(host)", "(guest)", "iphone", "android", "phone", "..."]
    for term in noise_terms:
        text = text.replace(term, "")
        
    # Remove non-alphanumeric characters (except spaces) for cleaner matching?
    # Or just return the cleaned text
    return text.strip()

def match_attendance(ocr_text, members):
    """Matches OCR text against member list using improved matching."""
    present_members = []
    
    # Pre-compute first name counts to check for uniqueness
    # usage: 'Emre' -> 1
    first_name_counts = {}
    for m in members:
        first_name = m.strip().split(" ")[0].lower()
        # Normalize first name
        first_name = normalize_text(first_name)
        first_name_counts[first_name] = first_name_counts.get(first_name, 0) + 1

    # 1. Clean up OCR text
    normalized_ocr = normalize_text(ocr_text)
    
    # Prepare cleaned lines
    raw_lines = ocr_text.split('\n')
    cleaned_lines = []
    for line in raw_lines:
        line = clean_line(line)
        line = normalize_text(line)
        if line:
            cleaned_lines.append(line)
    
    for member in members:
        if not member.strip():
            continue
            
        # Normalize member name
        normalized_member = normalize_text(member)
        
        # --- Strategy 1: Exact substring match (normalized) ---
        if normalized_member in normalized_ocr:
             present_members.append(member)
             print(f"Matched (Substring): {member}")
             continue
             
        # --- Strategy 2: Concatenated Match (e.g. batuhanaltan) ---
        # Good for "batuhanaltan" vs "Batuhan Altan"
        nospaces_member = normalized_member.replace(" ", "")
        found_concat = False
        for line in cleaned_lines:
            if nospaces_member in line.replace(" ", ""):
                present_members.append(member)
                print(f"Matched (Concatenated): {member} (Line: '{line}')")
                found_concat = True
                break
        if found_concat:
            continue

        # --- Strategy 3: Fuzzy Match using token_set_ratio ---
        best_match = process.extractOne(
            normalized_member, 
            cleaned_lines, 
            scorer=fuzz.token_set_ratio
        )
        
        if best_match and best_match[1] >= 85: 
             present_members.append(member)
             print(f"Matched (Fuzzy Token): {member} (Found: '{best_match[0]}', Score: {best_match[1]})")
             continue
             
        # --- Strategy 4: Unique First Name Fallback ---
        # If "Emre" is unique in the group, and we find "Emre" in the text, match it.
        # This solves "Emre (Patientdesk.ai)" matching "Emre Kaplaner"
        parts = normalized_member.split()
        if len(parts) > 0:
            first_name = parts[0]
            if first_name_counts.get(first_name) == 1:
                # Check if this first name exists in lines (fuzzy or exact)
                # Fuzzy match for just the first name against lines
                best_fn_match = process.extractOne(
                    first_name,
                    cleaned_lines,
                    scorer=fuzz.token_set_ratio # or partial_ratio?
                )
                # Use a slightly stricter threshold for single name to avoid "Ali" matching "Salih" too easily?
                # "Emre" vs "Emre (Patient...)" -> token_set_ratio should be 100
                if best_fn_match and best_fn_match[1] >= 90:
                    present_members.append(member)
                    print(f"Matched (Unique First Name): {member} (Found: '{best_fn_match[0]}', Score: {best_fn_match[1]})")
                    continue
    
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
            
            is_present_from_screenshot = member_name in present_members
            current_val = str(row[col_index - 1]).strip().upper()
            
            # IMPORTANT: Preserve existing TRUE values (manual edits)
            # Only set TRUE if detected in screenshot or already marked TRUE
            # Only set FALSE if NOT detected AND currently not TRUE
            is_already_present = current_val in ["TRUE", "1", "YES"]
            
            if is_already_present:
                # Member is already marked present (possibly manually) - preserve it
                status_val = True
            else:
                # Member not currently marked present - use screenshot detection
                status_val = is_present_from_screenshot
            
            cells_to_update.append(gspread.Cell(row_num, col_index, status_val))
            
        if cells_to_update:
            sheet.update_cells(cells_to_update)
            print(f"Attendance for {date_str} updated successfully ({len(cells_to_update)} cells).")
        else:
             print("No updates needed.")
        
        # Recalculate streaks immediately
        recalculate_missed_streaks(client)

    except Exception as e:
        print(f"Error updating sheet: {e}")

def recalculate_missed_streaks(client):
    """
    Recalculates the '# of Meetings Missed in a Row' for all members
    based on the current state of the sheet.
    """
    if not client:
        return

    try:
        sheet = client.open(config.SHEET_NAME).sheet1
        all_records = sheet.get_all_values()
        headers = all_records[0]
        
        missed_col_name = "# of Meetings Missed in a Row"
        missed_col_index = -1
        
        for idx, h in enumerate(headers):
             if missed_col_name in h:
                 missed_col_index = idx + 1
                 break
        
        if missed_col_index != -1:
             print(f"Updating '{missed_col_name}' column (Index: {missed_col_index})...")
             
             # Identify date columns
             date_indices = []
             for idx, header in enumerate(headers):
                try:
                    dt = datetime.datetime.strptime(header, "%d/%m/%Y")
                    date_indices.append((idx, dt))
                except ValueError:
                    continue
             
             # Sort by date
             date_indices.sort(key=lambda x: x[1])
             
             # Filter out future dates: keep dates <= TODAY
             cutoff_date = datetime.date.today()
                 
             valid_date_indices = []
             for idx, dt in date_indices:
                 if dt.date() <= cutoff_date:
                     valid_date_indices.append(idx)
             
             # Iterate backwards through VALID dates
             for i, row in enumerate(all_records[1:]): # Skip header
                 row_num = i + 2
                 
                 consecutive_misses = 0
                 # Iterate backwards
                 for col_idx in reversed(valid_date_indices):
                     val = row[col_idx]
                     str_val = str(val).strip().upper()
                     
                     # Handle attendance states:
                     # - Empty/"" = No meeting that week, SKIP (don't count, don't reset)
                     # - FALSE = Meeting happened, person was ABSENT (counts as miss)
                     # - TRUE/1/YES = Meeting happened, person was PRESENT (resets streak)
                     
                     if str_val == "":
                         # No screenshot uploaded = no meeting = SKIP this week
                         # Don't count it, but also don't reset the streak
                         continue
                     elif str_val == "FALSE":
                         # Meeting happened, person was absent
                         consecutive_misses += 1
                     elif str_val in ["TRUE", "1", "YES"]:
                         # Meeting happened, person was present - reset streak
                         break
                     else:
                         # Unknown value, skip
                         continue
                 
                 # Cap at 3 for the dropdown options (0, 1, 2, 3)
                 dropdown_val = min(consecutive_misses, 3)
                 
                 current_miss_val = row[missed_col_index - 1]
                 current_val_str = str(current_miss_val).strip()
                 
                 # Check if update needed
                 # Lockout logic: Once someone reaches 3 misses, they stay locked at 3
                 # UNLESS they are marked present for the most recent meeting (manual override)
                 if current_val_str == "3":
                     # Check if the most recent meeting has them marked as present
                     # If so, this is a manual override - respect it and recalculate
                     if valid_date_indices:
                         most_recent_idx = valid_date_indices[-1]  # Last date is most recent
                         most_recent_val = str(row[most_recent_idx]).strip().upper()
                         if most_recent_val in ["TRUE", "1", "YES"]:
                             # Manual override detected - allow recalculation
                             print(f"🔓 Member '{row[0]}' was at 3 misses but attended most recent meeting - unlocking")
                         else:
                             # Still absent for most recent - keep locked at 3
                             continue
                 
                 if str(current_miss_val) != str(dropdown_val):
                     sheet.update_cell(row_num, missed_col_index, dropdown_val)
                     if dropdown_val == 3:
                         print(f"⚠️ ALERT: Member '{row[0]}' has reached 3 consecutive misses! (LOCKED)")
        else:
            print(f"Warning: Column '{missed_col_name}' not found.")

    except Exception as e:
        print(f"Error recalculating streaks: {e}")

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
