# Twilio Setup Guide for Real SMS Messages

## 🔧 **Step 1: Get Your Twilio Credentials**

### 1.1 Go to Twilio Console
- Visit: https://console.twilio.com/
- Sign in to your Twilio account

### 1.2 Get Account SID
- Your Account SID is displayed on the main dashboard
- It starts with "AC" (e.g., `AC2fad7137768fc75868e78`)
- ✅ **Your Account SID looks correct**

### 1.3 Regenerate Auth Token
- Click on your **Account Name** (top right corner)
- Go to **"Account"** → **"API Keys & Tokens"**
- Find the **"Auth Token"** section
- Click **"Regenerate"** button
- **Copy the new Auth Token** (it will be different from your current one)

### 1.4 Get Your Twilio Phone Number
- Go to **"Phone Numbers"** → **"Manage"** → **"Active numbers"**
- Copy your actual Twilio phone number
- It should look like: `+447700900000` (not `+447XXXXXXXXX`)

## 🔧 **Step 2: Update Your .env File**

Replace the values in your `.env` file:

```bash
# Food Bank SMS Service Environment Variables
SECRET_KEY=food-bank-secret-key-change-this-in-production-2025

# Your actual Twilio credentials (UPDATE THESE)
TWILIO_ACCOUNT_SID=AC2fad7137768fc75868e78
TWILIO_AUTH_TOKEN=your_new_auth_token_here
TWILIO_PHONE_NUMBER=+447700900000

DATABASE_URL=sqlite:///foodbank.db
UPLOAD_FOLDER=uploads
```

## 🔧 **Step 3: Test Your Credentials**

After updating your `.env` file, run:

```bash
python test_twilio.py
```

You should see:
```
✅ Authentication successful!
✅ Found 1 phone number(s)
   📞 +447700900000 (Your Number Name)
```

## 🔧 **Step 4: Test Real SMS**

Once credentials are working:

1. **Restart the application**:
   ```bash
   python foodbank_app.py
   ```

2. **Go to the web interface**: http://localhost:3000

3. **Click "📤 Send SMS Requests"**

4. **Select a client and send SMS**

5. **Check your phone** - you should receive a real SMS!

## 🚨 **Common Issues**

### Issue: "Authentication Error - invalid username"
**Solution**: Your Auth Token is incorrect. Regenerate it in Twilio Console.

### Issue: "No phone numbers found"
**Solution**: You need to purchase a Twilio phone number first.

### Issue: "Account suspended"
**Solution**: Your Twilio account needs to be verified or has billing issues.

## 💡 **Free Trial Notes**

- Twilio offers a free trial with $15-20 credit
- You can send SMS messages during the trial
- After trial, you'll need to add payment method
- SMS costs vary by country (usually $0.01-0.05 per message)

## 📞 **Need Help?**

- **Twilio Support**: https://support.twilio.com/
- **Twilio Documentation**: https://www.twilio.com/docs/
- **Test your credentials**: Run `python test_twilio.py`
