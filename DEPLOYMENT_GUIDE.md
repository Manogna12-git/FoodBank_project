# 🚀 Food Bank SMS System - Deployment Guide

## 📋 **Deployment Options**

### **Option 1: Vercel (Recommended - Fastest & Free)**

#### **Step 1: Prepare GitHub Repository**
1. **Create a GitHub repository** (if you haven't already)
2. **Push your code** to GitHub:
   ```bash
   git init
   git add .
   git commit -m "Initial commit - Food Bank SMS System"
   git branch -M main
   git remote add origin https://github.com/yourusername/foodbank-sms-service.git
   git push -u origin main
   ```

#### **Step 2: Deploy to Vercel**
1. **Go to [Vercel.com](https://vercel.com)**
2. **Sign up/Login** with your GitHub account
3. **Click "New Project"**
4. **Import your GitHub repository**
5. **Configure settings**:
   - Framework Preset: Other
   - Build Command: `pip install -r requirements.txt`
   - Output Directory: Leave empty
   - Install Command: Leave empty
6. **Add Environment Variables**:
   ```
   SECRET_KEY=your-secret-key-here
   FOOD_BANK_NAME=Lewisham Food Bank
   FOOD_BANK_PHONE=020-XXXX-XXXX
   BASE_URL=https://your-app-name.vercel.app
   ```
7. **Click "Deploy"**

#### **Step 3: Get Your Public URL**
- Your app will be available at: `https://your-app-name.vercel.app`
- Vercel provides automatic HTTPS and CDN

---

### **Option 2: Railway (Alternative)**

#### **Step 1: Create Railway Account**
1. Go to [Railway.app](https://railway.app)
2. Sign up with GitHub account
3. Get $5 free credit monthly

#### **Step 2: Deploy Your App**
1. **Connect GitHub Repository**:
   - Click "New Project"
   - Select "Deploy from GitHub repo"
   - Choose your repository

2. **Configure Environment Variables**:
   - Go to "Variables" tab
   - Add these variables:
   ```
   SECRET_KEY=your-secret-key-here
   FOOD_BANK_NAME=Lewisham Food Bank
   FOOD_BANK_PHONE=020-XXXX-XXXX
   BASE_URL=https://your-app-name.railway.app
   ```

3. **Deploy**:
   - Railway will automatically detect Python
   - Build and deploy your app
   - Get your public URL

#### **Step 3: Get Your Public URL**
- Your app will be available at: `https://your-app-name.railway.app`
- Share this URL with your team

---

### **Option 3: Render (Alternative)**

#### **Step 1: Create Render Account**
1. Go to [Render.com](https://render.com)
2. Sign up with GitHub account

#### **Step 2: Deploy**
1. **New Web Service**:
   - Connect GitHub repository
   - Select Python environment
   - Build Command: `pip install -r requirements.txt`
   - Start Command: `python foodbank_app.py`

2. **Environment Variables**:
   ```
   SECRET_KEY=your-secret-key-here
   FOOD_BANK_NAME=Lewisham Food Bank
   FOOD_BANK_PHONE=020-XXXX-XXXX
   BASE_URL=https://your-app-name.onrender.com
   ```

---

## 🔧 **Post-Deployment Setup**

### **1. Update BASE_URL**
After deployment, update your `.env` file with the new URL:
```bash
BASE_URL=https://your-app-name.vercel.app
```

### **2. Test Your Deployed App**
1. **Visit your public URL**
2. **Test SMS functionality** (simulation mode)
3. **Test upload links**
4. **Verify all features work**

### **3. Configure Twilio (Optional)**
If you want real SMS:
1. **Get Twilio credentials** (as per previous guide)
2. **Add to environment variables**:
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
- **Photo Upload**: Real upload links
- **Client Management**: Full CRUD operations
- **Staff Portal**: Manual data entry
- **Reports**: Generate annual reports
- **Database**: All data stored securely

### **🔗 Your Public Links:**
- **Main Dashboard**: `https://your-app-name.vercel.app`
- **SMS Requests**: `https://your-app-name.vercel.app/send_sms_requests`
- **Client Management**: `https://your-app-name.vercel.app/view_clients`
- **Staff Portal**: `https://your-app-name.vercel.app/staff_portal`
- **Reports**: `https://your-app-name.vercel.app/generate_report`

---

## 🎯 **Next Steps**

1. **Choose a deployment platform** (Vercel recommended)
2. **Follow the deployment steps**
3. **Get your public URL**
4. **Test all features**
5. **Share with your team**

## 💡 **Tips**

- **Vercel** is the fastest and easiest option
- **Free tiers** are sufficient for testing
- **Simulation mode** works perfectly for demos
- **All features** work the same as local version
- **Database** is automatically managed

---

## 🆘 **Need Help?**

- **Vercel Docs**: https://vercel.com/docs
- **Railway Docs**: https://docs.railway.app
- **Render Docs**: https://render.com/docs

Your Food Bank SMS System will be live and accessible from anywhere! 🎉
