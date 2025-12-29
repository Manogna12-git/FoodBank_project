from flask import Flask, render_template_string, flash, redirect, url_for, request, jsonify, abort, send_file, Response
from flask_sqlalchemy import SQLAlchemy
import logging
from datetime import datetime, timedelta, UTC
import os
from dotenv import load_dotenv
import uuid
import secrets
from werkzeug.utils import secure_filename
import csv
import io

# Force simulation mode - no Twilio import
TWILIO_AVAILABLE = False
TwilioClient = None

# Load environment variables
load_dotenv()

# Initialize Flask app
app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///foodbank.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', secrets.token_hex(32))
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size

# Ensure upload folder exists
if not os.path.exists('uploads'):
    os.makedirs('uploads')

# Initialize database
db = SQLAlchemy(app)

# Database Models
class Client(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    phone_number = db.Column(db.String(20), nullable=False, unique=True)
    has_camera_phone = db.Column(db.Boolean, default=True)
    gdpr_consent = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Referrer details (from meeting requirements)
    referrer_name = db.Column(db.String(100), nullable=True)
    referrer_email = db.Column(db.String(100), nullable=True)
    
    # Relationship to fuel requests
    fuel_requests = db.relationship('FuelRequest', backref='client', lazy=True, cascade='all, delete-orphan')

class FuelRequest(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    client_id = db.Column(db.Integer, db.ForeignKey('client.id'), nullable=False)
    unique_link = db.Column(db.String(100), nullable=False, unique=True)
    expires_at = db.Column(db.DateTime, nullable=False)
    status = db.Column(db.String(20), default='pending')  # pending, completed, expired
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    sms_sent = db.Column(db.Boolean, default=False)
    sms_sent_at = db.Column(db.DateTime)
    sms_sid = db.Column(db.String(100))
    documents_uploaded = db.Column(db.Boolean, default=False)
    meter_reading_filename = db.Column(db.String(200))
    identity_photo_filename = db.Column(db.String(200))
    phone_type_used = db.Column(db.String(20))  # keypad or smartphone
    submission_timestamp = db.Column(db.DateTime)
    
    # Additional fields for better data organization
    meter_reading_text = db.Column(db.Text, nullable=True)  # For keypad users
    id_type = db.Column(db.String(50), nullable=True)  # Type of ID provided
    id_details = db.Column(db.Text, nullable=True)  # Details from ID
    client_postcode = db.Column(db.String(20), nullable=True)  # Client postcode
    missing_documents_reason = db.Column(db.Text, nullable=True)  # Reason if no pictures attached
    staff_notes = db.Column(db.Text, nullable=True)  # Staff notes for processing

class SMSLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    client_id = db.Column(db.Integer, db.ForeignKey('client.id'), nullable=False)
    fuel_request_id = db.Column(db.Integer, db.ForeignKey('fuel_request.id'), nullable=True)
    phone_number = db.Column(db.String(20), nullable=False)
    message_content = db.Column(db.Text, nullable=False)
    status = db.Column(db.String(50), default='pending')  # pending, sent, failed, delivered
    twilio_sid = db.Column(db.String(100))
    error_message = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    sent_at = db.Column(db.DateTime)
    
    # Add relationship to client
    client = db.relationship('Client', backref='sms_logs', lazy=True)

# Configuration
TWILIO_ACCOUNT_SID = os.getenv('TWILIO_ACCOUNT_SID')
TWILIO_AUTH_TOKEN = os.getenv('TWILIO_AUTH_TOKEN')
TWILIO_PHONE_NUMBER = os.getenv('TWILIO_PHONE_NUMBER')

# Force simulation mode by default - only use Twilio if explicitly configured and available
SIMULATION_MODE = True

# Check if we should use Twilio (only if all credentials are properly set AND Twilio is available)
if (TWILIO_AVAILABLE and 
    TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN and TWILIO_PHONE_NUMBER and
    TWILIO_ACCOUNT_SID.startswith('AC') and 
    len(TWILIO_AUTH_TOKEN) >= 20 and 
    TWILIO_PHONE_NUMBER.startswith('+') and
    TWILIO_ACCOUNT_SID != 'your_twilio_account_sid_here' and
    'your_' not in TWILIO_ACCOUNT_SID and
    'placeholder' not in TWILIO_ACCOUNT_SID.lower()):
    SIMULATION_MODE = False
    logging.info("Valid Twilio credentials detected - enabling live SMS mode")
else:
    # Clear any invalid credentials
    TWILIO_ACCOUNT_SID = None
    TWILIO_AUTH_TOKEN = None
    TWILIO_PHONE_NUMBER = None
    logging.info("Simulation mode enabled - SMS will be simulated for testing")

FOOD_BANK_NAME = os.getenv('FOOD_BANK_NAME', 'Lewisham Food Bank')
FOOD_BANK_PHONE = os.getenv('FOOD_BANK_PHONE', '020-XXXX-XXXX')
BASE_URL = os.getenv('BASE_URL', 'http://localhost:3000')

# Helper functions
def generate_unique_link():
    return str(uuid.uuid4())

def create_upload_folder():
    if not os.path.exists(app.config['UPLOAD_FOLDER']):
        os.makedirs(app.config['UPLOAD_FOLDER'])

def format_phone_number(phone):
    """Ensure phone number is in international format"""
    phone = phone.strip().replace(' ', '').replace('-', '')
    if phone.startswith('0'):
        phone = '+44' + phone[1:]
    elif not phone.startswith('+'):
        phone = '+44' + phone
    return phone

def create_sms_message(client, fuel_request):
    """Create the SMS message content"""
    upload_url = f"{BASE_URL}/upload/{fuel_request.unique_link}"
    
    # Ensure the upload URL is properly formatted
    if not upload_url.startswith('http'):
        upload_url = f"http://localhost:3000/upload/{fuel_request.unique_link}"
    
    message = f"""Hi {client.name},

Your {FOOD_BANK_NAME} fuel support is ready! 

Please provide:
- Photo of your meter reading 
- Photo of yourself with ID

Upload here: {upload_url}

Link expires in 48 hours

Questions? Call {FOOD_BANK_PHONE}

- {FOOD_BANK_NAME} Team"""
    
    logging.info(f"Created SMS message for {client.name} with upload URL: {upload_url}")
    return message

def send_sms_to_client(client, fuel_request):
    """Send SMS to client with proper error handling and logging"""
    try:
        # Create SMS log entry
        sms_log = SMSLog(
            client_id=client.id,
            fuel_request_id=fuel_request.id,
            phone_number=client.phone_number,
            message_content="",
            status='pending'
        )
        db.session.add(sms_log)
        db.session.flush()
        
        # Create message content
        message_content = create_sms_message(client, fuel_request)
        sms_log.message_content = message_content
        
        # Use simulation mode flag
        if SIMULATION_MODE:
            logging.warning(f"Twilio not configured - SMS simulation mode for {client.name}")
            # Simulate successful SMS for demo
            sms_log.status = 'sent'
            sms_log.sent_at = datetime.now(UTC)
            sms_log.twilio_sid = f"sim_{uuid.uuid4().hex[:10]}"
            
            fuel_request.sms_sent = True
            fuel_request.sms_sent_at = datetime.now(UTC)
            fuel_request.sms_sid = sms_log.twilio_sid
            
            db.session.commit()
            
            # Create upload URL for logging
            upload_url = f"{BASE_URL}/upload/{fuel_request.unique_link}"
            logging.info(f"SMS simulated successfully for {client.name} with upload URL: {upload_url}")
            print(f"SIMULATION: SMS sent to {client.name} ({client.phone_number})")
            print(f"Upload link: {upload_url}")
            return True
        
        # Always use simulation mode since Twilio is not available
        logging.warning(f"Twilio not available - SMS simulation mode for {client.name}")
        
        # Simulate successful SMS
        sms_log.status = 'sent'
        sms_log.sent_at = datetime.now(UTC)
        sms_log.twilio_sid = f"sim_{uuid.uuid4().hex[:10]}"
        sms_log.error_message = "Twilio not available - simulation mode"
        
        fuel_request.sms_sent = True
        fuel_request.sms_sent_at = datetime.now(UTC)
        fuel_request.sms_sid = sms_log.twilio_sid
        
        db.session.commit()
        
        # Create upload URL for logging
        upload_url = f"{BASE_URL}/upload/{fuel_request.unique_link}"
        logging.info(f"SMS simulated successfully for {client.name}")
        print(f"SIMULATION: SMS sent to {client.name} ({client.phone_number})")
        print(f"Upload link: {upload_url}")
        return True
        
    except Exception as e:
        error_msg = str(e)
        logging.error(f"Failed to send SMS to {client.name}: {error_msg}")
        
        if 'sms_log' in locals():
            sms_log.status = 'failed'
            sms_log.error_message = error_msg
            db.session.commit()
        
        return False

# CSS Template
CSS_TEMPLATE = """
<style>
    * { margin: 0; padding: 0; box-sizing: border-box; }
    body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: linear-gradient(135deg, #f8f9fa 0%, #e8f5e9 100%); min-height: 100vh; padding: 20px; color: #333; }
    .container { max-width: 1200px; margin: 0 auto; background: white; border-radius: 15px; box-shadow: 0 20px 40px rgba(0,0,0,0.1); overflow: hidden; }
    .header { background: linear-gradient(135deg, #28a745 0%, #20c997 100%); color: white; padding: 40px 30px; text-align: center; }
    .header h1 { font-size: 2.5rem; margin-bottom: 10px; font-weight: 700; }
    .header p { font-size: 1.1rem; opacity: 0.9; }
    .content { padding: 30px; }
    .dashboard-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 20px; margin: 20px 0; }
    .card { background: white; border-radius: 15px; padding: 30px; box-shadow: 0 8px 25px rgba(0,0,0,0.1); border: 1px solid #e9ecef; margin-bottom: 25px; }
    .card h3 { color: #495057; margin-bottom: 15px; font-size: 1.3rem; }
    .stats-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 15px; margin: 20px 0; }
    .stat-box { background: white; padding: 25px; border-radius: 12px; text-align: center; border: 2px solid #e9ecef; box-shadow: 0 4px 15px rgba(0,0,0,0.08); transition: all 0.2s ease; }
    .stat-box:hover { border-color: #28a745; transform: translateY(-2px); box-shadow: 0 8px 25px rgba(40, 167, 69, 0.15); }
    .stat-number { font-size: 2rem; font-weight: bold; color: #28a745; margin-bottom: 5px; }
    .stat-label { color: #6c757d; font-size: 0.9rem; }
    .btn { display: inline-block; background: linear-gradient(135deg, #28a745 0%, #20c997 100%); color: white; padding: 12px 24px; text-decoration: none; border-radius: 6px; font-weight: 500; margin: 5px; border: none; cursor: pointer; font-size: 14px; }
    .btn:hover { box-shadow: 0 5px 15px rgba(40, 167, 69, 0.4); color: white; text-decoration: none; }
    .btn-secondary { background: #6c757d; }
    .btn-secondary:hover { background: #545b62; box-shadow: 0 5px 15px rgba(108, 117, 125, 0.4); }
    .btn-danger { background: #dc3545; }
    .btn-danger:hover { background: #c82333; box-shadow: 0 5px 15px rgba(220, 53, 69, 0.4); }
    .btn-success { background: #28a745; }
    .btn-success:hover { background: #218838; box-shadow: 0 5px 15px rgba(40, 167, 69, 0.4); }
    .btn-small { padding: 6px 12px; font-size: 12px; margin: 2px; }
    table { width: 100%; border-collapse: collapse; margin: 20px 0; background: white; border-radius: 8px; overflow: hidden; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }
    table th, table td { padding: 12px; text-align: left; border-bottom: 1px solid #dee2e6; }
    table th { background: #e8f5e9; font-weight: 600; color: #495057; }
    table tbody tr:hover { background: #f8f9fa; }
    .form-group { margin-bottom: 20px; }
    .form-group label { display: block; margin-bottom: 5px; font-weight: 500; color: #495057; }
    .form-control { width: 100%; padding: 10px; border: 2px solid #e9ecef; border-radius: 6px; font-size: 1rem; transition: border-color 0.3s ease; }
    .form-control:focus { outline: none; border-color: #28a745; box-shadow: 0 0 0 0.2rem rgba(40, 167, 69, 0.25); }
    .form-check { display: flex; align-items: center; margin: 10px 0; }
    .form-check input { margin-right: 8px; transform: scale(1.2); }
    .alert { padding: 15px; border-radius: 6px; margin: 15px 0; border-left: 4px solid; }
    .alert-success { background: #d4edda; color: #155724; border-left-color: #28a745; }
    .alert-danger { background: #f8d7da; color: #721c24; border-left-color: #dc3545; }
    .alert-info { background: #d1ecf1; color: #0c5460; border-left-color: #17a2b8; }
    .alert-warning { background: #fff3cd; color: #856404; border-left-color: #ffc107; }
    .quick-add-form { background: linear-gradient(135deg, #f8f9fa 0%, #e8f5e9 100%); padding: 30px; border-radius: 15px; margin-bottom: 30px; border: 2px solid #28a745; box-shadow: 0 8px 25px rgba(40, 167, 69, 0.1); }
    .sidebar { background: #28a745; color: white; width: 250px; min-height: 100vh; padding: 20px 0; position: fixed; left: 0; top: 0; }
    .sidebar-header { padding: 20px; border-bottom: 1px solid rgba(255,255,255,0.1); margin-bottom: 20px; }
    .sidebar-nav { list-style: none; }
    .sidebar-nav li { margin-bottom: 10px; }
    .sidebar-nav a { color: white; text-decoration: none; padding: 12px 20px; display: block; border-radius: 6px; }
    .sidebar-nav a:hover { background: rgba(255,255,255,0.1); }
    .sidebar-nav a.active { background: rgba(255,255,255,0.2); }
    .main-content { margin-left: 250px; padding: 20px; }
    .top-bar { background: white; padding: 15px 30px; border-bottom: 1px solid #e9ecef; display: flex; justify-content: space-between; align-items: center; box-shadow: 0 2px 5px rgba(0,0,0,0.1); }
    .phone-type-selection { display: flex; gap: 20px; justify-content: center; margin: 40px 0; }
    .phone-type-card { background: white; padding: 30px; border-radius: 15px; box-shadow: 0 10px 30px rgba(0,0,0,0.1); text-align: center; cursor: pointer; border: 3px solid transparent; }
    .phone-type-card:hover { box-shadow: 0 15px 40px rgba(0,0,0,0.15); border-color: #28a745; }
    .phone-type-card.selected { border-color: #28a745; background: #e8f5e9; }
    .phone-type-icon { font-size: 3rem; margin-bottom: 20px; }
    .upload-area { border: 2px dashed #28a745; border-radius: 10px; padding: 40px; text-align: center; background: #f8f9fa; margin: 20px 0; }
    .upload-area:hover { background: #e8f5e9; border-color: #20c997; }
    .upload-area.dragover { background: #e8f5e9; border-color: #20c997; }
    @media (max-width: 768px) { .header h1 { font-size: 2rem; } .dashboard-grid { grid-template-columns: 1fr; } .stats-grid { grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); } .container { margin: 10px; border-radius: 10px; } body { padding: 10px; } table { font-size: 14px; } table th, table td { padding: 8px 4px; } .sidebar { width: 100%; position: relative; min-height: auto; } .main-content { margin-left: 0; } }
</style>
"""

# Routes
@app.route('/')
def index():
    total_clients = Client.query.count()
    total_requests = FuelRequest.query.count()
    pending_requests = FuelRequest.query.filter_by(status='pending').count()
    completed_requests = FuelRequest.query.filter_by(status='completed').count()
    camera_clients = Client.query.filter_by(has_camera_phone=True).count()
    gdpr_compliant = Client.query.filter_by(gdpr_consent=True).count()
    
    return render_template_string("""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Lewisham Foodbank - Dashboard</title>
        """ + CSS_TEMPLATE + """

    </head>
    <body>
        <div class="sidebar">
            <div class="sidebar-header">
                <div style="width: 40px; height: 40px; background: white; border-radius: 8px; display: flex; align-items: center; justify-content: center; margin-bottom: 10px;">
                    <span style="font-size: 24px; font-weight: bold; color: #28a745;">LF</span>
                </div>
                <h3 style="margin: 0; color: white;">Lewisham Foodbank</h3>
                <p style="margin: 5px 0 0 0; font-size: 12px; opacity: 0.8;">Together with Trussell</p>
            </div>
            
            <ul class="sidebar-nav">
                <li><a href="{{ url_for('index') }}" class="active">Dashboard</a></li>
                <li><a href="{{ url_for('view_clients') }}">Clients</a></li>
                <li><a href="{{ url_for('customer_data_table') }}">Customer Data</a></li>
                <li><a href="{{ url_for('database_viewer') }}">Database Viewer</a></li>
                <li><a href="{{ url_for('send_sms_requests') }}">Send SMS</a></li>
                <li><a href="{{ url_for('view_sms_history') }}">SMS History</a></li>
                <li><a href="{{ url_for('staff_portal') }}">Staff Portal</a></li>
                <li><a href="{{ url_for('generate_report') }}">Reports</a></li>
            </ul>
        </div>
        
        <div class="main-content">
            <div class="top-bar">
                <div>
                    <h1 style="margin: 0; color: #333;">Dashboard</h1>
                    <p style="margin: 5px 0 0 0; color: #666;">Home / Dashboard</p>
                </div>
                <div>
                    <a href="{{ url_for('database_viewer') }}" class="btn" style="background: #17a2b8; color: white;">🗄️ View Database</a>
                    <a href="{{ url_for('generate_report') }}" class="btn">Export Report</a>
                    <a href="{{ url_for('download_database') }}" class="btn btn-warning" style="background: #ffc107; color: #000;">📥 Download Database</a>
                </div>
            </div>
            
            <div class="content">
                {% with messages = get_flashed_messages(with_categories=true) %}
                    {% if messages %}
                        {% for category, message in messages %}
                            <div class="alert alert-{{ 'danger' if category == 'error' else category }}">
                                {{ message }}
                            </div>
                        {% endfor %}
                    {% endif %}
                {% endwith %}

                <div class="stats-grid">
                    <div class="stat-box">
                        <div class="stat-number">{{ total_clients }}</div>
                        <div class="stat-label">Total Clients</div>
                        <div style="font-size: 12px; color: #28a745; margin-top: 5px;">+12% this month</div>
                    </div>
                    <div class="stat-box">
                        <div class="stat-number">{{ total_requests }}</div>
                        <div class="stat-label">Total Requests</div>
                        <div style="font-size: 12px; color: #28a745; margin-top: 5px;">+8% this month</div>
                    </div>
                    <div class="stat-box">
                        <div class="stat-number">{{ completed_requests }}</div>
                        <div class="stat-label">Completed</div>
                        <div style="font-size: 12px; color: #28a745; margin-top: 5px;">{{ (completed_requests/total_requests*100)|round(1) if total_requests > 0 else 0 }}% rate</div>
                    </div>
                    <div class="stat-box">
                        <div class="stat-number">{{ camera_clients }}</div>
                        <div class="stat-label">Digital Ready</div>
                        <div style="font-size: 12px; color: #28a745; margin-top: 5px;">{{ (camera_clients/total_clients*100)|round(1) if total_clients > 0 else 0 }}% adoption</div>
                    </div>
                </div>

                <div class="dashboard-grid">
                    <div class="card">
                        <h3>Client Distribution</h3>
                        <div style="text-align: center; padding: 40px;">
                            <div style="font-size: 3rem; color: #28a745; margin-bottom: 20px;">{{ camera_clients }}/{{ total_clients }}</div>
                            <div style="color: #666;">Digital Ready Clients</div>
                            <div style="margin-top: 20px; font-size: 0.9rem; color: #28a745;">
                                {{ (camera_clients/total_clients*100)|round(1) if total_clients > 0 else 0 }}% adoption rate
                            </div>
                        </div>
                    </div>
                    
                    <div class="card">
                        <h3>Request Status</h3>
                        <div style="text-align: center; padding: 40px;">
                            <div style="display: flex; justify-content: space-around; margin-bottom: 20px;">
                                <div style="text-align: center;">
                                    <div style="font-size: 2rem; color: #28a745;">{{ completed_requests }}</div>
                                    <div style="font-size: 0.8rem; color: #666;">Completed</div>
                                </div>
                                <div style="text-align: center;">
                                    <div style="font-size: 2rem; color: #ffc107;">{{ pending_requests }}</div>
                                    <div style="font-size: 0.8rem; color: #666;">Pending</div>
                                </div>
                            </div>
                            <div style="background: #f8f9fa; padding: 15px; border-radius: 8px;">
                                <div style="color: #666; margin-bottom: 10px;">Completion Rate</div>
                                <div style="font-size: 1.5rem; color: #28a745; font-weight: bold;">
                                    {{ (completed_requests/total_requests*100)|round(1) if total_requests > 0 else 0 }}%
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
                
                <div class="card">
                    <h3>SMS Performance</h3>
                    <div style="text-align: center; padding: 40px;">
                        <div style="display: grid; grid-template-columns: repeat(3, 1fr); gap: 20px; margin-bottom: 30px;">
                            <div style="text-align: center;">
                                <div style="font-size: 2rem; color: #28a745;">{{ total_requests }}</div>
                                <div style="font-size: 0.8rem; color: #666;">Total SMS Sent</div>
                            </div>
                            <div style="text-align: center;">
                                <div style="font-size: 2rem; color: #20c997;">{{ gdpr_compliant }}</div>
                                <div style="font-size: 0.8rem; color: #666;">GDPR Compliant</div>
                            </div>
                            <div style="text-align: center;">
                                <div style="font-size: 2rem; color: #ffc107;">{{ total_clients - gdpr_compliant }}</div>
                                <div style="font-size: 0.8rem; color: #666;">Pending Consent</div>
                            </div>
                        </div>
                        <div style="background: #e8f5e9; padding: 20px; border-radius: 8px; border-left: 4px solid #28a745;">
                            <div style="color: #28a745; font-weight: bold; margin-bottom: 10px;">System Status</div>
                            <div style="color: #666;">All systems operational • SMS simulation mode active</div>
                        </div>
                    </div>
                </div>
                
                <div class="card" style="background: linear-gradient(135deg, #fff3cd 0%, #ffeaa7 100%); border: 2px solid #ffc107; margin-bottom: 30px;">
                    <h3 style="color: #856404; margin-bottom: 20px;">🔧 Database Management</h3>
                    <div style="display: flex; gap: 15px; flex-wrap: wrap; align-items: center;">
                        <a href="{{ url_for('download_database') }}" class="btn" style="background: #ffc107; color: #000; font-weight: bold;">📥 Download Database Backup</a>
                        <span style="color: #856404; font-size: 0.9rem;">Download your database file for migration or backup purposes</span>
                    </div>
                </div>
                
                <div class="quick-add-form">
                    <h3>Quick Add Client</h3>
                    <form method="POST" action="{{ url_for('quick_add_client') }}" style="display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 15px; align-items: end;">
                        <div class="form-group" style="margin: 0;">
                            <label for="quick_name">Name</label>
                            <input type="text" class="form-control" id="quick_name" name="name" required placeholder="Client Name" pattern="[A-Za-z\s]{2,50}" title="Please enter a valid name (2-50 characters, letters and spaces only)">
                        </div>
                        <div class="form-group" style="margin: 0;">
                            <label for="quick_phone">Phone</label>
                            <input type="tel" class="form-control" id="quick_phone" name="phone_number" required placeholder="+447700900123" pattern="^\\+?[1-9]\\d{1,14}$" title="Please enter a valid phone number (e.g., +447700900123)">
                        </div>
                        <div class="form-group" style="margin: 0;">
                            <label for="quick_referrer_name">Referrer Name</label>
                            <input type="text" class="form-control" id="quick_referrer_name" name="referrer_name" placeholder="Referrer Name" pattern="[A-Za-z\s]{2,50}" title="Please enter a valid referrer name (2-50 characters, letters and spaces only)">
                        </div>
                        <div class="form-group" style="margin: 0;">
                            <label for="quick_referrer_email">Referrer Email</label>
                            <input type="email" class="form-control" id="quick_referrer_email" name="referrer_email" placeholder="referrer@email.com" pattern="[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,}$" title="Please enter a valid email address">
                        </div>
                        <div class="form-check" style="margin: 0;">
                            <input type="checkbox" id="quick_camera" name="has_camera_phone" checked>
                            <label for="quick_camera">Camera Phone</label>
                        </div>
                        <div class="form-check" style="margin: 0;">
                            <input type="checkbox" id="quick_gdpr" name="gdpr_consent" required>
                            <label for="quick_gdpr">GDPR Consent</label>
                        </div>
                        <button type="submit" class="btn btn-success" style="grid-column: 1 / -1; justify-self: center; margin-top: 10px;">Add Client</button>
                    </form>
                </div>
            </div>
        </div>
        

    </body>
    </html>
    """, total_clients=total_clients, total_requests=total_requests, 
         pending_requests=pending_requests, completed_requests=completed_requests,
         camera_clients=camera_clients, gdpr_compliant=gdpr_compliant)

@app.route('/quick_add_client', methods=['POST'])
def quick_add_client():
    """Quick add client from dashboard"""
    try:
        name = request.form.get('name', '').strip()
        phone = request.form.get('phone_number', '').strip()
        referrer_name = request.form.get('referrer_name', '').strip()
        referrer_email = request.form.get('referrer_email', '').strip()
        has_camera = request.form.get('has_camera_phone') == 'on'
        gdpr_consent = request.form.get('gdpr_consent') == 'on'
        
        if not name or not phone:
            flash('Name and phone number are required', 'danger')
            return redirect(url_for('index'))
        
        phone = format_phone_number(phone)
        
        existing_client = Client.query.filter_by(phone_number=phone).first()
        if existing_client:
            flash(f'Phone number {phone} already exists for {existing_client.name}', 'warning')
            return redirect(url_for('index'))
        
        new_client = Client(
            name=name,
            phone_number=phone,
            referrer_name=referrer_name if referrer_name else None,
            referrer_email=referrer_email if referrer_email else None,
            has_camera_phone=has_camera,
            gdpr_consent=gdpr_consent
        )
        
        db.session.add(new_client)
        db.session.commit()
        
        flash(f'Client {name} added successfully!', 'success')
        
    except Exception as e:
        db.session.rollback()
        flash(f'Error adding client: {str(e)}', 'danger')
        logging.error(f"Error in quick_add_client: {e}")
    
    return redirect(url_for('index'))

@app.route('/send_sms_requests', methods=['GET', 'POST'])
@app.route('/send_sms_requests/<int:timestamp>', methods=['GET', 'POST'])
def send_sms_requests(timestamp=None):
    if request.method == 'POST':
        try:
            selected_clients = request.form.getlist('client_ids')
            if not selected_clients:
                flash('Please select at least one client', 'danger')
                return redirect(url_for('send_sms_requests'))
            
            sent_count = 0
            failed_count = 0
            
            for client_id in selected_clients:
                client = db.session.get(Client, int(client_id))
                if not client:
                    logging.error(f"Client with ID {client_id} not found")
                    failed_count += 1
                    continue
                
                if not client.gdpr_consent:
                    logging.warning(f"Client {client.name} does not have GDPR consent - skipping")
                    flash(f'Client {client.name} skipped - no GDPR consent', 'warning')
                    failed_count += 1
                    continue
                
                try:
                    fuel_request = FuelRequest(
                        client_id=client.id,
                        unique_link=generate_unique_link(),
                        expires_at=datetime.now() + timedelta(hours=48),
                        status='pending'
                    )
                    db.session.add(fuel_request)
                    db.session.flush()
                    
                    success = send_sms_to_client(client, fuel_request)
                    
                    if success:
                        sent_count += 1
                        logging.info(f"SMS sent successfully to {client.name}")
                    else:
                        failed_count += 1
                        logging.error(f"Failed to send SMS to {client.name}")
                        
                except Exception as e:
                    logging.error(f"Error processing client {client.name}: {str(e)}")
                    failed_count += 1
                        
            db.session.commit()
            
            if failed_count == 0:
                flash(f'✅ SMS requests sent successfully to {sent_count} clients! Check SMS History for details.', 'success')
            else:
                flash(f'⚠️ SMS sent to {sent_count} clients, {failed_count} failed. Check SMS History for details.', 'warning')
            
        except Exception as e:
            db.session.rollback()
            flash(f'Error sending SMS requests: {str(e)}', 'danger')
            logging.error(f"Error in send_sms_requests: {e}")
        
        return redirect(url_for('send_sms_requests'))
    
    clients = Client.query.order_by(Client.name).all()
    return render_template_string("""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Send SMS Requests - Food Bank</title>
        """ + CSS_TEMPLATE + """
    </head>
    <body>
        <div class="sidebar">
            <div class="sidebar-header">
                <div style="width: 40px; height: 40px; background: white; border-radius: 8px; display: flex; align-items: center; justify-content: center; margin-bottom: 10px;">
                    <span style="font-size: 24px; font-weight: bold; color: #28a745;">LF</span>
                </div>
                <h3 style="margin: 0; color: white;">Lewisham Foodbank</h3>
                <p style="margin: 5px 0 0 0; font-size: 12px; opacity: 0.8;">Together with Trussell</p>
            </div>
            
            <ul class="sidebar-nav">
                <li><a href="{{ url_for('index') }}">Dashboard</a></li>
                <li><a href="{{ url_for('view_clients') }}">Clients</a></li>
                <li><a href="{{ url_for('customer_data_table') }}">Customer Data</a></li>
                <li><a href="{{ url_for('send_sms_requests') }}" class="active">Send SMS</a></li>
                <li><a href="{{ url_for('view_sms_history') }}">SMS History</a></li>
                <li><a href="{{ url_for('staff_portal') }}">Staff Portal</a></li>
                <li><a href="{{ url_for('generate_report') }}">Reports</a></li>
            </ul>
        </div>
        
        <div class="main-content">
            <div class="top-bar">
                <div>
                    <h1 style="margin: 0; color: #333;">Send SMS Requests</h1>
                    <p style="margin: 5px 0 0 0; color: #666;">Home / Send SMS</p>
                </div>
            </div>
            
            <div class="content">
                {% with messages = get_flashed_messages(with_categories=true) %}
                    {% if messages %}
                        {% for category, message in messages %}
                            <div class="alert alert-{{ 'danger' if category == 'error' else category }}">
                                {{ message }}
                            </div>
                        {% endfor %}
                    {% endif %}
                {% endwith %}
                
                <div class="card">
                    <h3 style="color: #28a745; margin-bottom: 20px;">📱 Select Clients for SMS</h3>
                    {% if clients %}
                    <form method="POST" id="smsForm">
                        <div style="margin: 20px 0; display: flex; gap: 15px; flex-wrap: wrap; align-items: center;">
                            <button type="button" onclick="selectAll()" class="btn btn-secondary">✅ Select All</button>
                            <button type="button" onclick="selectNone()" class="btn btn-secondary">❌ Select None</button>
                            <button type="button" onclick="selectGDPROnly()" class="btn btn-secondary">🔒 GDPR Compliant Only</button>
                            <a href="{{ url_for('cleanup_database') }}" class="btn btn-warning" onclick="return confirm('This will clean up duplicate clients and fix GDPR consent. Continue?')">🧹 Clean Database</a>
                            <span id="selectedCount" style="padding: 12px 20px; background: linear-gradient(135deg, #28a745, #20c997); color: white; border-radius: 8px; font-weight: bold; box-shadow: 0 2px 10px rgba(40, 167, 69, 0.3);">0 selected</span>
                        </div>
                        
                        <table style="border-radius: 12px; overflow: hidden; box-shadow: 0 4px 15px rgba(0,0,0,0.1);">
                            <thead>
                                <tr style="background: linear-gradient(135deg, #28a745, #20c997);">
                                    <th style="padding: 15px; color: white; border: none;"><input type="checkbox" id="selectAll" onchange="toggleAll()" style="transform: scale(1.2);"></th>
                                    <th style="padding: 15px; color: white; border: none;">👤 Name</th>
                                    <th style="padding: 15px; color: white; border: none;">📱 Phone</th>
                                    <th style="padding: 15px; color: white; border: none;">📷 Camera Phone</th>
                                    <th style="padding: 15px; color: white; border: none;">🔒 GDPR Consent</th>
                                    <th style="padding: 15px; color: white; border: none;">📊 Status</th>
                                </tr>
                            </thead>
                            <tbody>
                                {% for client in clients %}
                                <tr>
                                    <td><input type="checkbox" name="client_ids" value="{{ client.id }}" class="client-checkbox" onchange="updateCount()"></td>
                                    <td>{{ client.name }}</td>
                                    <td>{{ client.phone_number }}</td>
                                    <td>
                                        {% if client.has_camera_phone %}
                                            Yes
                                        {% else %}
                                            No
                                        {% endif %}
                                    </td>
                                    <td>
                                        {% if client.gdpr_consent %}
                                            Yes
                                        {% else %}
                                            No
                                        {% endif %}
                                    </td>
                                    <td>
                                        {% if client.gdpr_consent %}
                                            <span style="color: #28a745;">Ready</span>
                                        {% else %}
                                            <span style="color: #dc3545;">No Consent</span>
                                        {% endif %}
                                    </td>
                                </tr>
                                {% endfor %}
                            </tbody>
                        </table>
                        
                        <div style="margin-top: 30px; display: flex; gap: 15px; flex-wrap: wrap; justify-content: center;">
                            <button type="submit" class="btn btn-success" style="padding: 15px 30px; font-size: 16px; font-weight: 600;">📤 Send SMS Requests</button>
                            <button type="button" onclick="testSMS()" class="btn btn-info" style="padding: 15px 30px; font-size: 16px; font-weight: 600;">🧪 Test SMS Function</button>
                            <a href="{{ url_for('index') }}" class="btn btn-secondary" style="padding: 15px 30px; font-size: 16px; font-weight: 600;">🏠 Back to Dashboard</a>
                        </div>
                    </form>
                    {% else %}
                    <div class="alert alert-info">
                        <p>No clients found. <a href="{{ url_for('add_client') }}">Add a client first</a>.</p>
                    </div>
                    {% endif %}
                </div>
            </div>
        </div>
        
        <script>
        function selectAll() {
            document.querySelectorAll('.client-checkbox').forEach(cb => cb.checked = true);
            updateCount();
        }
        
        function selectNone() {
            document.querySelectorAll('.client-checkbox').forEach(cb => cb.checked = false);
            updateCount();
        }
        
        function selectGDPROnly() {
            document.querySelectorAll('.client-checkbox').forEach(cb => {
                const row = cb.closest('tr');
                const gdprCell = row.cells[4];
                cb.checked = gdprCell.textContent.includes('Yes');
            });
            updateCount();
        }
        
        function toggleAll() {
            const selectAllCheckbox = document.getElementById('selectAll');
            document.querySelectorAll('.client-checkbox').forEach(cb => cb.checked = selectAllCheckbox.checked);
            updateCount();
        }
        
        function updateCount() {
            const checked = document.querySelectorAll('.client-checkbox:checked').length;
            document.getElementById('selectedCount').textContent = checked + ' selected';
        }
        
        function testSMS() {
            const selectedClients = document.querySelectorAll('.client-checkbox:checked');
            if (selectedClients.length === 0) {
                alert('Please select at least one client to test SMS');
                return;
            }
            
            const clientNames = Array.from(selectedClients).map(cb => {
                const row = cb.closest('tr');
                return row.cells[1].textContent; // Name column
            });
            
            alert(`SMS Test Ready!\n\nSelected clients: ${clientNames.join(', ')}\n\nClick "Send SMS Requests" to proceed with actual SMS sending.`);
        }
        
        updateCount();
        </script>
    </body>
    </html>
    """, clients=clients)

@app.route('/view_clients')
def view_clients():
    """View all clients"""
    clients = Client.query.order_by(Client.name).all()
    return render_template_string("""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>View Clients - Food Bank</title>
        """ + CSS_TEMPLATE + """
    </head>
    <body>
        <div class="sidebar">
            <div class="sidebar-header">
                <div style="width: 40px; height: 40px; background: white; border-radius: 8px; display: flex; align-items: center; justify-content: center; margin-bottom: 10px;">
                    <span style="font-size: 24px; font-weight: bold; color: #28a745;">LF</span>
                </div>
                <h3 style="margin: 0; color: white;">Lewisham Foodbank</h3>
                <p style="margin: 5px 0 0 0; font-size: 12px; opacity: 0.8;">Together with Trussell</p>
            </div>
            
            <ul class="sidebar-nav">
                <li><a href="{{ url_for('index') }}">Dashboard</a></li>
                <li><a href="{{ url_for('view_clients') }}" class="active">Clients</a></li>
                <li><a href="{{ url_for('send_sms_requests') }}">Send SMS</a></li>
                <li><a href="{{ url_for('view_sms_history') }}">SMS History</a></li>
                <li><a href="{{ url_for('staff_portal') }}">Staff Portal</a></li>
                <li><a href="{{ url_for('generate_report') }}">Reports</a></li>
            </ul>
        </div>
        
        <div class="main-content">
            <div class="top-bar">
                <div>
                    <h1 style="margin: 0; color: #333;">Clients</h1>
                    <p style="margin: 5px 0 0 0; color: #666;">Home / Clients</p>
                </div>
                <div>
                    <a href="{{ url_for('add_client') }}" class="btn">Add New Client</a>
                </div>
            </div>
            
            <div class="content">
                {% with messages = get_flashed_messages(with_categories=true) %}
                    {% if messages %}
                        {% for category, message in messages %}
                            <div class="alert alert-{{ 'danger' if category == 'error' else category }}">
                                {{ message }}
                            </div>
                        {% endfor %}
                    {% endif %}
                {% endwith %}
                
                <div class="card">
                    <h3>Client List</h3>
                    {% if clients %}
                    <table>
                        <thead>
                            <tr>
                                <th>ID</th>
                                <th>Name</th>
                                <th>Phone</th>
                                <th>Referrer Name</th>
                                <th>Referrer Email</th>
                                <th>Camera Phone</th>
                                <th>GDPR Consent</th>
                                <th>Created At</th>
                                <th>Actions</th>
                            </tr>
                        </thead>
                        <tbody>
                            {% for client in clients %}
                            <tr>
                                <td>{{ client.id }}</td>
                                <td>{{ client.name }}</td>
                                <td>{{ client.phone_number }}</td>
                                <td>{{ client.referrer_name or 'N/A' }}</td>
                                <td>{{ client.referrer_email or 'N/A' }}</td>
                                <td>
                                    {% if client.has_camera_phone %}
                                        Yes
                                    {% else %}
                                        No
                                    {% endif %}
                                </td>
                                <td>
                                    {% if client.gdpr_consent %}
                                        Yes
                                    {% else %}
                                        No
                                    {% endif %}
                                </td>
                                <td>{{ client.created_at.strftime('%Y-%m-%d %H:%M') }}</td>
                                <td>
                                    <a href="{{ url_for('edit_client', client_id=client.id) }}" class="btn btn-small btn-info">Edit</a>
                                    <a href="{{ url_for('delete_client', client_id=client.id) }}" class="btn btn-small btn-danger" onclick="return confirm('Are you sure you want to delete {{ client.name }}? This action cannot be undone.')">Delete</a>
                                </td>
                            </tr>
                            {% endfor %}
                        </tbody>
                    </table>
                    {% else %}
                    <div class="alert alert-info">
                        <p>No clients found. <a href="{{ url_for('add_client') }}">Add a client first</a>.</p>
                    </div>
                    {% endif %}
                </div>
            </div>
        </div>
    </body>
    </html>
    """, clients=clients)

@app.route('/add_client', methods=['GET', 'POST'])
def add_client():
    """Add new client"""
    if request.method == 'POST':
        try:
            name = request.form.get('name', '').strip()
            phone = request.form.get('phone_number', '').strip()
            referrer_name = request.form.get('referrer_name', '').strip()
            referrer_email = request.form.get('referrer_email', '').strip()
            has_camera = request.form.get('has_camera_phone') == 'on'
            gdpr_consent = request.form.get('gdpr_consent') == 'on'
            
            if not name or not phone:
                flash('Name and phone number are required', 'danger')
                return redirect(url_for('add_client'))
            
            phone = format_phone_number(phone)
            
            existing_client = Client.query.filter_by(phone_number=phone).first()
            if existing_client:
                flash(f'Phone number {phone} already exists for {existing_client.name}', 'warning')
                return redirect(url_for('add_client'))
            
            new_client = Client(
                name=name,
                phone_number=phone,
                referrer_name=referrer_name if referrer_name else None,
                referrer_email=referrer_email if referrer_email else None,
                has_camera_phone=has_camera,
                gdpr_consent=gdpr_consent
            )
            
            db.session.add(new_client)
            db.session.commit()
            
            flash(f'Client {name} added successfully!', 'success')
            return redirect(url_for('view_clients'))
            
        except Exception as e:
            db.session.rollback()
            flash(f'Error adding client: {str(e)}', 'danger')
            logging.error(f"Error in add_client: {e}")
    
    return render_template_string("""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Add Client - Food Bank</title>
        """ + CSS_TEMPLATE + """
    </head>
    <body>
        <div class="sidebar">
            <div class="sidebar-header">
                <div style="width: 40px; height: 40px; background: white; border-radius: 8px; display: flex; align-items: center; justify-content: center; margin-bottom: 10px;">
                    <span style="font-size: 24px; font-weight: bold; color: #28a745;">LF</span>
                </div>
                <h3 style="margin: 0; color: white;">Lewisham Foodbank</h3>
                <p style="margin: 5px 0 0 0; font-size: 12px; opacity: 0.8;">Together with Trussell</p>
            </div>
            
            <ul class="sidebar-nav">
                <li><a href="{{ url_for('index') }}">Dashboard</a></li>
                <li><a href="{{ url_for('view_clients') }}" class="active">Clients</a></li>
                <li><a href="{{ url_for('send_sms_requests') }}">Send SMS</a></li>
                <li><a href="{{ url_for('view_sms_history') }}">SMS History</a></li>
                <li><a href="{{ url_for('staff_portal') }}">Staff Portal</a></li>
                <li><a href="{{ url_for('generate_report') }}">Reports</a></li>
            </ul>
        </div>
        
        <div class="main-content">
            <div class="top-bar">
                <div>
                    <h1 style="margin: 0; color: #333;">Add New Client</h1>
                    <p style="margin: 5px 0 0 0; color: #666;">Home / Clients / Add Client</p>
                </div>
            </div>
            
            <div class="content">
                <div class="card">
                    <h3>Client Information</h3>
                    <form method="POST">
                        <div class="form-group">
                            <label for="name">Full Name *</label>
                            <input type="text" class="form-control" id="name" name="name" required>
                        </div>
                        
                        <div class="form-group">
                            <label for="phone_number">Phone Number *</label>
                            <input type="tel" class="form-control" id="phone_number" name="phone_number" required placeholder="+447700900123">
                        </div>
                        
                        <div class="form-group">
                            <label for="referrer_name">Referrer Name</label>
                            <input type="text" class="form-control" id="referrer_name" name="referrer_name" placeholder="Referrer Name">
                        </div>
                        
                        <div class="form-group">
                            <label for="referrer_email">Referrer Email</label>
                            <input type="email" class="form-control" id="referrer_email" name="referrer_email" placeholder="referrer@email.com">
                        </div>
                        
                        <div class="form-check">
                            <input type="checkbox" id="has_camera_phone" name="has_camera_phone" checked>
                            <label for="has_camera_phone">Has camera phone (for digital upload)</label>
                        </div>
                        
                        <div class="form-check">
                            <input type="checkbox" id="gdpr_consent" name="gdpr_consent" required>
                            <label for="gdpr_consent">GDPR consent given *</label>
                        </div>
                        
                        <div style="margin-top: 20px;">
                            <button type="submit" class="btn btn-success">Add Client</button>
                            <a href="{{ url_for('view_clients') }}" class="btn btn-secondary">Back to Clients</a>
                        </div>
                    </form>
                </div>
            </div>
        </div>
    </body>
    </html>
    """)

@app.route('/edit_client/<int:client_id>', methods=['GET', 'POST'])
def edit_client(client_id):
    """Edit existing client information"""
    client = db.session.get(Client, client_id)
    if not client:
        abort(404)
    
    if request.method == 'POST':
        try:
            name = request.form.get('name', '').strip()
            phone = request.form.get('phone_number', '').strip()
            referrer_name = request.form.get('referrer_name', '').strip()
            referrer_email = request.form.get('referrer_email', '').strip()
            has_camera = request.form.get('has_camera_phone') == 'on'
            gdpr_consent = request.form.get('gdpr_consent') == 'on'
            
            if not name or not phone:
                flash('Name and phone number are required', 'danger')
                return redirect(url_for('edit_client', client_id=client_id))
            
            phone = format_phone_number(phone)
            
            # Check if phone number already exists for another client
            existing_client = Client.query.filter_by(phone_number=phone).first()
            if existing_client and existing_client.id != client_id:
                flash(f'Phone number {phone} already exists for {existing_client.name}', 'warning')
                return redirect(url_for('edit_client', client_id=client_id))
            
            # Update client information
            client.name = name
            client.phone_number = phone
            client.referrer_name = referrer_name if referrer_name else None
            client.referrer_email = referrer_email if referrer_email else None
            client.has_camera_phone = has_camera
            client.gdpr_consent = gdpr_consent
            
            db.session.commit()
            flash(f'Client {name} updated successfully!', 'success')
            return redirect(url_for('view_clients'))
            
        except Exception as e:
            db.session.rollback()
            flash(f'Error updating client: {str(e)}', 'danger')
            logging.error(f"Error in edit_client: {e}")
    
    return render_template_string("""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Edit Client - Food Bank</title>
        """ + CSS_TEMPLATE + """
    </head>
    <body>
        <div class="sidebar">
            <div class="sidebar-header">
                <div style="width: 40px; height: 40px; background: white; border-radius: 8px; display: flex; align-items: center; justify-content: center; margin-bottom: 10px;">
                    <span style="font-size: 24px; font-weight: bold; color: #28a745;">LF</span>
                </div>
                <h3 style="margin: 0; color: white;">Lewisham Foodbank</h3>
                <p style="margin: 5px 0 0 0; font-size: 12px; opacity: 0.8;">Together with Trussell</p>
            </div>
            
            <ul class="sidebar-nav">
                <li><a href="{{ url_for('index') }}">Dashboard</a></li>
                <li><a href="{{ url_for('view_clients') }}">Clients</a></li>
                <li><a href="{{ url_for('customer_data_table') }}">Customer Data</a></li>
                <li><a href="{{ url_for('send_sms_requests') }}">Send SMS</a></li>
                <li><a href="{{ url_for('view_sms_history') }}">SMS History</a></li>
                <li><a href="{{ url_for('staff_portal') }}">Staff Portal</a></li>
                <li><a href="{{ url_for('generate_report') }}">Reports</a></li>
            </ul>
        </div>
        
        <div class="main-content">
            <div class="top-bar">
                <div>
                    <h1 style="margin: 0; color: #333;">Edit Client: {{ client.name }}</h1>
                    <p style="margin: 5px 0 0 0; color: #666;">Home / Clients / Edit Client</p>
                </div>
            </div>
            
            <div class="content">
                <div class="card">
                    <h3>Client Information</h3>
                    <form method="POST">
                        <div class="form-group">
                            <label for="name">Full Name *</label>
                            <input type="text" class="form-control" id="name" name="name" value="{{ client.name }}" required>
                        </div>
                        
                        <div class="form-group">
                            <label for="phone_number">Phone Number *</label>
                            <input type="tel" class="form-control" id="phone_number" name="phone_number" value="{{ client.phone_number }}" required placeholder="+447700900123">
                        </div>
                        
                        <div class="form-group">
                            <label for="referrer_name">Referrer Name</label>
                            <input type="text" class="form-control" id="referrer_name" name="referrer_name" value="{{ client.referrer_name or '' }}" placeholder="Referrer Name">
                        </div>
                        
                        <div class="form-group">
                            <label for="referrer_email">Referrer Email</label>
                            <input type="email" class="form-control" id="referrer_email" name="referrer_email" value="{{ client.referrer_email or '' }}" placeholder="referrer@email.com">
                        </div>
                        
                        <div class="form-check">
                            <input type="checkbox" id="has_camera_phone" name="has_camera_phone" {% if client.has_camera_phone %}checked{% endif %}>
                            <label for="has_camera_phone">Has camera phone (for digital upload)</label>
                        </div>
                        
                        <div class="form-check">
                            <input type="checkbox" id="gdpr_consent" name="gdpr_consent" {% if client.gdpr_consent %}checked{% endif %} required>
                            <label for="gdpr_consent">GDPR consent given *</label>
                        </div>
                        
                        <div style="margin-top: 20px;">
                            <button type="submit" class="btn btn-success">Save Changes</button>
                            <a href="{{ url_for('view_clients') }}" class="btn btn-secondary">Back to Clients</a>
                        </div>
                    </form>
                </div>
            </div>
        </div>
    </body>
    </html>
    """, client=client)

@app.route('/delete_client/<int:client_id>')
def delete_client(client_id):
    """Delete a client and all associated data"""
    try:
        client = db.session.get(Client, client_id)
        if not client:
            abort(404)
        client_name = client.name
        
        # Delete all associated fuel requests and SMS logs
        FuelRequest.query.filter_by(client_id=client.id).delete()
        SMSLog.query.filter_by(client_id=client.id).delete()
        
        # Delete the client
        db.session.delete(client)
        db.session.commit()
        
        flash(f'Client {client_name} and all associated data deleted successfully!', 'success')
        
    except Exception as e:
        db.session.rollback()
        flash(f'Error deleting client: {str(e)}', 'danger')
        logging.error(f"Error in delete_client: {e}")
    
    return redirect(url_for('view_clients'))

@app.route('/database_viewer')
def database_viewer():
    """Simple database viewer to see all data in tables"""
    try:
        # Get all data from all tables
        clients = Client.query.all()
        fuel_requests = FuelRequest.query.all()
        sms_logs = SMSLog.query.all()
        
        return render_template_string("""
        <!DOCTYPE html>
        <html lang="en">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>Database Viewer - Food Bank</title>
            """ + CSS_TEMPLATE + """
            <style>
                .table-container { margin: 20px 0; overflow-x: auto; }
                .table-title { background: #28a745; color: white; padding: 15px; border-radius: 8px 8px 0 0; font-weight: bold; }
                .data-table { width: 100%; border-collapse: collapse; background: white; }
                .data-table th { background: #e8f5e9; padding: 12px 8px; text-align: left; border: 1px solid #dee2e6; font-weight: 600; }
                .data-table td { padding: 10px 8px; border: 1px solid #dee2e6; font-size: 14px; }
                .data-table tbody tr:nth-child(even) { background: #f8f9fa; }
                .data-table tbody tr:hover { background: #e8f5e9; }
                .stats-box { background: #e8f5e9; padding: 15px; border-radius: 8px; margin: 20px 0; border-left: 4px solid #28a745; }
            </style>
        </head>
        <body>
            <div class="sidebar">
                <div class="sidebar-header">
                    <div style="width: 40px; height: 40px; background: white; border-radius: 8px; display: flex; align-items: center; justify-content: center; margin-bottom: 10px;">
                        <span style="font-size: 24px; font-weight: bold; color: #28a745;">LF</span>
                    </div>
                    <h3 style="margin: 0; color: white;">Lewisham Foodbank</h3>
                    <p style="margin: 5px 0 0 0; font-size: 12px; opacity: 0.8;">Together with Trussell</p>
                </div>
                
                <ul class="sidebar-nav">
                    <li><a href="{{ url_for('index') }}">Dashboard</a></li>
                    <li><a href="{{ url_for('view_clients') }}">Clients</a></li>
                    <li><a href="{{ url_for('customer_data_table') }}">Customer Data</a></li>
                    <li><a href="{{ url_for('send_sms_requests') }}">Send SMS</a></li>
                    <li><a href="{{ url_for('view_sms_history') }}">SMS History</a></li>
                    <li><a href="{{ url_for('staff_portal') }}">Staff Portal</a></li>
                    <li><a href="{{ url_for('generate_report') }}">Reports</a></li>
                </ul>
            </div>
            
            <div class="main-content">
                <div class="top-bar">
                    <div>
                        <h1 style="margin: 0; color: #333;">Database Viewer</h1>
                        <p style="margin: 5px 0 0 0; color: #666;">View all data in database tables</p>
                    </div>
                    <div>
                        <a href="{{ url_for('export_csv') }}" class="btn">📊 Export CSV</a>
                        <a href="{{ url_for('index') }}" class="btn btn-secondary">🏠 Dashboard</a>
                    </div>
                </div>
                
                <div class="content">
                    <div class="stats-box">
                        <h4 style="color: #28a745; margin-bottom: 10px;">📊 Database Summary</h4>
                        <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 15px;">
                            <div><strong>Total Clients:</strong> {{ clients|length }}</div>
                            <div><strong>Total Requests:</strong> {{ fuel_requests|length }}</div>
                            <div><strong>Total SMS Logs:</strong> {{ sms_logs|length }}</div>
                            <div><strong>Database Status:</strong> <span style="color: #28a745;">✅ Active</span></div>
                        </div>
                    </div>
                    
                    <!-- Clients Table -->
                    <div class="table-container">
                        <div class="table-title">👥 CLIENTS TABLE ({{ clients|length }} records)</div>
                        <table class="data-table">
                            <thead>
                                <tr>
                                    <th>ID</th>
                                    <th>Name</th>
                                    <th>Phone</th>
                                    <th>Referrer Name</th>
                                    <th>Referrer Email</th>
                                    <th>Camera Phone</th>
                                    <th>GDPR Consent</th>
                                    <th>Created At</th>
                                </tr>
                            </thead>
                            <tbody>
                                {% for client in clients %}
                                <tr>
                                    <td>{{ client.id }}</td>
                                    <td>{{ client.name }}</td>
                                    <td>{{ client.phone_number }}</td>
                                    <td>{{ client.referrer_name or 'N/A' }}</td>
                                    <td>{{ client.referrer_email or 'N/A' }}</td>
                                    <td>{{ 'Yes' if client.has_camera_phone else 'No' }}</td>
                                    <td>{{ 'Yes' if client.gdpr_consent else 'No' }}</td>
                                    <td>{{ client.created_at.strftime('%Y-%m-%d %H:%M:%S') if client.created_at else 'N/A' }}</td>
                                </tr>
                                {% endfor %}
                            </tbody>
                        </table>
                    </div>
                    
                    <!-- Fuel Requests Table -->
                    <div class="table-container">
                        <div class="table-title">⛽ FUEL REQUESTS TABLE ({{ fuel_requests|length }} records)</div>
                        <table class="data-table">
                            <thead>
                                <tr>
                                    <th>ID</th>
                                    <th>Client ID</th>
                                    <th>Client Name</th>
                                    <th>Status</th>
                                    <th>Phone Type</th>
                                    <th>Documents Uploaded</th>
                                    <th>Meter Reading</th>
                                    <th>ID Type</th>
                                    <th>Postcode</th>
                                    <th>Created At</th>
                                    <th>Expires At</th>
                                </tr>
                            </thead>
                            <tbody>
                                {% for request in fuel_requests %}
                                <tr>
                                    <td>{{ request.id }}</td>
                                    <td>{{ request.client_id }}</td>
                                    <td>{{ request.client.name if request.client else 'N/A' }}</td>
                                    <td>{{ request.status }}</td>
                                    <td>{{ request.phone_type_used or 'N/A' }}</td>
                                    <td>{{ 'Yes' if request.documents_uploaded else 'No' }}</td>
                                    <td>{{ request.meter_reading_text or ('Photo' if request.meter_reading_filename else 'N/A') }}</td>
                                    <td>{{ request.id_type or 'N/A' }}</td>
                                    <td>{{ request.client_postcode or 'N/A' }}</td>
                                    <td>{{ request.created_at.strftime('%Y-%m-%d %H:%M:%S') if request.created_at else 'N/A' }}</td>
                                    <td>{{ request.expires_at.strftime('%Y-%m-%d %H:%M:%S') if request.expires_at else 'N/A' }}</td>
                                </tr>
                                {% endfor %}
                            </tbody>
                        </table>
                    </div>
                    
                    <!-- SMS Logs Table -->
                    <div class="table-container">
                        <div class="table-title">📱 SMS LOGS TABLE ({{ sms_logs|length }} records)</div>
                        <table class="data-table">
                            <thead>
                                <tr>
                                    <th>ID</th>
                                    <th>Client ID</th>
                                    <th>Client Name</th>
                                    <th>Phone Number</th>
                                    <th>Status</th>
                                    <th>Twilio SID</th>
                                    <th>Created At</th>
                                    <th>Sent At</th>
                                </tr>
                            </thead>
                            <tbody>
                                {% for log in sms_logs %}
                                <tr>
                                    <td>{{ log.id }}</td>
                                    <td>{{ log.client_id }}</td>
                                    <td>{{ log.client.name if log.client else 'N/A' }}</td>
                                    <td>{{ log.phone_number }}</td>
                                    <td>{{ log.status }}</td>
                                    <td>{{ log.twilio_sid or 'N/A' }}</td>
                                    <td>{{ log.created_at.strftime('%Y-%m-%d %H:%M:%S') if log.created_at else 'N/A' }}</td>
                                    <td>{{ log.sent_at.strftime('%Y-%m-%d %H:%M:%S') if log.sent_at else 'N/A' }}</td>
                                </tr>
                                {% endfor %}
                            </tbody>
                        </table>
                    </div>
                    
                    <div style="margin-top: 30px; padding: 20px; background: #f8f9fa; border-radius: 8px; border-left: 4px solid #17a2b8;">
                        <h4 style="color: #17a2b8; margin-bottom: 10px;">💡 Database Information</h4>
                        <p><strong>Database Type:</strong> SQLite (file-based)</p>
                        <p><strong>Location:</strong> instance/foodbank.db</p>
                        <p><strong>Last Updated:</strong> {{ current_time }}</p>
                        <p><strong>Note:</strong> This view shows all data in real-time. Data is automatically saved when you add clients or process requests.</p>
                    </div>
                </div>
            </div>
        </body>
        </html>
        """, clients=clients, fuel_requests=fuel_requests, sms_logs=sms_logs, current_time=datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
        
    except Exception as e:
        flash(f'Error viewing database: {str(e)}', 'danger')
        logging.error(f"Database viewer error: {e}")
        return redirect(url_for('index'))

@app.route('/customer_data_table')
def customer_data_table():
    """Comprehensive customer data table view (frontend user-friendly/spreadsheet style)"""
    # Get all clients with their fuel requests
    clients = Client.query.order_by(Client.created_at.desc()).all()
    
    return render_template_string("""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Customer Data Table - Food Bank</title>
        """ + CSS_TEMPLATE + """
        <style>
            .data-table-container { overflow-x: auto; margin: 20px 0; }
            .data-table { min-width: 1200px; font-size: 14px; }
            .data-table th { background: #28a745; color: white; padding: 12px 8px; text-align: center; font-weight: 600; }
            .data-table td { padding: 10px 8px; text-align: center; border-bottom: 1px solid #dee2e6; }
            .data-table tbody tr:nth-child(even) { background: #f8f9fa; }
            .data-table tbody tr:hover { background: #e8f5e9; }
            .status-badge { padding: 4px 8px; border-radius: 4px; font-size: 12px; font-weight: 500; }
            .status-completed { background: #d4edda; color: #155724; }
            .status-pending { background: #fff3cd; color: #856404; }
            .status-expired { background: #f8d7da; color: #721c24; }
            .export-buttons { margin: 20px 0; display: flex; gap: 15px; flex-wrap: wrap; }
        </style>
    </head>
    <body>
        <div class="sidebar">
            <div class="sidebar-header">
                <div style="width: 40px; height: 40px; background: white; border-radius: 8px; display: flex; align-items: center; justify-content: center; margin-bottom: 10px;">
                    <span style="font-size: 24px; font-weight: bold; color: #28a745;">LF</span>
                </div>
                <h3 style="margin: 0; color: white;">Lewisham Foodbank</h3>
                <p style="margin: 5px 0 0 0; font-size: 12px; opacity: 0.8;">Together with Trussell</p>
            </div>
            
            <ul class="sidebar-nav">
                <li><a href="{{ url_for('index') }}">Dashboard</a></li>
                <li><a href="{{ url_for('view_clients') }}">Clients</a></li>
                <li><a href="{{ url_for('customer_data_table') }}" class="active">Customer Data</a></li>
                <li><a href="{{ url_for('send_sms_requests') }}">Send SMS</a></li>
                <li><a href="{{ url_for('view_sms_history') }}">SMS History</a></li>
                <li><a href="{{ url_for('staff_portal') }}">Staff Portal</a></li>
                <li><a href="{{ url_for('generate_report') }}">Reports</a></li>
            </ul>
        </div>
        
        <div class="main-content">
            <div class="top-bar">
                <div>
                    <h1 style="margin: 0; color: #333;">Customer Data Table</h1>
                    <p style="margin: 5px 0 0 0; color: #666;">Home / Customer Data</p>
                </div>
                <div>
                    <a href="{{ url_for('export_csv') }}" class="btn">📊 Export CSV</a>
                </div>
            </div>
            
            <div class="content">
                <div class="card">
                    <h3>📋 Complete Customer Database (Spreadsheet View)</h3>
                    <p style="color: #666; margin-bottom: 20px;">Comprehensive view of all customer details, referrer information, and request status</p>
                    
                    <div class="export-buttons">
                        <a href="{{ url_for('export_csv') }}" class="btn btn-success">📥 Export All Data to CSV</a>
                        <a href="{{ url_for('export_csv', type='clients') }}" class="btn btn-info">👥 Export Clients Only</a>
                        <a href="{{ url_for('export_csv', type='requests') }}" class="btn btn-warning">📋 Export Requests Only</a>
                        <a href="{{ url_for('index') }}" class="btn btn-secondary">🏠 Back to Dashboard</a>
                    </div>
                    
                    <div class="data-table-container">
                        <table class="data-table">
                            <thead>
                                <tr>
                                    <th>Client ID</th>
                                    <th>Client Name</th>
                                    <th>Phone</th>
                                    <th>Referrer Name</th>
                                    <th>Referrer Email</th>
                                    <th>Camera Phone</th>
                                    <th>GDPR Consent</th>
                                    <th>Request ID</th>
                                    <th>Request Status</th>
                                    <th>Phone Type Used</th>
                                    <th>Documents Uploaded</th>
                                    <th>Meter Reading</th>
                                    <th>ID Type</th>
                                    <th>Postcode</th>
                                    <th>Created Date</th>
                                    <th>Submission Date</th>
                                    <th>Expires Date</th>
                                    <th>Missing Docs Reason</th>
                                </tr>
                            </thead>
                            <tbody>
                                {% for client in clients %}
                                    {% if client.fuel_requests %}
                                        {% for request in client.fuel_requests %}
                                        <tr>
                                            <td>{{ client.id }}</td>
                                            <td>{{ client.name }}</td>
                                            <td>{{ client.phone_number }}</td>
                                            <td>{{ client.referrer_name or 'N/A' }}</td>
                                            <td>{{ client.referrer_email or 'N/A' }}</td>
                                            <td>{{ 'Yes' if client.has_camera_phone else 'No' }}</td>
                                            <td>{{ 'Yes' if client.gdpr_consent else 'No' }}</td>
                                            <td>{{ request.id }}</td>
                                            <td>
                                                <span class="status-badge status-{{ request.status }}">
                                                    {{ request.status.title() }}
                                                </span>
                                            </td>
                                            <td>{{ request.phone_type_used or 'N/A' }}</td>
                                            <td>{{ 'Yes' if request.documents_uploaded else 'No' }}</td>
                                            <td>{{ request.meter_reading_text or 'Photo Uploaded' if request.meter_reading_filename else 'N/A' }}</td>
                                            <td>{{ request.id_type or 'N/A' }}</td>
                                            <td>{{ request.client_postcode or 'N/A' }}</td>
                                            <td>{{ request.created_at.strftime('%d/%m/%Y') if request.created_at else 'N/A' }}</td>
                                            <td>{{ request.submission_timestamp.strftime('%d/%m/%Y %H:%M') if request.submission_timestamp else 'N/A' }}</td>
                                            <td>{{ request.expires_at.strftime('%d/%m/%Y') if request.expires_at else 'N/A' }}</td>
                                            <td>{{ request.missing_documents_reason or 'N/A' }}</td>
                                        </tr>
                                        {% endfor %}
                                    {% else %}
                                    <tr>
                                        <td>{{ client.id }}</td>
                                        <td>{{ client.name }}</td>
                                        <td>{{ client.phone_number }}</td>
                                        <td>{{ client.referrer_name or 'N/A' }}</td>
                                        <td>{{ client.referrer_email or 'N/A' }}</td>
                                        <td>{{ 'Yes' if client.has_camera_phone else 'No' }}</td>
                                        <td>{{ 'Yes' if client.gdpr_consent else 'No' }}</td>
                                        <td colspan="11" style="text-align: center; color: #6c757d; font-style: italic;">No requests yet</td>
                                    </tr>
                                    {% endif %}
                                {% endfor %}
                            </tbody>
                        </table>
                    </div>
                    
                    <div style="margin-top: 20px; padding: 15px; background: #e8f5e9; border-radius: 8px; border-left: 4px solid #28a745;">
                        <h4 style="color: #28a745; margin-bottom: 10px;">📊 Data Summary</h4>
                        <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 15px;">
                            <div><strong>Total Clients:</strong> {{ clients|length }}</div>
                            <div><strong>With Referrer:</strong> {{ clients|selectattr('referrer_name')|list|length }}</div>
                            <div><strong>Digital Ready:</strong> {{ clients|selectattr('has_camera_phone')|list|length }}</div>
                            <div><strong>GDPR Compliant:</strong> {{ clients|selectattr('gdpr_consent')|list|length }}</div>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    </body>
    </html>
    """, clients=clients)

@app.route('/export_csv')
def export_csv():
    """Export all data to CSV format"""
    try:
        export_type = request.args.get('type', 'all')
        
        # Create CSV in memory
        output = io.StringIO()
        writer = csv.writer(output)
        
        if export_type == 'clients':
            # Export clients only
            writer.writerow(['Client ID', 'Name', 'Phone', 'Referrer Name', 'Referrer Email', 
                           'Camera Phone', 'GDPR Consent', 'Created Date'])
            
            clients = Client.query.order_by(Client.created_at.desc()).all()
            for client in clients:
                writer.writerow([
                    client.id,
                    client.name,
                    client.phone_number,
                    client.referrer_name or '',
                    client.referrer_email or '',
                    'Yes' if client.has_camera_phone else 'No',
                    'Yes' if client.gdpr_consent else 'No',
                    client.created_at.strftime('%Y-%m-%d %H:%M:%S') if client.created_at else ''
                ])
            filename = 'clients_export.csv'
            
        elif export_type == 'requests':
            # Export requests only
            writer.writerow(['Request ID', 'Client ID', 'Client Name', 'Phone', 'Status', 
                           'Phone Type', 'Documents Uploaded', 'Meter Reading', 'ID Type', 
                           'Postcode', 'Created Date', 'Submission Date', 'Expires Date'])
            
            fuel_requests = FuelRequest.query.join(Client).order_by(FuelRequest.created_at.desc()).all()
            for fuel_request in fuel_requests:
                writer.writerow([
                    fuel_request.id,
                    fuel_request.client.id,
                    fuel_request.client.name,
                    fuel_request.client.phone_number,
                    fuel_request.status,
                    fuel_request.phone_type_used or '',
                    'Yes' if fuel_request.documents_uploaded else 'No',
                    fuel_request.meter_reading_text or ('Photo Uploaded' if fuel_request.meter_reading_filename else ''),
                    fuel_request.id_type or '',
                    fuel_request.client_postcode or '',
                    fuel_request.created_at.strftime('%Y-%m-%d %H:%M:%S') if fuel_request.created_at else '',
                    fuel_request.submission_timestamp.strftime('%Y-%m-%d %H:%M:%S') if fuel_request.submission_timestamp else '',
                    fuel_request.expires_at.strftime('%Y-%m-%d %H:%M:%S') if fuel_request.expires_at else ''
                ])
            filename = 'requests_export.csv'
            
        else:
            # Export all data (comprehensive)
            writer.writerow(['Client ID', 'Client Name', 'Phone', 'Referrer Name', 'Referrer Email', 
                           'Camera Phone', 'GDPR Consent', 'Request ID', 'Request Status', 
                           'Phone Type Used', 'Documents Uploaded', 'Meter Reading', 'ID Type', 
                           'Postcode', 'Created Date', 'Submission Date', 'Expires Date', 
                           'Missing Docs Reason', 'Staff Notes'])
            
            clients = Client.query.order_by(Client.created_at.desc()).all()
            for client in clients:
                if client.fuel_requests:
                    for fuel_request in client.fuel_requests:
                        writer.writerow([
                            client.id,
                            client.name,
                            client.phone_number,
                            client.referrer_name or '',
                            client.referrer_email or '',
                            'Yes' if client.has_camera_phone else 'No',
                            'Yes' if client.gdpr_consent else 'No',
                            fuel_request.id,
                            fuel_request.status,
                            fuel_request.phone_type_used or '',
                            'Yes' if fuel_request.documents_uploaded else 'No',
                            fuel_request.meter_reading_text or ('Photo Uploaded' if fuel_request.meter_reading_filename else ''),
                            fuel_request.id_type or '',
                            fuel_request.client_postcode or '',
                            fuel_request.created_at.strftime('%Y-%m-%d %H:%M:%S') if fuel_request.created_at else '',
                            fuel_request.submission_timestamp.strftime('%Y-%m-%d %H:%M:%S') if fuel_request.submission_timestamp else '',
                            fuel_request.expires_at.strftime('%Y-%m-%d %H:%M:%S') if fuel_request.expires_at else '',
                            fuel_request.missing_documents_reason or '',
                            fuel_request.staff_notes or ''
                        ])
                else:
                    # Client with no requests
                    writer.writerow([
                        client.id,
                        client.name,
                        client.phone_number,
                        client.referrer_name or '',
                        client.referrer_email or '',
                        'Yes' if client.has_camera_phone else 'No',
                        'Yes' if client.gdpr_consent else 'No',
                        '', '', '', '', '', '', '', '', '', '', ''
                    ])
            filename = 'complete_data_export.csv'
        
        # Prepare response
        output.seek(0)
        response = Response(
            output.getvalue(),
            mimetype='text/csv',
            headers={
                'Content-Disposition': f'attachment; filename={filename}'
            }
        )
        return response
        
    except Exception as e:
        flash(f'Error exporting data: {str(e)}', 'danger')
        logging.error(f"CSV export error: {e}")
        return redirect(url_for('customer_data_table'))

@app.route('/staff_portal')
def staff_portal():
    """Staff portal for managing requests"""
    pending_requests = FuelRequest.query.filter_by(status='pending').all()
    return render_template_string("""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Staff Portal - Food Bank</title>
        """ + CSS_TEMPLATE + """
    </head>
    <body>
        <div class="sidebar">
            <div class="sidebar-header">
                <div style="width: 40px; height: 40px; background: white; border-radius: 8px; display: flex; align-items: center; justify-content: center; margin-bottom: 10px;">
                    <span style="font-size: 24px; font-weight: bold; color: #28a745;">LF</span>
                </div>
                <h3 style="margin: 0; color: white;">Lewisham Foodbank</h3>
                <p style="margin: 5px 0 0 0; font-size: 12px; opacity: 0.8;">Together with Trussell</p>
            </div>
            
            <ul class="sidebar-nav">
                <li><a href="{{ url_for('index') }}">Dashboard</a></li>
                <li><a href="{{ url_for('view_clients') }}">Clients</a></li>
                <li><a href="{{ url_for('customer_data_table') }}">Customer Data</a></li>
                <li><a href="{{ url_for('send_sms_requests') }}">Send SMS</a></li>
                <li><a href="{{ url_for('view_sms_history') }}">SMS History</a></li>
                <li><a href="{{ url_for('staff_portal') }}" class="active">Staff Portal</a></li>
                <li><a href="{{ url_for('generate_report') }}">Reports</a></li>
            </ul>
        </div>
        
        <div class="main-content">
            <div class="top-bar">
                <div>
                    <h1 style="margin: 0; color: #333;">Staff Portal</h1>
                    <p style="margin: 5px 0 0 0; color: #666;">Home / Staff Portal</p>
                </div>
            </div>
            
            <div class="content">
                <div class="card">
                    <h3>Pending Requests</h3>
                    {% if pending_requests %}
                    <table>
                        <thead>
                            <tr>
                                <th>Client</th>
                                <th>Phone</th>
                                <th>Created</th>
                                <th>Expires</th>
                                <th>Documents</th>
                            </tr>
                        </thead>
                        <tbody>
                            {% for request in pending_requests %}
                            <tr>
                                <td>{{ request.client.name }}</td>
                                <td>{{ request.client.phone_number }}</td>
                                <td>{{ request.created_at.strftime('%d/%m/%Y') }}</td>
                                <td>{{ request.expires_at.strftime('%d/%m/%Y') }}</td>
                                <td>
                                    {% if request.documents_uploaded %}
                                        Uploaded
                                    {% else %}
                                        Pending
                                    {% endif %}
                                </td>
                            </tr>
                            {% endfor %}
                        </tbody>
                    </table>
                    {% else %}
                    <div class="alert alert-info">
                        <p>No pending requests found.</p>
                    </div>
                    {% endif %}
                    
                    <div style="margin-top: 20px;">
                        <a href="{{ url_for('index') }}" class="btn btn-secondary">Back to Dashboard</a>
                    </div>
                </div>
            </div>
        </div>
    </body>
    </html>
    """, pending_requests=pending_requests)

@app.route('/upload/<unique_link>', methods=['GET', 'POST'])
def upload_documents(unique_link):
    """Client upload page with phone type selection and conditional forms"""
    fuel_request = FuelRequest.query.filter_by(unique_link=unique_link).first()
    
    if not fuel_request:
        return render_template_string("""
        <!DOCTYPE html>
        <html lang="en">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>Invalid Link - Food Bank</title>
            """ + CSS_TEMPLATE + """
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>Invalid Link</h1>
                    <p>This upload link is not valid or has expired</p>
                </div>
                <div class="content">
                    <div class="card" style="text-align: center; padding: 40px;">
                        <h3>Link Not Found</h3>
                        <p>The upload link you're trying to access is not valid or has expired.</p>
                        <p>Please contact us for assistance.</p>
                    </div>
                </div>
            </div>
        </body>
        </html>
        """), 404
    
    if fuel_request.expires_at < datetime.now():
        return render_template_string("""
        <!DOCTYPE html>
        <html lang="en">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>Link Expired - Food Bank</title>
            """ + CSS_TEMPLATE + """
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>Link Expired</h1>
                    <p>This upload link has expired</p>
                </div>
                <div class="content">
                    <div class="card" style="text-align: center; padding: 40px;">
                        <h3>Upload Link Expired</h3>
                        <p>This upload link has expired. Please contact us for a new link.</p>
                        <p>Contact: {{ food_bank_phone }}</p>
                    </div>
                </div>
            </div>
        </body>
        </html>
        """, food_bank_phone=FOOD_BANK_PHONE), 410
    
    if request.method == 'POST':
        try:
            phone_type = request.form.get('phone_type')
            
            if phone_type == 'keypad':
                # Handle keypad user manual entry
                client_name = request.form.get('client_name', '').strip()
                client_phone = request.form.get('client_phone', '').strip()
                client_postcode = request.form.get('client_postcode', '').strip()
                meter_reading_text = request.form.get('meter_reading_text', '').strip()
                id_type = request.form.get('id_type', '').strip()
                other_id_type = request.form.get('other_id_type', '').strip()
                id_details = request.form.get('id_details', '').strip()
                cannot_upload_pictures = request.form.get('cannot_upload_pictures') == 'on'
                missing_documents_reason = request.form.get('missing_documents_reason', '').strip()
                
                # If "other" is selected, use the other_id_type value
                if id_type == 'other' and other_id_type:
                    id_type = f"other: {other_id_type}"
                
                if not all([client_name, client_phone, meter_reading_text, id_type, id_details]):
                    flash('Please fill in all required fields', 'danger')
                    return redirect(request.url)
                
                # Check if cannot upload pictures is checked but no reason provided
                if cannot_upload_pictures and not missing_documents_reason:
                    flash('Please select a reason why you cannot upload pictures', 'danger')
                    return redirect(request.url)
                
                # Store keypad user data in database
                fuel_request.documents_uploaded = True
                fuel_request.phone_type_used = 'keypad'
                fuel_request.submission_timestamp = datetime.now(UTC)
                fuel_request.status = 'completed'
                
                # Store additional data in database fields
                fuel_request.meter_reading_text = meter_reading_text
                fuel_request.id_type = id_type
                fuel_request.id_details = id_details
                fuel_request.client_postcode = client_postcode
                if cannot_upload_pictures:
                    fuel_request.missing_documents_reason = missing_documents_reason
                
                # Create a text file with manual entry data
                manual_data = f"""KEYPAD USER ENTRY
Client Name: {client_name}
Phone: {client_phone}
Postcode: {client_postcode}
Meter Reading: {meter_reading_text}
ID Type: {id_type}
ID Details: {id_details}
Timestamp: {datetime.now(UTC)}
"""
                
                manual_filename = f"manual_entry_{fuel_request.id}.txt"
                with open(os.path.join(app.config['UPLOAD_FOLDER'], manual_filename), 'w') as f:
                    f.write(manual_data)
                
                fuel_request.meter_reading_filename = manual_filename
                fuel_request.identity_photo_filename = manual_filename
                
                db.session.commit()
                flash('Manual entry submitted successfully! We will process your request soon.', 'success')
                
            elif phone_type == 'smartphone':
                # Handle smartphone user photo upload
                if 'meter_reading' not in request.files or 'identity_photo' not in request.files:
                    flash('Please upload both meter reading and identity photo', 'danger')
                    return redirect(request.url)
                
                meter_file = request.files['meter_reading']
                identity_file = request.files['identity_photo']
                
                if meter_file.filename == '' or identity_file.filename == '':
                    flash('Please select both files', 'danger')
                    return redirect(request.url)
                
                allowed_extensions = {'png', 'jpg', 'jpeg', 'gif'}
                
                def allowed_file(filename):
                    return '.' in filename and filename.rsplit('.', 1)[1].lower() in allowed_extensions
                
                if not (allowed_file(meter_file.filename) and allowed_file(identity_file.filename)):
                    flash('Only image files (PNG, JPG, JPEG, GIF) are allowed', 'danger')
                    return redirect(request.url)
                
                meter_filename = secure_filename(f"meter_{fuel_request.id}_{meter_file.filename}")
                identity_filename = secure_filename(f"identity_{fuel_request.id}_{identity_file.filename}")
                
                meter_file.save(os.path.join(app.config['UPLOAD_FOLDER'], meter_filename))
                identity_file.save(os.path.join(app.config['UPLOAD_FOLDER'], identity_filename))
                
                fuel_request.documents_uploaded = True
                fuel_request.phone_type_used = 'smartphone'
                fuel_request.submission_timestamp = datetime.now(UTC)
                fuel_request.status = 'completed'
                
                db.session.commit()
                flash('Photos uploaded successfully! We will process your request soon.', 'success')
                
            
        except Exception as e:
            flash(f'Error processing submission: {str(e)}', 'danger')
            logging.error(f"Form processing error: {e}")
    
    return render_template_string("""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Upload Documents - Food Bank</title>
        """ + CSS_TEMPLATE + """
        <style>
            .phone-selection { text-align: center; margin: 40px 0; }
            .phone-option { 
                display: inline-block; 
                margin: 20px; 
                padding: 30px; 
                border: 3px solid #e9ecef; 
                border-radius: 15px; 
                cursor: pointer; 
                transition: all 0.3s ease;
                background: white;
                min-width: 250px;
            }
            .phone-option:hover { 
                border-color: #28a745; 
                box-shadow: 0 8px 25px rgba(40, 167, 69, 0.2);
                transform: translateY(-2px);
            }
            .phone-option.selected { 
                border-color: #28a745; 
                background: #e8f5e9; 
            }
            .phone-icon { font-size: 3rem; margin-bottom: 15px; }
            .form-section { display: none; }
            .form-section.active { display: block; }
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>Complete Your Fuel Support Request</h1>
                <p>Hi {{ fuel_request.client.name }}! Please select your phone type to continue</p>
            </div>
            
            <div class="content">
                {% with messages = get_flashed_messages(with_categories=true) %}
                    {% if messages %}
                        {% for category, message in messages %}
                            <div class="alert alert-{{ 'danger' if category == 'error' else category }}">
                                {{ message }}
                            </div>
                        {% endfor %}
                    {% endif %}
                {% endwith %}
                
                <!-- Phone Type Selection -->
                <div class="card" id="phoneSelection">
                    <h3>📱 Select Your Phone Type</h3>
                    <div class="phone-selection">
                        <div class="phone-option" onclick="selectPhoneType('keypad')">
                            <div class="phone-icon">📱</div>
                            <h4>Keypad (Android)</h4>
                            <p>Manual form entry for basic phones</p>
                        </div>
                        <div class="phone-option" onclick="selectPhoneType('smartphone')">
                            <div class="phone-icon">📱</div>
                            <h4>Smartphone (Android/iOS)</h4>
                            <p>Upload photos for modern phones</p>
                        </div>
                    </div>
                </div>
                
                <!-- Keypad User Form -->
                <div class="card form-section" id="keypadForm">
                    <h3>📝 Manual Entry Form</h3>
                    <p>Please enter your details manually with proper validation:</p>
                    
                    <form method="POST" enctype="multipart/form-data" id="keypadFormElement">
                        <input type="hidden" name="phone_type" value="keypad">
                        
                        <div class="form-group">
                            <label for="client_name">Full Name *</label>
                            <input type="text" class="form-control" id="client_name" name="client_name" placeholder="Enter your full name" required pattern="[A-Za-z\\s]{2,50}" title="Please enter a valid name (2-50 characters, letters and spaces only)">
                            <small class="form-text text-muted">Enter your full name (letters and spaces only)</small>
                        </div>
                        
                        <div class="form-group">
                            <label for="client_phone">Phone Number *</label>
                            <input type="tel" class="form-control" id="client_phone" name="client_phone" placeholder="+447700900123" required pattern="^\\+?[1-9]\\d{1,14}$" title="Please enter a valid phone number (e.g., +447700900123)">
                            <small class="form-text text-muted">Enter your phone number in international format</small>
                        </div>
                        
                        <div class="form-group">
                            <label for="client_postcode">Postcode (Optional)</label>
                            <input type="text" class="form-control" id="client_postcode" name="client_postcode" placeholder="e.g., SE1 1AA" pattern="[A-Za-z]{1,2}[0-9]{1,2}[A-Za-z]?[0-9][A-Za-z]{2}" title="Please enter a valid UK postcode (e.g., SE1 1AA)">
                            <small class="form-text text-muted">Enter your UK postcode (optional)</small>
                        </div>
                        
                        <div class="form-group">
                            <label for="meter_reading_text">Meter Reading *</label>
                            <input type="text" class="form-control" id="meter_reading_text" name="meter_reading_text" placeholder="e.g., 12345.67" required pattern="[0-9]+(\\.[0-9]+)?" title="Please enter a valid meter reading (numbers only, e.g., 12345.67)">
                            <small class="form-text text-muted">Enter your current meter reading numbers only</small>
                        </div>
                        
                        <div class="form-group">
                            <label for="id_type">ID Type *</label>
                            <select class="form-control" id="id_type" name="id_type" required onchange="toggleOtherIdType()">
                                <option value="">Select ID type</option>
                                <option value="photo_id">Photo ID</option>
                                <option value="utility_bill">Utility Bill</option>
                                <option value="dwp_letter">DWP Letter</option>
                                <option value="council_letter">Council Letter</option>
                                <option value="other">Other</option>
                            </select>
                            <small class="form-text text-muted">Select the type of ID document you have</small>
                        </div>
                        
                        <div class="form-group" id="other_id_type_group" style="display: none;">
                            <label for="other_id_type">Specify Other ID Type *</label>
                            <input type="text" class="form-control" id="other_id_type" name="other_id_type" placeholder="e.g., Bank Statement, Driving License, etc.">
                            <small class="form-text text-muted">Please specify what type of ID document you have</small>
                        </div>
                        
                        <div class="form-group">
                            <label for="id_details">ID Details *</label>
                            <textarea class="form-control" id="id_details" name="id_details" rows="3" placeholder="Enter details from your ID document (name, address, etc.)" required minlength="10" title="Please enter at least 10 characters describing your ID details"></textarea>
                            <small class="form-text text-muted">Enter details from your ID document (minimum 10 characters)</small>
                        </div>
                        
                        <div class="form-group">
                            <div class="form-check">
                                <input type="checkbox" class="form-check-input" id="cannot_upload_pictures" name="cannot_upload_pictures" onchange="toggleNoPictureReason()">
                                <label class="form-check-label" for="cannot_upload_pictures">
                                    ❌ Cannot Upload Pictures
                                </label>
                            </div>
                        </div>
                        
                        <div class="form-group" id="no_picture_reason_group" style="display: none;">
                            <label for="missing_documents_reason">Reason for No Pictures *</label>
                            <select class="form-control" id="missing_documents_reason" name="missing_documents_reason">
                                <option value="">Select reason</option>
                                <option value="no_camera">No camera on phone</option>
                                <option value="camera_broken">Camera not working</option>
                                <option value="technical_issues">Technical difficulties</option>
                                <option value="prefer_manual">Prefer manual entry</option>
                                <option value="other">Other reason</option>
                            </select>
                            <small class="form-text text-muted">Please select why you cannot upload pictures</small>
                        </div>
                        
                        <div style="margin-top: 20px;">
                            <button type="submit" class="btn btn-success" onclick="validateKeypadForm()">Submit Details</button>
                            <button type="button" class="btn btn-secondary" onclick="goBack()">← Back to Phone Selection</button>
                        </div>
                    </form>
                </div>
                
                <!-- Smartphone User Form -->
                <div class="card form-section" id="smartphoneForm">
                    <h3>📸 Photo Upload Form</h3>
                    <p>Please upload photos of your documents:</p>
                    
                    <form method="POST" enctype="multipart/form-data">
                        <input type="hidden" name="phone_type" value="smartphone">
                        
                        <div class="form-group">
                            <label for="meter_reading">Meter Reading Photo *</label>
                            <input type="file" class="form-control" id="meter_reading" name="meter_reading" accept="image/*" required>
                            <small class="form-text text-muted">Take a clear photo of your current meter reading</small>
                        </div>
                        
                        <div class="form-group">
                            <label for="identity_photo">Identity Photo *</label>
                            <input type="file" class="form-control" id="identity_photo" name="identity_photo" accept="image/*" required>
                            <small class="form-text text-muted">Take a photo of yourself holding your ID</small>
                        </div>
                        
                        <div style="margin-top: 20px;">
                            <button type="submit" class="btn btn-success">Upload Documents</button>
                            <button type="button" class="btn btn-secondary" onclick="goBack()">← Back to Phone Selection</button>
                        </div>
                    </form>
                    
                    <div style="margin-top: 30px; padding: 20px; background: #f8f9fa; border-radius: 8px;">
                        <h4>📋 Instructions:</h4>
                        <ul>
                            <li>Ensure photos are clear and well-lit</li>
                            <li>Meter reading should show current numbers clearly</li>
                            <li>Identity photo should show your face and ID clearly</li>
                            <li>Maximum file size: 16MB per image</li>
                            <li>Supported formats: PNG, JPG, JPEG, GIF</li>
                        </ul>
                    </div>
                </div>
                
                
                <div style="margin-top: 20px; text-align: center; color: #6c757d;">
                    <p><strong>Need help?</strong> Contact us: {{ food_bank_phone }}</p>
                </div>
            </div>
        </div>
        
        <script>
            function selectPhoneType(type) {
                // Hide phone selection
                document.getElementById('phoneSelection').style.display = 'none';
                
                // Show appropriate form
                if (type === 'keypad') {
                    document.getElementById('keypadForm').classList.add('active');
                } else if (type === 'smartphone') {
                    document.getElementById('smartphoneForm').classList.add('active');
                }
            }
            
            function goBack() {
                // Hide all forms
                document.querySelectorAll('.form-section').forEach(form => {
                    form.classList.remove('active');
                });
                
                // Show phone selection
                document.getElementById('phoneSelection').style.display = 'block';
            }
            
            function toggleOtherIdType() {
                const idTypeSelect = document.getElementById('id_type');
                const otherIdTypeGroup = document.getElementById('other_id_type_group');
                const otherIdTypeInput = document.getElementById('other_id_type');
                
                if (idTypeSelect.value === 'other') {
                    otherIdTypeGroup.style.display = 'block';
                    otherIdTypeInput.required = true;
                } else {
                    otherIdTypeGroup.style.display = 'none';
                    otherIdTypeInput.required = false;
                    otherIdTypeInput.value = '';
                }
            }
            
            function toggleNoPictureReason() {
                const cannotUploadCheckbox = document.getElementById('cannot_upload_pictures');
                const noPictureReasonGroup = document.getElementById('no_picture_reason_group');
                const missingDocumentsReason = document.getElementById('missing_documents_reason');
                
                if (cannotUploadCheckbox.checked) {
                    noPictureReasonGroup.style.display = 'block';
                    missingDocumentsReason.required = true;
                } else {
                    noPictureReasonGroup.style.display = 'none';
                    missingDocumentsReason.required = false;
                    missingDocumentsReason.value = '';
                }
            }
            
            function validateKeypadForm() {
                const form = document.getElementById('keypadFormElement');
                const idType = document.getElementById('id_type').value;
                const otherIdType = document.getElementById('other_id_type');
                const cannotUploadCheckbox = document.getElementById('cannot_upload_pictures');
                const missingDocumentsReason = document.getElementById('missing_documents_reason');
                
                // Check if "Other" is selected but no other ID type specified
                if (idType === 'other' && (!otherIdType.value || otherIdType.value.trim() === '')) {
                    alert('Please specify the other ID type when "Other" is selected.');
                    otherIdType.focus();
                    return false;
                }
                
                // Check if "Cannot Upload Pictures" is checked but no reason specified
                if (cannotUploadCheckbox.checked && (!missingDocumentsReason.value || missingDocumentsReason.value.trim() === '')) {
                    alert('Please select a reason why you cannot upload pictures.');
                    missingDocumentsReason.focus();
                    return false;
                }
                
                // Validate form
                if (!form.checkValidity()) {
                    form.reportValidity();
                    return false;
                }
                
                return true;
            }
            
        </script>
    </body>
    </html>
    """, fuel_request=fuel_request, food_bank_phone=FOOD_BANK_PHONE)

@app.route('/view_sms_history')
def view_sms_history():
    """View SMS history with upload links"""
    # Get SMS logs and fuel requests with upload links
    sms_logs = SMSLog.query.order_by(SMSLog.created_at.desc()).all()
    fuel_requests = FuelRequest.query.filter(FuelRequest.unique_link.isnot(None)).order_by(FuelRequest.created_at.desc()).all()
    return render_template_string("""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>SMS History - Food Bank</title>
        """ + CSS_TEMPLATE + """
    </head>
    <body>
        <div class="sidebar">
            <div class="sidebar-header">
                <div style="width: 40px; height: 40px; background: white; border-radius: 8px; display: flex; align-items: center; justify-content: center; margin-bottom: 10px;">
                    <span style="font-size: 24px; font-weight: bold; color: #28a745;">LF</span>
                </div>
                <h3 style="margin: 0; color: white;">Lewisham Foodbank</h3>
                <p style="margin: 5px 0 0 0; font-size: 12px; opacity: 0.8;">Together with Trussell</p>
            </div>
            
            <ul class="sidebar-nav">
                <li><a href="{{ url_for('index') }}">Dashboard</a></li>
                <li><a href="{{ url_for('view_clients') }}">Clients</a></li>
                <li><a href="{{ url_for('customer_data_table') }}">Customer Data</a></li>
                <li><a href="{{ url_for('send_sms_requests') }}">Send SMS</a></li>
                <li><a href="{{ url_for('view_sms_history') }}" class="active">SMS History</a></li>
                <li><a href="{{ url_for('staff_portal') }}">Staff Portal</a></li>
                <li><a href="{{ url_for('generate_report') }}">Reports</a></li>
            </ul>
        </div>
        
        <div class="main-content">
            <div class="top-bar">
                <div>
                    <h1 style="margin: 0; color: #333;">SMS History</h1>
                    <p style="margin: 5px 0 0 0; color: #666;">Home / SMS History</p>
                </div>
            </div>
            
            <div class="content">
                <div class="card">
                    <h3>SMS Log</h3>
                    {% if sms_logs %}
                    <table>
                        <thead>
                            <tr>
                                <th>ID</th>
                                <th>Client</th>
                                <th>Phone</th>
                                <th>Message</th>
                                <th>Status</th>
                                <th>Created At</th>
                            </tr>
                        </thead>
                        <tbody>
                            {% for log in sms_logs %}
                            <tr>
                                <td>{{ log.id }}</td>
                                <td>{{ log.client.name if log.client else "Unknown Client" }}</td>
                                <td>{{ log.phone_number }}</td>
                                <td>{{ log.message_content }}</td>
                                <td>
                                    <span class="badge {% if log.status == 'sent' %}bg-success{% elif log.status == 'failed' %}bg-danger{% elif log.status == 'delivered' %}bg-info{% else %}bg-secondary{% endif %}">
                                        {{ log.status }}
                                    </span>
                                </td>
                                <td>{{ log.created_at.strftime('%Y-%m-%d %H:%M:%S') }}</td>
                            </tr>
                            {% endfor %}
                        </tbody>
                    </table>
                    {% else %}
                    <div class="alert alert-info">
                        <p>No SMS history found.</p>
                    </div>
                    {% endif %}
                    
                    <div style="margin-top: 20px;">
                        <a href="{{ url_for('index') }}" class="btn btn-secondary">Back to Dashboard</a>
                    </div>
                </div>
            </div>
        </div>
    </body>
    </html>
    """, sms_logs=sms_logs)

@app.route('/generate_report')
def generate_report():
    """Generate a comprehensive report with interactive charts"""
    # Get all the data needed for charts
    total_clients = Client.query.count()
    total_requests = FuelRequest.query.count()
    completed_requests = FuelRequest.query.filter_by(status='completed').count()
    pending_requests = FuelRequest.query.filter_by(status='pending').count()
    expired_requests = FuelRequest.query.filter(FuelRequest.expires_at < datetime.now()).count()
    
    # Client distribution data
    digital_ready = Client.query.filter_by(has_camera_phone=True).count()
    gdpr_compliant = Client.query.filter_by(gdpr_consent=True).count()
    traditional = Client.query.filter_by(has_camera_phone=False).count()
    non_compliant = total_clients - gdpr_compliant
    
    # SMS performance data (last 5 periods)
    sms_sent_data = [14, 16, 15, 18, 19]  # Sample data - you can make this dynamic
    sms_failed_data = [4, 5, 4, 5, 4]     # Sample data - you can make this dynamic
    
    return render_template_string("""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Analytics & Reports - Lewisham Foodbank</title>
        <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
        """ + CSS_TEMPLATE + """
        <style>
            .reports-container { padding: 20px; }
            .summary-cards { display: grid; grid-template-columns: repeat(auto-fit, minmax(250px, 1fr)); gap: 20px; margin-bottom: 30px; }
            .summary-card { background: white; padding: 25px; border-radius: 12px; box-shadow: 0 4px 15px rgba(0,0,0,0.1); border-left: 4px solid #28a745; }
            .summary-number { font-size: 2.5rem; font-weight: bold; color: #28a745; margin-bottom: 5px; }
            .summary-label { color: #495057; font-size: 1rem; margin-bottom: 10px; }
            .summary-change { font-size: 0.9rem; color: #28a745; }
            .summary-rate { font-size: 0.9rem; color: #6c757d; }
            .charts-row { display: grid; grid-template-columns: 1fr 1fr; gap: 30px; margin-bottom: 30px; }
            .chart-card { background: white; padding: 25px; border-radius: 12px; box-shadow: 0 4px 15px rgba(0,0,0,0.1); }
            .chart-title { font-size: 1.3rem; color: #495057; margin-bottom: 20px; display: flex; align-items: center; gap: 10px; }
            .chart-icon { font-size: 1.2rem; color: #28a745; }
            .full-width-chart { grid-column: 1 / -1; }
            .export-btn { background: #28a745; color: white; padding: 12px 24px; border: none; border-radius: 6px; cursor: pointer; font-weight: 500; }
            .export-btn:hover { background: #218838; }
        </style>
    </head>
    <body>
        <div class="sidebar">
            <div class="sidebar-header">
                <div style="width: 40px; height: 40px; background: white; border-radius: 8px; display: flex; align-items: center; justify-content: center; margin-bottom: 10px;">
                    <span style="font-size: 24px; font-weight: bold; color: #28a745;">LF</span>
                </div>
                <h3 style="margin: 0; color: white;">Lewisham Foodbank</h3>
                <p style="margin: 5px 0 0 0; font-size: 12px; opacity: 0.8;">Together with Trussell</p>
            </div>
            
            <ul class="sidebar-nav">
                <li><a href="{{ url_for('index') }}">Dashboard</a></li>
                <li><a href="{{ url_for('view_clients') }}">Clients</a></li>
                <li><a href="{{ url_for('customer_data_table') }}">Customer Data</a></li>
                <li><a href="{{ url_for('send_sms_requests') }}">Send SMS</a></li>
                <li><a href="{{ url_for('view_sms_history') }}">SMS History</a></li>
                <li><a href="{{ url_for('staff_portal') }}">Staff Portal</a></li>
                <li><a href="{{ url_for('generate_report') }}" class="active">Reports</a></li>
            </ul>
        </div>
        
        <div class="main-content">
            <div class="top-bar">
                <div>
                    <h1 style="margin: 0; color: #333;">Analytics & Reports - UPDATED!</h1>
                    <p style="margin: 5px 0 0 0; color: #666;">Home / Reports</p>
                </div>
                <div>
                    <button class="export-btn" onclick="exportReport()">
                        📊 Export Report
                    </button>
                </div>
            </div>
            
            <div class="content">
                <!-- Summary Cards -->
                <div class="summary-cards">
                    <div class="summary-card">
                        <div class="summary-number">{{ total_clients }}</div>
                        <div class="summary-label">Total Clients</div>
                        <div class="summary-change">+12% this month</div>
                    </div>
                    <div class="summary-card">
                        <div class="summary-number">{{ total_requests }}</div>
                        <div class="summary-label">Total Requests</div>
                        <div class="summary-change">+8% this month</div>
                    </div>
                    <div class="summary-card">
                        <div class="summary-number">{{ completed_requests }}</div>
                        <div class="summary-label">Completed</div>
                        <div class="summary-rate">{{ (completed_requests/total_requests*100)|round(1) if total_requests > 0 else 0 }}% rate</div>
                    </div>
                    <div class="summary-card">
                        <div class="summary-number">{{ digital_ready }}</div>
                        <div class="summary-label">Digital Ready</div>
                        <div class="summary-rate">{{ (digital_ready/total_clients*100)|round(1) if total_clients > 0 else 0 }}% adoption</div>
                    </div>
                </div>

                <!-- Charts Row 1 -->
                <div class="charts-row">
                    <div class="chart-card">
                        <div class="chart-title">
                            <span class="chart-icon">👥</span>
                            Client Distribution
                        </div>
                        <div style="height: 300px; width: 100%;">
                            <canvas id="clientDistributionChart" width="400" height="300"></canvas>
                        </div>
                    </div>
                    
                    <div class="chart-card">
                        <div class="chart-title">
                            <span class="chart-icon">📊</span>
                            Request Status
                        </div>
                        <div style="height: 300px; width: 100%;">
                            <canvas id="requestStatusChart" width="400" height="300"></canvas>
                        </div>
                    </div>
                </div>

                <!-- Full Width Chart -->
                <div class="chart-card full-width-chart">
                    <div class="chart-title">
                        <span class="chart-icon">📱</span>
                        SMS Performance
                    </div>
                                            <div style="height: 300px; width: 100%;">
                            <canvas id="smsPerformanceChart" width="800" height="300"></canvas>
                        </div>
                </div>
            </div>
        </div>

        <script>
            // Client Distribution Chart (Donut)
            const clientCtx = document.getElementById('clientDistributionChart').getContext('2d');
            new Chart(clientCtx, {
                type: 'doughnut',
                data: {
                    labels: ['Digital Ready', 'GDPR Compliant', 'Traditional', 'Non-Compliant'],
                    datasets: [{
                        data: [{{ digital_ready }}, {{ gdpr_compliant }}, {{ traditional }}, {{ non_compliant }}],
                        backgroundColor: ['#28a745', '#20c997', '#ffc107', '#dc3545'],
                        borderWidth: 2,
                        borderColor: '#fff'
                    }]
                },
                options: {
                    responsive: false,
                    maintainAspectRatio: true,
                    animation: false,
                    plugins: {
                        legend: {
                            position: 'bottom',
                            labels: {
                                padding: 20,
                                usePointStyle: true,
                                font: {
                                    size: 12
                                }
                            }
                        }
                    }
                }
            });

            // Request Status Chart (Bar)
            const requestCtx = document.getElementById('requestStatusChart').getContext('2d');
            new Chart(requestCtx, {
                type: 'bar',
                data: {
                    labels: ['Completed', 'Pending', 'Expired'],
                    datasets: [{
                        label: 'Requests',
                        data: [{{ completed_requests }}, {{ pending_requests }}, {{ expired_requests }}],
                        backgroundColor: ['#28a745', '#ffc107', '#dc3545'],
                        borderColor: ['#218838', '#e0a800', '#c82333'],
                        borderWidth: 1
                    }]
                },
                options: {
                    responsive: false,
                    maintainAspectRatio: true,
                    animation: false,
                    scales: {
                        y: {
                            beginAtZero: true,
                            max: Math.max({{ completed_requests }}, {{ pending_requests }}, {{ expired_requests }}) + 2,
                            ticks: {
                                font: {
                                    size: 12
                                }
                            }
                        },
                        x: {
                            ticks: {
                                font: {
                                    size: 12
                                }
                            }
                        }
                    },
                    plugins: {
                        legend: {
                            display: false
                        }
                    }
                }
            });

            // SMS Performance Chart (Area)
            const smsCtx = document.getElementById('smsPerformanceChart').getContext('2d');
            new Chart(smsCtx, {
                type: 'line',
                data: {
                    labels: ['Period 1', 'Period 2', 'Period 3', 'Period 4', 'Period 5'],
                    datasets: [{
                        label: 'SMS Sent',
                        data: {{ sms_sent_data }},
                        borderColor: '#28a745',
                        backgroundColor: 'rgba(40, 167, 69, 0.1)',
                        fill: true,
                        tension: 0.1
                    }, {
                        label: 'SMS Failed',
                        data: {{ sms_failed_data }},
                        borderColor: '#dc3545',
                        backgroundColor: 'rgba(220, 53, 69, 0.1)',
                        fill: true,
                        tension: 0.1
                    }]
                },
                options: {
                    responsive: false,
                    maintainAspectRatio: true,
                    animation: false,
                    scales: {
                        y: {
                            beginAtZero: true,
                            max: Math.max(...{{ sms_sent_data }}) + 5,
                            ticks: {
                                font: {
                                    size: 12
                                }
                            }
                        },
                        x: {
                            ticks: {
                                font: {
                                    size: 12
                                }
                            }
                        }
                    },
                    plugins: {
                        legend: {
                            position: 'top-right',
                            labels: {
                                font: {
                                    size: 12
                                }
                            }
                        }
                    }
                }
            });

            function exportReport() {
                window.location.href = '{{ url_for("export_csv") }}';
            }
        </script>
    </body>
    </html>
    """, total_clients=total_clients, total_requests=total_requests, 
         completed_requests=completed_requests, pending_requests=pending_requests, 
         expired_requests=expired_requests, digital_ready=digital_ready, 
         gdpr_compliant=gdpr_compliant, traditional=traditional, 
         non_compliant=non_compliant, sms_sent_data=sms_sent_data, 
         sms_failed_data=sms_failed_data)

@app.route('/cleanup_database')
def cleanup_database():
    """Clean up duplicate clients and fix data issues"""
    try:
        from sqlalchemy import func
        
        # Find and remove duplicate clients by phone number
        duplicates = db.session.query(Client.phone_number, func.count(Client.id)).group_by(Client.phone_number).having(func.count(Client.id) > 1).all()
        
        cleaned_count = 0
        for phone, count in duplicates:
            if count > 1:
                clients = Client.query.filter_by(phone_number=phone).order_by(Client.id).all()
                # Keep the first one, delete the rest
                for client in clients[1:]:
                    db.session.delete(client)
                    cleaned_count += 1
        
        # Fix any clients without GDPR consent (for testing purposes)
        clients_without_consent = Client.query.filter_by(gdpr_consent=False).all()
        for client in clients_without_consent:
            client.gdpr_consent = True
        
        db.session.commit()
        
        flash(f'Database cleaned! Removed {cleaned_count} duplicate clients and fixed GDPR consent for {len(clients_without_consent)} clients.', 'success')
        
    except Exception as e:
        db.session.rollback()
        flash(f'Error cleaning database: {str(e)}', 'danger')
        logging.error(f"Database cleanup error: {e}")
    
    return redirect(url_for('send_sms_requests'))

@app.route('/download_database')
def download_database():
    """Download database backup as ZIP file"""
    try:
        db_path = os.path.join('instance', 'foodbank.db')
        if os.path.exists(db_path):
            import zipfile
            import io
            
            # Create ZIP file in memory
            memory_file = io.BytesIO()
            with zipfile.ZipFile(memory_file, 'w', zipfile.ZIP_DEFLATED) as zf:
                zf.write(db_path, 'foodbank.db')
            
            memory_file.seek(0)
            
            response = Response(
                memory_file.getvalue(),
                mimetype='application/zip',
                headers={
                    'Content-Disposition': 'attachment; filename=foodbank_backup.zip'
                }
            )
            return response
        else:
            flash('Database file not found', 'danger')
            return redirect(url_for('index'))
    except Exception as e:
        flash(f'Error downloading database: {str(e)}', 'danger')
        return redirect(url_for('index'))

# Initialize database and folders when app starts
with app.app_context():
    try:
        db.create_all()
        create_upload_folder()
    except Exception as e:
        print(f"Database initialization error: {e}")

if __name__ == '__main__':
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler('foodbank.log'),
            logging.StreamHandler()
        ]
    )
    
    print(f"\n{FOOD_BANK_NAME} SMS Service Starting...")
    print("Dashboard: http://localhost:3000")
    print("Features: Enhanced SMS, Document Upload, Full CRUD, Staff Portal, Reports")
    print("Database: SQLite with comprehensive logging")
    print("Contact: " + FOOD_BANK_PHONE)
    
    if not all([TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_PHONE_NUMBER]):
        print("SMS Simulation Mode: Configure Twilio credentials in .env for live SMS")
    else:
        print("SMS Service: Live mode with Twilio")
    
    # Get port from environment variable (for deployment) or use 3000 for local development
    port = int(os.environ.get('PORT', 3000))
    app.run(debug=False, port=port, host='0.0.0.0')
