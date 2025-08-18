#!/usr/bin/env python3
"""
Test script to verify SMS functionality and upload links
"""

import requests
import json
import time

BASE_URL = "http://localhost:3000"

def test_sms_status():
    """Test SMS configuration and status"""
    print("🔍 Testing SMS Status...")
    try:
        response = requests.get(f"{BASE_URL}/debug/sms_status")
        if response.status_code == 200:
            data = response.json()
            print(f"✅ Twilio Configured: {data['twilio_configured']}")
            print(f"📱 Base URL: {data['base_url']}")
            print(f"🏠 Food Bank: {data['food_bank_name']}")
            print(f"📞 Phone: {data['food_bank_phone']}")
            
            if data['recent_sms_logs']:
                print("\n📋 Recent SMS Logs:")
                for log in data['recent_sms_logs']:
                    print(f"  - {log['client_name']}: {log['status']} ({log['phone']})")
                    if log['error']:
                        print(f"    Error: {log['error']}")
            else:
                print("📋 No recent SMS logs found")
        else:
            print(f"❌ Failed to get SMS status: {response.status_code}")
    except Exception as e:
        print(f"❌ Error testing SMS status: {e}")

def test_upload_link(unique_link):
    """Test if an upload link is working"""
    print(f"\n🔗 Testing upload link: {unique_link}")
    try:
        response = requests.get(f"{BASE_URL}/test_upload/{unique_link}")
        if response.status_code == 200:
            data = response.json()
            print(f"✅ Link valid for: {data['client_name']}")
            print(f"📅 Expires: {data['expires_at']}")
            print(f"🔗 Upload URL: {data['upload_url']}")
        else:
            print(f"❌ Link invalid: {response.status_code}")
    except Exception as e:
        print(f"❌ Error testing upload link: {e}")

def main():
    print("🚀 Food Bank SMS System Test")
    print("=" * 40)
    
    # Test SMS status
    test_sms_status()
    
    # Test a sample upload link (you'll need to replace this with a real one)
    print("\n" + "=" * 40)
    print("💡 To test upload links, run this script after sending an SMS")
    print("   and replace the unique_link with the actual link from the SMS log")
    
    # Example of how to test an upload link
    # test_upload_link("your-unique-link-here")

if __name__ == "__main__":
    main()
