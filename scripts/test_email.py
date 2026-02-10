#!/usr/bin/env python3
"""
Test script for email service
"""
import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from api.email_service import get_email_service

def test_email():
    # Load env
    load_dotenv()
    
    username = os.getenv("EMAIL_USERNAME")
    password = os.getenv("EMAIL_APP_PASSWORD")
    
    print(f"📧 Testing Email Service...")
    print(f"   Username: {username}")
    print(f"   Password: {'****' if password else 'MISSING'}")
    
    if not username or "your_email" in username:
        print("\n❌ Error: Please update your .env file with real Gmail credentials.")
        print("   Current values look like placeholders.")
        return

    email_service = get_email_service()
    
    recipient = input("\nEnter recipient email for test: ")
    if not recipient:
        recipient = username
        
    print(f"⏳ Sending test email to {recipient}...")
    
    success = email_service.send_email(
        to_email=recipient,
        subject="JobDetector Email Test",
        html_content="<h1>Test Successful!</h1><p>Your JobDetector email service is now working correctly.</p>"
    )
    
    if success:
        print("\n✅ Success! Please check your inbox (and spam folder).")
    else:
        print("\n❌ Failed! Check the console output for error messages.")
        print("   Common issues:")
        print("   1. Gmail 'App Password' is required (not your regular password)")
        print("   2. 2-Step Verification must be enabled on Gmail")

if __name__ == "__main__":
    test_email()
