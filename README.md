
# Exposure Attendance Automation

This project automates attendance tracking for Exposure meetings using Google Drive screenshots and Google Sheets.

## Prerequisites

1. **Python 3.8+**
2. **Tesseract OCR**: 
   - macOS: `brew install tesseract`
   - Ensure the path is correct in `config.py` (checked `/opt/homebrew/bin/tesseract`).
3. **Google Cloud Credentials**:
   - Create a project in Google Cloud Console.
   - Enable Drive API and Sheets API.
   - Create OAuth 2.0 Client ID credentials.
   - Download `client_secret.json` or copy `client_id` and `client_secret` to `.env`.

## Setup

1. **Clone the repository**:
   ```bash
   git clone <repo-url>
   cd "exposure attendance"
   ```

2. **Create a virtual environment**:
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   ```

3. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

4. **Configure Environment**:
   - Copy `.env.example` to `.env`:
     ```bash
     cp .env.example .env
     ```
   - Fill in your `client_id`, `client_secret`, and Drive Folder IDs.

5. **Run Manually**:
   ```bash
   python drive_monitor.py
   ```

## Background Service (Optional)

To run automatically in the background on macOS:

1. Update `com.onurcelik.exposure_attendance.plist` with your correct absolute paths.
2. Load the service:
   ```bash
   launchctl load com.onurcelik.exposure_attendance.plist
   ```

## Troubleshooting

- **Logs**: Check `monitor.log` and `monitor.err` for errors.
- **Limits**: The consecutive miss limit is set in `config.py` (currently 4).

