import sys
import random
import datetime
import main as attendance_script
import config

def run_test_scenario(date_str):
    print(f"--- Running Test Scenario for {date_str} ---")
    
    # Parse date
    try:
        target_date = datetime.datetime.strptime(date_str, "%d/%m/%Y").date()
    except ValueError:
        print("Invalid date format. Use DD/MM/YYYY")
        return

    print("Authenticating...")
    client = attendance_script.get_google_sheet_client()
    if not client:
        return

    # Get members
    members = attendance_script.get_members(client.open(config.SHEET_NAME))
    print(f"Loaded {len(members)} members.")
    
    # 1. Randomly select attendance (approx 50% attend)
    present_members = []
    for member in members:
        if random.random() > 0.5: # 50% chance
            present_members.append(member)
            
    print(f"Simulating attendance for: {len(present_members)} people.")
    print(f"Attendees: {present_members}")
    
    # 2. Update Sheet
    # This will write TRUE/FALSE to the column matching date_str
    # AND it will update the Missed Count using date_str as the cutoff
    attendance_script.update_sheet_attendance(client, present_members, target_date)
    print("Scenario complete.\n")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 test_scenario.py <DD/MM/YYYY>")
    else:
        run_test_scenario(sys.argv[1])
