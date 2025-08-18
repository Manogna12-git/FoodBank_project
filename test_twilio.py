#!/usr/bin/env python3
"""
Test Twilio credentials and SMS functionality
"""

import os
from dotenv import load_dotenv
from twilio.rest import Client
from twilio.base.exceptions import TwilioException

# Load environment variables
load_dotenv()

def test_twilio_credentials():
    """Test Twilio credentials"""
    print("🔍 Testing Updated Twilio Credentials...")
    print("=" * 50)
    
    # Get credentials
    account_sid = os.getenv('TWILIO_ACCOUNT_SID')
    auth_token = os.getenv('TWILIO_AUTH_TOKEN')
    phone_number = os.getenv('TWILIO_PHONE_NUMBER')
    
    print(f"Account SID: {account_sid}")
    print(f"Auth Token: {auth_token[:10]}..." if auth_token else "Auth Token: Not set")
    print(f"Phone Number: {phone_number}")
    print()
    
    # Validate format
    if not account_sid or not account_sid.startswith('AC'):
        print("❌ Invalid Account SID format (should start with 'AC')")
        return False
    
    if not auth_token or len(auth_token) < 20:
        print("❌ Invalid Auth Token (too short)")
        return False
    
    if not phone_number or not phone_number.startswith('+'):
        print("❌ Invalid Phone Number (should start with '+')")
        return False
    
    print("✅ Credential format looks valid")
    
    # Test Twilio API
    try:
        client = Client(account_sid, auth_token)
        
        # Try to get account info (this will fail if credentials are invalid)
        account = client.api.accounts(account_sid).fetch()
        print(f"✅ Authentication successful!")
        print(f"   Account Name: {account.friendly_name}")
        print(f"   Account Status: {account.status}")
        
        # Test phone number
        incoming_phone_numbers = client.incoming_phone_numbers.list()
        if incoming_phone_numbers:
            print(f"✅ Found {len(incoming_phone_numbers)} phone number(s)")
            for number in incoming_phone_numbers:
                print(f"   📞 {number.phone_number} ({number.friendly_name})")
        else:
            print("⚠️  No phone numbers found in your account")
        
        return True
        
    except TwilioException as e:
        print(f"❌ Twilio Authentication Failed: {e}")
        print("\n💡 Common solutions:")
        print("   1. Check your Account SID is correct")
        print("   2. Regenerate your Auth Token in Twilio Console")
        print("   3. Make sure your account is active")
        return False
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        return False

def test_sms_sending():
    """Test SMS sending functionality"""
    print("\n📱 Testing SMS Sending...")
    print("=" * 30)
    
    account_sid = os.getenv('TWILIO_ACCOUNT_SID')
    auth_token = os.getenv('TWILIO_AUTH_TOKEN')
    from_number = os.getenv('TWILIO_PHONE_NUMBER')
    
    # Test phone number (you can change this to your own number)
    test_number = "+447587731869"  # Your phone number for testing
    
    try:
        client = Client(account_sid, auth_token)
        
        message = client.messages.create(
            body="🧪 Test SMS from Food Bank System - If you receive this, SMS is working!",
            from_=from_number,
            to=test_number
        )
        
        print(f"✅ SMS sent successfully!")
        print(f"   Message SID: {message.sid}")
        print(f"   Status: {message.status}")
        print(f"   To: {test_number}")
        print(f"   From: {from_number}")
        
        return True
        
    except TwilioException as e:
        print(f"❌ SMS sending failed: {e}")
        return False
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        return False

if __name__ == "__main__":
    print("🚀 Testing Food Bank SMS System Credentials")
    print("=" * 60)
    
    # Test credentials first
    if test_twilio_credentials():
        print("\n" + "=" * 60)
        # If credentials work, test SMS sending
        test_sms_sending()
    else:
        print("\n❌ Credentials failed - cannot test SMS sending")
    
    print("\n" + "=" * 60)
    print("�� Test completed!")
