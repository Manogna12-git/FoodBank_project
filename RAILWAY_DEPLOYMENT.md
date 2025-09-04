# 🚀 Railway Deployment Guide for Foodbank SMS Service

## **Prerequisites:**
1. **Railway Account** - Sign up at [railway.app](https://railway.app)
2. **GitHub Repository** - Your code should be on GitHub
3. **Railway CLI** (Optional) - For local testing

## **Step 1: Connect GitHub to Railway**

1. **Go to Railway Dashboard:**
   - Visit [railway.app](https://railway.app)
   - Sign in with GitHub

2. **Create New Project:**
   - Click "New Project"
   - Select "Deploy from GitHub repo"
   - Choose your repository: `Manogna12-git/FoodBank_project`

## **Step 2: Configure Environment Variables**

In Railway Dashboard, go to your project → Variables tab and add:

```bash
FLASK_ENV=production
FLASK_DEBUG=False
SECRET_KEY=your-super-secret-production-key-here
DATABASE_URL=sqlite:///foodbank.db
TWILIO_ACCOUNT_SID=your_twilio_account_sid
TWILIO_AUTH_TOKEN=your_twilio_auth_token
TWILIO_PHONE_NUMBER=your_twilio_phone_number
FOOD_BANK_PHONE=020-XXXX-XXXX
FOOD_BANK_NAME=Lewisham Foodbank
UPLOAD_FOLDER=uploads
MAX_CONTENT_LENGTH=16777216
```

## **Step 3: Deploy**

1. **Automatic Deployment:**
   - Railway will automatically detect your Flask app
   - It will use the `Procfile` and `requirements.txt`
   - Build will start automatically

2. **Monitor Build:**
   - Watch the build logs in Railway dashboard
   - Check for any errors

## **Step 4: Access Your App**

1. **Get Your URL:**
   - Railway will provide a URL like: `https://your-app-name.railway.app`
   - This replaces `localhost:3000`

2. **Test Your App:**
   - Visit the URL in your browser
   - Test all functionality

## **Step 5: Custom Domain (Optional)**

1. **Add Custom Domain:**
   - Go to Settings → Domains
   - Add your custom domain
   - Configure DNS records

## **Important Notes:**

✅ **Production Ready:** Your app is configured for production
✅ **Database:** SQLite will work on Railway (for small apps)
✅ **File Uploads:** Uploads folder will be created automatically
✅ **Environment Variables:** All configurable via Railway dashboard

## **Troubleshooting:**

- **Build Errors:** Check Railway build logs
- **Environment Variables:** Ensure all required vars are set
- **Port Issues:** Railway automatically sets `$PORT` environment variable

## **Next Steps After Deployment:**

1. **Update SMS Links:** Change `localhost:3000` to your Railway URL
2. **Test All Features:** Ensure everything works in production
3. **Monitor Logs:** Use Railway's logging features
4. **Scale if Needed:** Railway can scale your app automatically

---

**Your Foodbank SMS Service will be live on Railway! 🎉**
