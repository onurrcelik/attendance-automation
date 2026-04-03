import sys
from PIL import Image
import pytesseract

def test_ocr(image_path):
    print(f"Testing OCR on {image_path}...")
    try:
        text = pytesseract.image_to_string(Image.open(image_path))
        print("--- Extracted Text ---")
        print(text)
        print("----------------------")
    except Exception as e:
        print(f"OCR Error: {e}")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 test_ocr.py <image_path>")
    else:
        test_ocr(sys.argv[1])
