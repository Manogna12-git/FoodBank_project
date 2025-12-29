# 🚀 Food Bank SMS System - Deployment Guide

## 📋 **Deployment to Render (Recommended - Free Tier)**

### **Step 1: Create Render Account**
1. Go to [Render.com](https://render.com)
2. Sign up with your **GitHub account**

### **Step 2: Create New Web Service**
1. Click **"New +"** → **"Web Service"**
2. Connect your **FoodBank_project** GitHub repository
3. Configure settings:
   - **Name**: `foodbank-sms-service`
   - **Environment**: `Python 3`
   - **Region**: Choose closest to your users
   - **Branch**: `main`
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `gunicorn foodbank_app:app --bind 0.0.0.0:$PORT`

### **Step 3: Add Environment Variables**
Click **"Advanced"** and add these environment variables:
```
SECRET_KEY=your-secret-key-here
FOOD_BANK_NAME=Lewisham Food Bank
FOOD_BANK_PHONE=020-XXXX-XXXX
BASE_URL=https://your-app-name.onrender.com
FLASK_ENV=production
```

### **Step 4: Select Free Plan**
- Choose **"Free"** instance type
- Click **"Create Web Service"**

### **Step 5: Wait for Deployment**
- Render will automatically build and deploy your app
- First deployment takes 2-5 minutes
- You'll get a public URL like: `https://foodbank-sms-service.onrender.com`

---

## 🔧 **Post-Deployment Setup**

### **1. Test Your Deployed App**
1. Visit your public URL
2. Test the dashboard loads correctly
3. Test adding a client
4. Test sending SMS (simulation mode)
5. Test export functions (PDF, Excel, CSV)

### **2. Configure Twilio (Optional)**
If you want real SMS functionality:
1. Get Twilio credentials from [twilio.com](https://twilio.com)
2. Add to Render environment variables:
   ```
   TWILIO_ACCOUNT_SID=your_account_sid
   TWILIO_AUTH_TOKEN=your_auth_token
   TWILIO_PHONE_NUMBER=your_twilio_number
   ```

---

## 📱 **Features Available After Deployment**

### **✅ What Works:**
- **Public URL**: Accessible from anywhere
- **SMS Simulation**: Test SMS functionality
- **Photo Upload**: Real upload links work
- **Client Management**: Full CRUD operations
- **Staff Portal**: Manual data entry
- **Reports**: PDF, Excel, CSV exports
- **Database**: SQLite stored on Render

### **🔗 Your Public Links:**
- **Main Dashboard**: `https://your-app-name.onrender.com`
- **Clients**: `https://your-app-name.onrender.com/view_clients`
- **Send SMS**: `https://your-app-name.onrender.com/send_sms_requests`
- **Staff Portal**: `https://your-app-name.onrender.com/staff_portal`
- **Reports**: `https://your-app-name.onrender.com/generate_report`

---

## ⚠️ **Important Notes**

### **Free Tier Limitations:**
- App may sleep after 15 minutes of inactivity
- First request after sleep takes ~30 seconds
- 750 free hours per month

### **For Production Use:**
- Consider upgrading to paid tier for always-on service
- Add persistent disk for database backup
- Configure custom domain if needed

---

## 🆘 **Troubleshooting**

### **Build Fails:**
- Check `requirements.txt` has all dependencies
- Ensure Python version compatibility

### **App Crashes:**
- Check Render logs for errors
- Verify environment variables are set correctly

### **Database Issues:**
- SQLite works but resets on redeploy (free tier)
- Consider PostgreSQL for persistent data

---

## 💡 **Tips**

- **Auto-deploy**: Render automatically deploys on GitHub push
- **Logs**: Check Render dashboard for real-time logs
- **Environment**: Use environment variables for secrets
- **Testing**: Always test locally before pushing

Your Food Bank SMS System will be live and accessible from anywhere! 🎉
