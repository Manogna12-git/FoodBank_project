# 🏠 Food Bank SMS System

A comprehensive SMS-based fuel support system for food banks, designed to help clients upload required documents (meter readings and identity photos) for fuel assistance.

## 🚀 Features

- **📱 SMS Management**: Send personalized SMS messages with secure upload links
- **📤 Document Upload**: Mobile-optimized interface for photo uploads
- **👥 Client Management**: Full CRUD operations for client data
- **🏢 Staff Portal**: Manual processing for non-camera phone clients
- **📊 Reports**: Generate comprehensive annual reports
- **🔒 GDPR Compliant**: Built-in data protection and consent management
- **💰 Cost-Effective**: Simulation mode for testing, optional real SMS

## 🛠️ Technology Stack

- **Backend**: Python 3.11, Flask
- **Database**: SQLite (with PostgreSQL support)
- **SMS**: Twilio API (with simulation mode)
- **Frontend**: HTML/CSS with Bootstrap styling
- **Deployment**: Vercel, Railway, or Render ready

## 📋 Requirements

- Python 3.11+
- Flask
- Flask-SQLAlchemy
- Twilio (optional)
- Python-dotenv

## 🚀 Quick Start

### 1. Clone the Repository
```bash
git clone https://github.com/yourusername/foodbank-sms-service.git
cd foodbank-sms-service
```

### 2. Install Dependencies
```bash
pip install -r requirements.txt
```

### 3. Configure Environment
Create a `.env` file:
```bash
SECRET_KEY=your-secret-key-here
FOOD_BANK_NAME=Lewisham Food Bank
FOOD_BANK_PHONE=020-XXXX-XXXX
BASE_URL=http://localhost:3000

# Optional: Twilio for real SMS
TWILIO_ACCOUNT_SID=your_twilio_account_sid
TWILIO_AUTH_TOKEN=your_twilio_auth_token
TWILIO_PHONE_NUMBER=your_twilio_phone_number
```

### 4. Run the Application
```bash
python foodbank_app.py
```

### 5. Access the Dashboard
Open your browser and go to: `http://localhost:3000`

## 🌐 Deployment

### Option 1: Vercel (Recommended)

1. **Push to GitHub**:
   ```bash
   git add .
   git commit -m "Initial commit"
   git push origin main
   ```

2. **Deploy to Vercel**:
   - Go to [Vercel.com](https://vercel.com)
   - Import your GitHub repository
   - Add environment variables
   - Deploy

### Option 2: Railway

1. **Connect to Railway**:
   - Go to [Railway.app](https://railway.app)
   - Import your GitHub repository
   - Configure environment variables
   - Deploy

### Option 3: Render

1. **Deploy to Render**:
   - Go to [Render.com](https://render.com)
   - Create new Web Service
   - Connect your repository
   - Configure build settings

## 📱 Usage

### For Staff:
1. **Add Clients**: Use the quick-add form or detailed client management
2. **Send SMS**: Select clients and send fuel support requests
3. **Monitor**: Track SMS history and upload status
4. **Process**: Use staff portal for manual data entry

### For Clients:
1. **Receive SMS**: Get personalized message with upload link
2. **Upload Documents**: Submit meter reading and identity photos
3. **Complete**: System automatically processes the request

## 🔧 Configuration

### Environment Variables

| Variable | Description | Required |
|----------|-------------|----------|
| `SECRET_KEY` | Flask secret key | Yes |
| `FOOD_BANK_NAME` | Organization name | Yes |
| `FOOD_BANK_PHONE` | Contact phone number | Yes |
| `BASE_URL` | Application URL | Yes |
| `TWILIO_ACCOUNT_SID` | Twilio Account SID | No |
| `TWILIO_AUTH_TOKEN` | Twilio Auth Token | No |
| `TWILIO_PHONE_NUMBER` | Twilio Phone Number | No |

### Database

The system uses SQLite by default. For production, consider PostgreSQL:

```python
# Update in foodbank_app.py
app.config['SQLALCHEMY_DATABASE_URI'] = 'postgresql://user:pass@localhost/dbname'
```

## 📊 Features Overview

### SMS System
- ✅ Personalized messages with client names
- ✅ Secure, time-limited upload links (48 hours)
- ✅ Simulation mode for testing
- ✅ Real SMS via Twilio (optional)
- ✅ Comprehensive logging and tracking

### Document Upload
- ✅ Mobile-optimized interface
- ✅ Support for meter readings and identity photos
- ✅ File validation and security
- ✅ Automatic file naming and storage

### Client Management
- ✅ Add, edit, delete clients
- ✅ Search and filter functionality
- ✅ Bulk operations
- ✅ GDPR consent tracking
- ✅ Export to CSV

### Staff Portal
- ✅ Manual data entry for non-camera phones
- ✅ Pending request management
- ✅ Document verification interface

### Reporting
- ✅ Annual reports with statistics
- ✅ System health monitoring
- ✅ Performance metrics
- ✅ Recommendations for improvement

## 🔒 Security & Compliance

- **GDPR Compliance**: Built-in consent management
- **Data Encryption**: Secure file storage
- **Access Control**: Staff-only administrative interface
- **Audit Logging**: Complete activity tracking
- **Data Retention**: Configurable retention policies

## 🆘 Support

### Common Issues

1. **SMS Not Sending**:
   - Check Twilio credentials in `.env`
   - Verify phone number format
   - Use simulation mode for testing

2. **Upload Links Not Working**:
   - Ensure `BASE_URL` is correctly set
   - Check server is running
   - Verify link expiration

3. **Database Issues**:
   - Delete `instance/foodbank.db` to reset
   - Check file permissions
   - Verify SQLite installation

### Getting Help

- **Documentation**: Check the deployment guide
- **Issues**: Create a GitHub issue
- **Email**: Contact your system administrator

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Test thoroughly
5. Submit a pull request

## 📄 License

This project is licensed under the MIT License - see the LICENSE file for details.

## 🙏 Acknowledgments

- Built for food banks and community organizations
- Designed with accessibility and ease of use in mind
- Supports both digital and manual processes

---

**Made with ❤️ for community support organizations**
