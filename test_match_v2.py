import main

members = [
    "Onur Celik", 
    "Batuhan Altan", 
    "Emre Kaplaner", 
    "Şan Fikri Köktas",
    "Efe Berke" # checking ambiguity with Emre? No, distinct.
]

ocr_cases = [
    ("Onur's Iphone (me)", "Onur Celik"),
    ("batuhanaltan", "Batuhan Altan"),
    ("Emre (Patientdesk.ai)", "Emre Kaplaner"),
    ("Fikri Koktas (Host)", "Şan Fikri Köktas"),
    ("Onur Gelik (me)", "Onur Celik") # typo + noise
]

ocr_text = "\n".join([c[0] for c in ocr_cases])

print("Testing V2 matching strategies...")
print(f"OCR Text:\n{ocr_text}\n")

present_members = main.match_attendance(ocr_text, members)

print("\n--- Results ---")
passed_all = True
for ocr_line, expected_member in ocr_cases:
    if expected_member in present_members:
        print(f"PASS: '{ocr_line}' matched -> {expected_member}")
    else:
        print(f"FAIL: '{ocr_line}' FAILED to match -> {expected_member}")
        passed_all = False

if passed_all:
    print("\nALL TESTS PASSED")
else:
    print("\nSOME TESTS FAILED")
