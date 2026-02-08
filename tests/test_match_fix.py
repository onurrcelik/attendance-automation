import main

members = ["Şan Fikri Köktas", "Onur Celik", "Batuhan Altan"]
ocr_text = """
Onur Celik (me)
Fikri Koktas (Host)
Batuhan Altan
Random Person
"""

print("Testing improved matching...")
present = main.match_attendance(ocr_text, members)
print("\nPresent Members:")
for p in present:
    print(f"- {p}")

expected = ["Şan Fikri Köktas", "Onur Celik", "Batuhan Altan"]
for exp in expected:
    if exp in present:
        print(f"PASS: {exp} found.")
    else:
        print(f"FAIL: {exp} NOT found.")
