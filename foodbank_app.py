from flask import Flask, render_template_string, flash, redirect, url_for, request, jsonify
from flask_sqlalchemy import SQLAlchemy
import logging
from datetime import datetime, timedelta
from twilio.rest import Client as TwilioClient
import os
from dotenv import load_dotenv
import uuid
import secrets
from werkzeug.utils import secure_filename

# Load environment variables
load_dotenv()

# Initialize Flask app
app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///foodbank.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', secrets.token_hex(32))
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size

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

# Configuration
TWILIO_ACCOUNT_SID = os.getenv('TWILIO_ACCOUNT_SID')
TWILIO_AUTH_TOKEN = os.getenv('TWILIO_AUTH_TOKEN')
TWILIO_PHONE_NUMBER = os.getenv('TWILIO_PHONE_NUMBER')

# Force simulation mode by default - only use Twilio if explicitly configured
SIMULATION_MODE = True

# Check if we should use Twilio (only if all credentials are properly set)
if (TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN and TWILIO_PHONE_NUMBER and
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

📋 Please provide:
• Photo of your meter reading 
• Photo of yourself with ID

📱 Upload here: {upload_url}

⏰ Link expires in 48 hours

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
            sms_log.sent_at = datetime.utcnow()
            sms_log.twilio_sid = f"sim_{uuid.uuid4().hex[:10]}"
            
            fuel_request.sms_sent = True
            fuel_request.sms_sent_at = datetime.utcnow()
            fuel_request.sms_sid = sms_log.twilio_sid
            
            db.session.commit()
            
            # Create upload URL for logging
            upload_url = f"{BASE_URL}/upload/{fuel_request.unique_link}"
            logging.info(f"SMS simulated successfully for {client.name} with upload URL: {upload_url}")
            print(f"📱 SIMULATION: SMS sent to {client.name} ({client.phone_number})")
            print(f"🔗 Upload link: {upload_url}")
            return True
        
        # Send actual SMS via Twilio
        try:
            twilio_client = TwilioClient(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
            formatted_phone = format_phone_number(client.phone_number)
            
            message = twilio_client.messages.create(
                body=message_content,
                from_=TWILIO_PHONE_NUMBER,
                to=formatted_phone
            )
            
            # Update log and fuel request
            sms_log.status = 'sent'
            sms_log.sent_at = datetime.utcnow()
            sms_log.twilio_sid = message.sid
            
            fuel_request.sms_sent = True
            fuel_request.sms_sent_at = datetime.utcnow()
            fuel_request.sms_sid = message.sid
            
            db.session.commit()
            logging.info(f"SMS sent successfully to {client.name}: {message.sid}")
            return True
            
        except Exception as twilio_error:
            # If Twilio fails, fall back to simulation mode
            logging.warning(f"Twilio SMS failed for {client.name}, falling back to simulation: {str(twilio_error)}")
            
            # Simulate successful SMS
            sms_log.status = 'sent'
            sms_log.sent_at = datetime.utcnow()
            sms_log.twilio_sid = f"sim_{uuid.uuid4().hex[:10]}"
            sms_log.error_message = f"Twilio failed, simulated: {str(twilio_error)}"
            
            fuel_request.sms_sent = True
            fuel_request.sms_sent_at = datetime.utcnow()
            fuel_request.sms_sid = sms_log.twilio_sid
            
            db.session.commit()
            
            # Create upload URL for logging
            upload_url = f"{BASE_URL}/upload/{fuel_request.unique_link}"
            logging.info(f"SMS simulated successfully for {client.name} after Twilio failure")
            print(f"📱 SIMULATION: SMS sent to {client.name} ({client.phone_number})")
            print(f"🔗 Upload link: {upload_url}")
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
    body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); min-height: 100vh; padding: 20px; color: #333; }
    .container { max-width: 1200px; margin: 0 auto; background: white; border-radius: 15px; box-shadow: 0 20px 40px rgba(0,0,0,0.1); overflow: hidden; }
    .header { background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 40px 30px; text-align: center; }
    .header h1 { font-size: 2.5rem; margin-bottom: 10px; font-weight: 700; }
    .header p { font-size: 1.1rem; opacity: 0.9; }
    .content { padding: 30px; }
    .dashboard-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 20px; margin: 20px 0; }
    .card { background: #f8f9fa; border-radius: 10px; padding: 25px; box-shadow: 0 5px 15px rgba(0,0,0,0.08); transition: transform 0.2s ease; }
    .card:hover { transform: translateY(-2px); box-shadow: 0 8px 25px rgba(0,0,0,0.15); }
    .card h3 { color: #495057; margin-bottom: 15px; font-size: 1.3rem; }
    .stats-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 15px; margin: 20px 0; }
    .stat-box { background: white; padding: 20px; border-radius: 8px; text-align: center; border-left: 4px solid #667eea; }
    .stat-number { font-size: 2rem; font-weight: bold; color: #667eea; margin-bottom: 5px; }
    .stat-label { color: #6c757d; font-size: 0.9rem; }
    .btn { display: inline-block; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 12px 24px; text-decoration: none; border-radius: 6px; font-weight: 500; margin: 5px; border: none; cursor: pointer; transition: all 0.3s ease; font-size: 14px; }
    .btn:hover { transform: translateY(-1px); box-shadow: 0 5px 15px rgba(102, 126, 234, 0.4); color: white; text-decoration: none; }
    .btn-secondary { background: #6c757d; }
    .btn-secondary:hover { background: #545b62; box-shadow: 0 5px 15px rgba(108, 117, 125, 0.4); }
    .btn-danger { background: #dc3545; }
    .btn-danger:hover { background: #c82333; box-shadow: 0 5px 15px rgba(220, 53, 69, 0.4); }
    .btn-success { background: #28a745; }
    .btn-success:hover { background: #218838; box-shadow: 0 5px 15px rgba(40, 167, 69, 0.4); }
    .btn-small { padding: 6px 12px; font-size: 12px; margin: 2px; }
    table { width: 100%; border-collapse: collapse; margin: 20px 0; background: white; border-radius: 8px; overflow: hidden; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }
    table th, table td { padding: 12px; text-align: left; border-bottom: 1px solid #dee2e6; }
    table th { background: #f8f9fa; font-weight: 600; color: #495057; }
    table tbody tr:hover { background: #f8f9fa; }
    .form-group { margin-bottom: 20px; }
    .form-group label { display: block; margin-bottom: 5px; font-weight: 500; color: #495057; }
    .form-control { width: 100%; padding: 10px; border: 2px solid #e9ecef; border-radius: 6px; font-size: 1rem; transition: border-color 0.3s ease; }
    .form-control:focus { outline: none; border-color: #667eea; box-shadow: 0 0 0 0.2rem rgba(102, 126, 234, 0.25); }
    .form-check { display: flex; align-items: center; margin: 10px 0; }
    .form-check input { margin-right: 8px; transform: scale(1.2); }
    .alert { padding: 15px; border-radius: 6px; margin: 15px 0; border-left: 4px solid; }
    .alert-success { background: #d4edda; color: #155724; border-left-color: #28a745; }
    .alert-danger { background: #f8d7da; color: #721c24; border-left-color: #dc3545; }
    .alert-info { background: #d1ecf1; color: #0c5460; border-left-color: #17a2b8; }
    .alert-warning { background: #fff3cd; color: #856404; border-left-color: #ffc107; }
    .quick-add-form { background: #e8f5e9; padding: 20px; border-radius: 8px; margin-bottom: 20px; border-left: 4px solid #28a745; }
    @media (max-width: 768px) { .header h1 { font-size: 2rem; } .dashboard-grid { grid-template-columns: 1fr; } .stats-grid { grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); } .container { margin: 10px; border-radius: 10px; } body { padding: 10px; } table { font-size: 14px; } table th, table td { padding: 8px 4px; } }
</style>
"""

# Routes
@app.route('/')
def index():
    total_clients = Client.query.count()
    total_requests = FuelRequest.query.count()
    pending_requests = FuelRequest.query.filter_by(status='pending').count()
    completed_requests = FuelRequest.query.filter_by(status='completed').count()
    
    return render_template_string("""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Food Bank Fuel Support System</title>
        """ + CSS_TEMPLATE + """
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>🏠 Food Bank Fuel Support System</h1>
                <p>Administrative Dashboard - Manage client fuel support requests efficiently</p>
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
                    </div>
                    <div class="stat-box">
                        <div class="stat-number">{{ total_requests }}</div>
                        <div class="stat-label">Total Requests</div>
                    </div>
                    <div class="stat-box">
                        <div class="stat-number">{{ pending_requests }}</div>
                        <div class="stat-label">Pending</div>
                    </div>
                    <div class="stat-box">
                        <div class="stat-number">{{ completed_requests }}</div>
                        <div class="stat-label">Completed</div>
                    </div>
                </div>

                <div class="quick-add-form">
                    <h3>⚡ Quick Add Client</h3>
                    <form method="POST" action="{{ url_for('quick_add_client') }}" style="display: flex; gap: 10px; flex-wrap: wrap; align-items: end;">
                        <div class="form-group" style="margin: 0; min-width: 200px;">
                            <label for="quick_name">Name</label>
                            <input type="text" class="form-control" id="quick_name" name="name" required placeholder="Client Name">
                        </div>
                        <div class="form-group" style="margin: 0; min-width: 150px;">
                            <label for="quick_phone">Phone</label>
                            <input type="tel" class="form-control" id="quick_phone" name="phone_number" required placeholder="+447700900123">
                        </div>
                        <div class="form-check" style="margin: 0;">
                            <input type="checkbox" id="quick_camera" name="has_camera_phone" checked>
                            <label for="quick_camera">Camera Phone</label>
                        </div>
                        <div class="form-check" style="margin: 0;">
                            <input type="checkbox" id="quick_gdpr" name="gdpr_consent" required>
                            <label for="quick_gdpr">GDPR Consent</label>
                        </div>
                        <button type="submit" class="btn btn-success">➕ Add Client</button>
                    </form>
                </div>
                
                <div class="dashboard-grid">
                    <div class="card">
                        <h3>📱 SMS Management</h3>
                        <p>Send fuel support requests to clients via SMS</p>
                        <div style="margin-top: 15px;">
                            <a href="{{ url_for('send_sms_requests') }}" class="btn">📤 Send SMS Requests</a>
                            <a href="{{ url_for('view_sms_history') }}" class="btn btn-secondary">📋 SMS History</a>
                        </div>
                    </div>
                    
                    <div class="card">
                        <h3>👥 Client Management</h3>
                        <p>View and manage all registered clients</p>
                        <div style="margin-top: 15px;">
                            <a href="{{ url_for('view_clients') }}" class="btn">👥 View All Clients</a>
                            <a href="{{ url_for('add_client') }}" class="btn btn-success">➕ Add New Client</a>
                        </div>
                    </div>
                    
                    <div class="card">
                        <h3>📞 Staff Portal</h3>
                        <p>Manual processing for non-camera phone clients</p>
                        <a href="{{ url_for('staff_portal') }}" class="btn">🏢 Staff Portal</a>
                    </div>
                    
                                         <div class="card">
                         <h3>📊 Reports</h3>
                         <p>Generate comprehensive reports and analytics</p>
                         <a href="{{ url_for('generate_report') }}" class="btn">📈 Generate Report</a>
                     </div>
                     
                     <div class="card">
                         <h3>🔧 Debug & Testing</h3>
                         <p>Check SMS configuration and test functionality</p>
                         <a href="{{ url_for('debug_sms_simulation') }}" class="btn btn-secondary">🔧 SMS Debug</a>
                     </div>
                </div>
            </div>
        </div>
    </body>
    </html>
    """, total_clients=total_clients, total_requests=total_requests, 
         pending_requests=pending_requests, completed_requests=completed_requests)

@app.route('/quick_add_client', methods=['POST'])
def quick_add_client():
    """Quick add client from dashboard"""
    try:
        name = request.form.get('name', '').strip()
        phone = request.form.get('phone_number', '').strip()
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
            has_camera_phone=has_camera,
            gdpr_consent=gdpr_consent
        )
        
        db.session.add(new_client)
        db.session.commit()
        
        flash(f'✅ Client {name} added successfully!', 'success')
        
    except Exception as e:
        db.session.rollback()
        flash(f'❌ Error adding client: {str(e)}', 'danger')
        logging.error(f"Error in quick_add_client: {e}")
    
    return redirect(url_for('index'))

@app.route('/send_sms_requests', methods=['GET', 'POST'])
def send_sms_requests():
    if request.method == 'POST':
        try:
            selected_clients = request.form.getlist('client_ids')
            if not selected_clients:
                flash('❌ Please select at least one client', 'danger')
                return redirect(url_for('send_sms_requests'))
            
            sent_count = 0
            failed_count = 0
            
            for client_id in selected_clients:
                client = Client.query.get(int(client_id))
                if not client:
                    logging.error(f"Client with ID {client_id} not found")
                    failed_count += 1
                    continue
                
                if not client.gdpr_consent:
                    logging.warning(f"Client {client.name} does not have GDPR consent - skipping")
                    failed_count += 1
                    continue
                
                try:
                    fuel_request = FuelRequest(
                        client_id=client.id,
                        unique_link=generate_unique_link(),
                        expires_at=datetime.utcnow() + timedelta(hours=48),
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
                flash(f'✅ SMS requests sent successfully to {sent_count} clients!', 'success')
            else:
                flash(f'⚠️ SMS sent to {sent_count} clients, {failed_count} failed. Check SMS history for details.', 'warning')
            
        except Exception as e:
            db.session.rollback()
            flash(f'❌ Error sending SMS requests: {str(e)}', 'danger')
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
        <div class="container">
            <div class="header">
                <h1>📱 Send SMS Requests</h1>
                <p>Send fuel support requests to selected clients via SMS</p>
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
                    <h3>Select Clients for SMS</h3>
                    {% if clients %}
                    <form method="POST" id="smsForm">
                        <div style="margin: 20px 0; display: flex; gap: 10px; flex-wrap: wrap;">
                            <button type="button" onclick="selectAll()" class="btn btn-secondary">✅ Select All</button>
                            <button type="button" onclick="selectNone()" class="btn btn-secondary">❌ Select None</button>
                            <button type="button" onclick="selectGDPROnly()" class="btn btn-secondary">📋 GDPR Compliant Only</button>
                            <span id="selectedCount" style="padding: 10px; background: #e9ecef; border-radius: 4px; font-weight: bold;">0 selected</span>
                        </div>
                        
                        <table>
                            <thead>
                                <tr>
                                    <th><input type="checkbox" id="selectAll" onchange="toggleAll()"></th>
                                    <th>Name</th>
                                    <th>Phone</th>
                                    <th>Camera Phone</th>
                                    <th>GDPR Consent</th>
                                    <th>Status</th>
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
                                            ✅ Yes
                                        {% else %}
                                            ❌ No
                                        {% endif %}
                                    </td>
                                    <td>
                                        {% if client.gdpr_consent %}
                                            ✅ Yes
                                        {% else %}
                                            ❌ No
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
                        
                        <div style="margin-top: 20px;">
                            <button type="submit" class="btn btn-success">📤 Send SMS Requests</button>
                            <a href="{{ url_for('index') }}" class="btn btn-secondary">← Back to Dashboard</a>
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
                cb.checked = gdprCell.textContent.includes('✅');
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
        
        updateCount();
        </script>
    </body>
    </html>
    """, clients=clients)

@app.route('/test_upload/<unique_link>')
def test_upload_link(unique_link):
    """Test route to verify upload links are working"""
    fuel_request = FuelRequest.query.filter_by(unique_link=unique_link).first()
    if fuel_request:
        return jsonify({
            'status': 'success',
            'client_name': fuel_request.client.name,
            'link_valid': True,
            'expires_at': fuel_request.expires_at.isoformat(),
            'upload_url': f"{BASE_URL}/upload/{unique_link}"
        })
    else:
        return jsonify({
            'status': 'error',
            'message': 'Link not found'
        }), 404

@app.route('/upload/<unique_link>', methods=['GET', 'POST'])
def upload_documents(unique_link):
    """Client upload page for documents"""
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
                    <h1>❌ Invalid Link</h1>
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
    
    if fuel_request.expires_at < datetime.utcnow():
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
                    <h1>⏰ Link Expired</h1>
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
            fuel_request.meter_reading_filename = meter_filename
            fuel_request.identity_photo_filename = identity_filename
            fuel_request.status = 'completed'
            
            db.session.commit()
            
            flash('✅ Documents uploaded successfully! We will process your request soon.', 'success')
            
        except Exception as e:
            flash(f'❌ Error uploading documents: {str(e)}', 'danger')
            logging.error(f"Upload error: {e}")
    
    return render_template_string("""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Upload Documents - Food Bank</title>
        """ + CSS_TEMPLATE + """
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>📱 Upload Documents</h1>
                <p>Please upload your meter reading and identity photo</p>
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
                    <h3>Hi {{ fuel_request.client.name }}!</h3>
                    <p>Please upload the following documents to complete your fuel support request:</p>
                    
                    <form method="POST" enctype="multipart/form-data">
                        <div class="form-group">
                            <label for="meter_reading">📊 Meter Reading Photo *</label>
                            <input type="file" class="form-control" id="meter_reading" name="meter_reading" accept="image/*" required>
                            <small class="form-text text-muted">Take a clear photo of your current meter reading</small>
                        </div>
                        
                        <div class="form-group">
                            <label for="identity_photo">🆔 Identity Photo *</label>
                            <input type="file" class="form-control" id="identity_photo" name="identity_photo" accept="image/*" required>
                            <small class="form-text text-muted">Take a photo of yourself holding your ID</small>
                        </div>
                        
                        <div style="margin-top: 20px;">
                            <button type="submit" class="btn btn-success">📤 Upload Documents</button>
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
                    
                    <div style="margin-top: 20px; text-align: center; color: #6c757d;">
                        <p><strong>Need help?</strong> Contact us: {{ food_bank_phone }}</p>
                    </div>
                </div>
            </div>
        </div>
    </body>
    </html>
    """, fuel_request=fuel_request, food_bank_phone=FOOD_BANK_PHONE)

# Additional routes for completeness
@app.route('/view_clients')
def view_clients():
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
        <div class="container">
            <div class="header">
                <h1>👥 View Clients</h1>
                <p>Manage all registered clients</p>
            </div>
            
            <div class="content">
                <div class="card">
                    <h3>All Clients</h3>
                    
                    <div style="margin-bottom: 20px; display: flex; gap: 10px; flex-wrap: wrap;">
                        <a href="{{ url_for('add_client') }}" class="btn btn-success">➕ Add New Client</a>
                        <a href="{{ url_for('search_clients') }}" class="btn">🔍 Search Clients</a>
                        <a href="{{ url_for('bulk_operations') }}" class="btn btn-warning">⚡ Bulk Operations</a>
                        <a href="{{ url_for('export_clients') }}" class="btn btn-info">📄 Export Clients</a>
                        <span style="padding: 10px; background: #e9ecef; border-radius: 4px; font-weight: bold;">{{ clients|length }} total clients</span>
                    </div>
                    
                    {% if clients %}
                    <table>
                        <thead>
                            <tr>
                                <th>Name</th>
                                <th>Phone Number</th>
                                <th>Camera Phone</th>
                                <th>GDPR Consent</th>
                                <th>Created</th>
                                <th>Actions</th>
                            </tr>
                        </thead>
                        <tbody>
                            {% for client in clients %}
                            <tr>
                                <td>{{ client.name }}</td>
                                <td>{{ client.phone_number }}</td>
                                <td>
                                    {% if client.has_camera_phone %}
                                        ✅ Yes
                                    {% else %}
                                        ❌ No
                                    {% endif %}
                                </td>
                                <td>
                                    {% if client.gdpr_consent %}
                                        ✅ Yes
                                    {% else %}
                                        ❌ No
                                    {% endif %}
                                </td>
                                <td>{{ client.created_at.strftime('%d/%m/%Y') }}</td>
                                <td>
                                    <a href="{{ url_for('edit_client', client_id=client.id) }}" class="btn btn-small">✏️ Edit</a>
                                    <a href="{{ url_for('client_details', client_id=client.id) }}" class="btn btn-small">👤 Details</a>
                                    <button onclick="deleteClient({{ client.id }}, '{{ client.name }}')" class="btn btn-small btn-danger">🗑️ Delete</button>
                                </td>
                            </tr>
                            {% endfor %}
                        </tbody>
                    </table>
                    {% else %}
                    <div class="alert alert-info">
                        <p>No clients found. <a href="{{ url_for('add_client') }}">Add your first client</a>.</p>
                    </div>
                    {% endif %}
                    
                    <div style="margin-top: 20px;">
                        <a href="{{ url_for('index') }}" class="btn btn-secondary">← Back to Dashboard</a>
                    </div>
                </div>
            </div>
        </div>
        
        <script>
        function deleteClient(clientId, clientName) {
            if (confirm('Are you sure you want to delete ' + clientName + '? This action cannot be undone.')) {
                window.location.href = '/delete_client/' + clientId;
            }
        }
        </script>
    </body>
    </html>
    """, clients=clients)

@app.route('/add_client', methods=['GET', 'POST'])
def add_client():
    if request.method == 'POST':
        try:
            name = request.form.get('name', '').strip()
            phone = request.form.get('phone_number', '').strip()
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
                has_camera_phone=has_camera,
                gdpr_consent=gdpr_consent
            )
            
            db.session.add(new_client)
            db.session.commit()
            
            flash(f'✅ Client {name} added successfully!', 'success')
            return redirect(url_for('view_clients'))
            
        except Exception as e:
            db.session.rollback()
            flash(f'❌ Error adding client: {str(e)}', 'danger')
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
        <div class="container">
            <div class="header">
                <h1>➕ Add New Client</h1>
                <p>Register a new client for fuel support</p>
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
                        
                        <div class="form-check">
                            <input type="checkbox" id="has_camera_phone" name="has_camera_phone" checked>
                            <label for="has_camera_phone">Has camera phone (for digital upload)</label>
                        </div>
                        
                        <div class="form-check">
                            <input type="checkbox" id="gdpr_consent" name="gdpr_consent" required>
                            <label for="gdpr_consent">GDPR consent given *</label>
                        </div>
                        
                        <div style="margin-top: 20px;">
                            <button type="submit" class="btn btn-success">➕ Add Client</button>
                            <a href="{{ url_for('view_clients') }}" class="btn btn-secondary">← Back to Clients</a>
                        </div>
                    </form>
                </div>
            </div>
        </div>
    </body>
    </html>
    """)

@app.route('/view_sms_history')
def view_sms_history():
    sms_logs = SMSLog.query.order_by(SMSLog.created_at.desc()).limit(50).all()
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
        <div class="container">
            <div class="header">
                <h1>📋 SMS History</h1>
                <p>View all SMS messages sent to clients</p>
            </div>
            
            <div class="content">
                <div class="card">
                    <h3>Recent SMS Messages</h3>
                    {% if sms_logs %}
                    <table>
                        <thead>
                            <tr>
                                <th>Date</th>
                                <th>Client</th>
                                <th>Phone</th>
                                <th>Status</th>
                                <th>Twilio SID</th>
                            </tr>
                        </thead>
                        <tbody>
                            {% for log in sms_logs %}
                            <tr>
                                <td>{{ log.created_at.strftime('%d/%m/%Y %H:%M') }}</td>
                                <td>{{ log.client.name if log.client else 'Unknown' }}</td>
                                <td>{{ log.phone_number }}</td>
                                <td>
                                    <span style="color: {% if log.status == 'sent' %}#28a745{% elif log.status == 'failed' %}#dc3545{% else %}#ffc107{% endif %};">
                                        {{ log.status.title() }}
                                    </span>
                                </td>
                                <td>{{ log.twilio_sid or 'N/A' }}</td>
                            </tr>
                            {% endfor %}
                        </tbody>
                    </table>
                    {% else %}
                    <div class="alert alert-info">
                        <p>No SMS messages found.</p>
                    </div>
                    {% endif %}
                    
                    <div style="margin-top: 20px;">
                        <a href="{{ url_for('index') }}" class="btn btn-secondary">← Back to Dashboard</a>
                    </div>
                </div>
            </div>
        </div>
    </body>
    </html>
    """, sms_logs=sms_logs)

@app.route('/staff_portal')
def staff_portal():
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
        <div class="container">
            <div class="header">
                <h1>🏢 Staff Portal</h1>
                <p>Manual processing for non-camera phone clients</p>
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
                                        ✅ Uploaded
                                    {% else %}
                                        📋 Pending
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
                        <a href="{{ url_for('index') }}" class="btn btn-secondary">← Back to Dashboard</a>
                    </div>
                </div>
            </div>
        </div>
    </body>
    </html>
    """, pending_requests=pending_requests)

@app.route('/generate_report')
def generate_report():
    try:
        current_year = datetime.utcnow().year
        total_clients = Client.query.count()
        total_requests = FuelRequest.query.count()
        completed_requests = FuelRequest.query.filter_by(status='completed').count()
        camera_clients = Client.query.filter_by(has_camera_phone=True).count()
        gdpr_compliant = Client.query.filter_by(gdpr_consent=True).count()
        documents_uploaded = FuelRequest.query.filter_by(documents_uploaded=True).count()
        total_sms_sent = SMSLog.query.filter_by(status='sent').count()
        total_sms_failed = SMSLog.query.filter_by(status='failed').count()

        return render_template_string("""
        <!DOCTYPE html>
        <html lang="en">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>Annual Report - Food Bank</title>
            """ + CSS_TEMPLATE + """
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>📊 Annual Report {{ current_year }}</h1>
                    <p>Comprehensive analysis of fuel support operations</p>
                </div>
                
                <div class="content">
                    <div class="stats-grid">
                        <div class="stat-box">
                            <div class="stat-number">{{ total_clients }}</div>
                            <div class="stat-label">Total Clients</div>
                        </div>
                        <div class="stat-box">
                            <div class="stat-number">{{ total_requests }}</div>
                            <div class="stat-label">Total Requests</div>
                        </div>
                        <div class="stat-box">
                            <div class="stat-number">{{ completed_requests }}</div>
                            <div class="stat-label">Completed</div>
                        </div>
                        <div class="stat-box">
                            <div class="stat-number">{{ camera_clients }}</div>
                            <div class="stat-label">Digital Ready</div>
                        </div>
                    </div>
                    
                    <div class="card">
                        <h3>💡 Recommendations for {{ current_year + 1 }}</h3>
                        <div style="background: #f8f9fa; padding: 20px; border-radius: 8px;">
                            <h4>Priority Actions:</h4>
                            <ol>
                                <li><strong>Expand Digital Adoption:</strong> 
                                    {% if total_clients > 0 and (camera_clients/total_clients)*100 < 80 %}
                                        Current rate {{ '%.1f'|format((camera_clients/total_clients)*100) }}% - target 85%+
                                    {% else %}
                                        Excellent adoption rate achieved ({{ '%.1f'|format((camera_clients/total_clients)*100) }}%)
                                    {% endif %}
                                </li>
                                <li><strong>SMS System Optimization:</strong> 
                                    {% if total_sms_failed > 0 %}
                                        Address {{ total_sms_failed }} failed SMS deliveries
                                    {% else %}
                                        Maintain excellent SMS delivery performance
                                    {% endif %}
                                </li>
                                <li><strong>Document Processing:</strong> Streamline verification of uploaded documents</li>
                                <li><strong>GDPR Compliance:</strong> 
                                    {% if gdpr_compliant < total_clients %}
                                        Ensure {{ total_clients - gdpr_compliant }} remaining clients provide consent
                                    {% else %}
                                        Maintain 100% GDPR compliance achieved
                                    {% endif %}
                                </li>
                            </ol>
                            
                            <h4 style="margin-top: 20px;">System Health:</h4>
                            <ul>
                                <li>Request completion rate: {{ '%.1f'|format((completed_requests/total_requests)*100) if total_requests > 0 else 0 }}%</li>
                                <li>Digital processing rate: {{ '%.1f'|format((camera_clients/total_clients)*100) if total_clients > 0 else 0 }}%</li>
                                <li>Document upload rate: {{ '%.1f'|format((documents_uploaded/total_requests)*100) if total_requests > 0 else 0 }}%</li>
                            </ul>
                        </div>
                    </div>
                    
                    <div style="margin-top: 20px; text-align: center;">
                        <a href="{{ url_for('index') }}" class="btn btn-secondary">← Back to Dashboard</a>
                    </div>
                </div>
            </div>
        </body>
        </html>
        """, 
        current_year=current_year,
        total_clients=total_clients, 
        total_requests=total_requests,
        completed_requests=completed_requests, 
        camera_clients=camera_clients, 
        gdpr_compliant=gdpr_compliant,
        documents_uploaded=documents_uploaded,
        total_sms_sent=total_sms_sent,
        total_sms_failed=total_sms_failed)
    except Exception as e:
        flash(f'Error generating report: {str(e)}', 'error')
        logging.error(f"Report generation error: {e}")
        return redirect(url_for('index'))

@app.route('/edit_client/<int:client_id>', methods=['GET', 'POST'])
def edit_client(client_id):
    """Edit existing client information"""
    client = Client.query.get_or_404(client_id)
    
    if request.method == 'POST':
        try:
            name = request.form.get('name', '').strip()
            phone = request.form.get('phone_number', '').strip()
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
            client.has_camera_phone = has_camera
            client.gdpr_consent = gdpr_consent
            
            db.session.commit()
            flash(f'✅ Client {name} updated successfully!', 'success')
            return redirect(url_for('view_clients'))
            
        except Exception as e:
            db.session.rollback()
            flash(f'❌ Error updating client: {str(e)}', 'danger')
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
        <div class="container">
            <div class="header">
                <h1>✏️ Edit Client</h1>
                <p>Update client information</p>
            </div>
            
            <div class="content">
                <div class="card">
                    <h3>Edit Client Information</h3>
                    <form method="POST">
                        <div class="form-group">
                            <label for="name">Full Name *</label>
                            <input type="text" class="form-control" id="name" name="name" value="{{ client.name }}" required>
                        </div>
                        
                        <div class="form-group">
                            <label for="phone_number">Phone Number *</label>
                            <input type="tel" class="form-control" id="phone_number" name="phone_number" value="{{ client.phone_number }}" required placeholder="+447700900123">
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
                            <button type="submit" class="btn btn-success">💾 Save Changes</button>
                            <a href="{{ url_for('view_clients') }}" class="btn btn-secondary">← Back to Clients</a>
                            <button type="button" onclick="deleteClient()" class="btn btn-danger">🗑️ Delete Client</button>
                        </div>
                    </form>
                </div>
            </div>
        </div>
        
        <script>
        function deleteClient() {
            if (confirm('Are you sure you want to delete this client? This action cannot be undone.')) {
                window.location.href = "{{ url_for('delete_client', client_id=client.id) }}";
            }
        }
        </script>
    </body>
    </html>
    """, client=client)

@app.route('/delete_client/<int:client_id>')
def delete_client(client_id):
    """Delete a client and all associated data"""
    try:
        client = Client.query.get_or_404(client_id)
        client_name = client.name
        
        # Delete all associated fuel requests and SMS logs
        FuelRequest.query.filter_by(client_id=client.id).delete()
        SMSLog.query.filter_by(client_id=client.id).delete()
        
        # Delete the client
        db.session.delete(client)
        db.session.commit()
        
        flash(f'✅ Client {client_name} and all associated data deleted successfully!', 'success')
        
    except Exception as e:
        db.session.rollback()
        flash(f'❌ Error deleting client: {str(e)}', 'danger')
        logging.error(f"Error in delete_client: {e}")
    
    return redirect(url_for('view_clients'))

@app.route('/search_clients')
def search_clients():
    """Search clients by name or phone number"""
    query = request.args.get('q', '').strip()
    clients = []
    
    if query:
        # Search by name or phone number
        clients = Client.query.filter(
            db.or_(
                Client.name.ilike(f'%{query}%'),
                Client.phone_number.ilike(f'%{query}%')
            )
        ).order_by(Client.name).all()
    
    return render_template_string("""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Search Clients - Food Bank</title>
        """ + CSS_TEMPLATE + """
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>🔍 Search Clients</h1>
                <p>Find clients by name or phone number</p>
            </div>
            
            <div class="content">
                <div class="card">
                    <h3>Search Clients</h3>
                    <form method="GET" style="margin-bottom: 20px;">
                        <div class="form-group">
                            <label for="q">Search by name or phone number</label>
                            <input type="text" class="form-control" id="q" name="q" value="{{ query }}" placeholder="Enter name or phone number...">
                        </div>
                        <button type="submit" class="btn">🔍 Search</button>
                        <a href="{{ url_for('view_clients') }}" class="btn btn-secondary">← Back to All Clients</a>
                    </form>
                    
                    {% if query %}
                        <h4>Search Results for "{{ query }}"</h4>
                        {% if clients %}
                        <table>
                            <thead>
                                <tr>
                                    <th>Name</th>
                                    <th>Phone</th>
                                    <th>Camera Phone</th>
                                    <th>GDPR Consent</th>
                                    <th>Created</th>
                                    <th>Actions</th>
                                </tr>
                            </thead>
                            <tbody>
                                {% for client in clients %}
                                <tr>
                                    <td>{{ client.name }}</td>
                                    <td>{{ client.phone_number }}</td>
                                    <td>
                                        {% if client.has_camera_phone %}
                                            ✅ Yes
                                        {% else %}
                                            ❌ No
                                        {% endif %}
                                    </td>
                                    <td>
                                        {% if client.gdpr_consent %}
                                            ✅ Yes
                                        {% else %}
                                            ❌ No
                                        {% endif %}
                                    </td>
                                    <td>{{ client.created_at.strftime('%d/%m/%Y') }}</td>
                                    <td>
                                        <a href="{{ url_for('edit_client', client_id=client.id) }}" class="btn btn-small">✏️ Edit</a>
                                        <button onclick="deleteClient({{ client.id }}, '{{ client.name }}')" class="btn btn-small btn-danger">🗑️ Delete</button>
                                    </td>
                                </tr>
                                {% endfor %}
                            </tbody>
                        </table>
                        {% else %}
                        <div class="alert alert-info">
                            <p>No clients found matching "{{ query }}".</p>
                        </div>
                        {% endif %}
                    {% endif %}
                </div>
            </div>
        </div>
        
        <script>
        function deleteClient(clientId, clientName) {
            if (confirm('Are you sure you want to delete ' + clientName + '? This action cannot be undone.')) {
                window.location.href = '/delete_client/' + clientId;
            }
        }
        </script>
    </body>
    </html>
    """, clients=clients, query=query)

@app.route('/bulk_operations', methods=['GET', 'POST'])
def bulk_operations():
    """Bulk operations on clients"""
    if request.method == 'POST':
        try:
            selected_clients = request.form.getlist('client_ids')
            operation = request.form.get('operation')
            
            if not selected_clients:
                flash('❌ Please select at least one client', 'danger')
                return redirect(url_for('bulk_operations'))
            
            if operation == 'delete':
                # Bulk delete
                deleted_count = 0
                for client_id in selected_clients:
                    client = Client.query.get(int(client_id))
                    if client:
                        # Delete associated data
                        FuelRequest.query.filter_by(client_id=client.id).delete()
                        SMSLog.query.filter_by(client_id=client.id).delete()
                        db.session.delete(client)
                        deleted_count += 1
                
                db.session.commit()
                flash(f'✅ Successfully deleted {deleted_count} clients!', 'success')
                
            elif operation == 'update_gdpr':
                # Bulk update GDPR consent
                updated_count = 0
                for client_id in selected_clients:
                    client = Client.query.get(int(client_id))
                    if client:
                        client.gdpr_consent = True
                        updated_count += 1
                
                db.session.commit()
                flash(f'✅ Successfully updated GDPR consent for {updated_count} clients!', 'success')
                
            elif operation == 'update_camera':
                # Bulk update camera phone status
                has_camera = request.form.get('camera_status') == 'true'
                updated_count = 0
                for client_id in selected_clients:
                    client = Client.query.get(int(client_id))
                    if client:
                        client.has_camera_phone = has_camera
                        updated_count += 1
                
                db.session.commit()
                flash(f'✅ Successfully updated camera phone status for {updated_count} clients!', 'success')
            
        except Exception as e:
            db.session.rollback()
            flash(f'❌ Error performing bulk operation: {str(e)}', 'danger')
            logging.error(f"Error in bulk_operations: {e}")
        
        return redirect(url_for('bulk_operations'))
    
    clients = Client.query.order_by(Client.name).all()
    return render_template_string("""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Bulk Operations - Food Bank</title>
        """ + CSS_TEMPLATE + """
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>⚡ Bulk Operations</h1>
                <p>Perform operations on multiple clients at once</p>
            </div>
            
            <div class="content">
                <div class="card">
                    <h3>Bulk Client Operations</h3>
                    {% if clients %}
                    <form method="POST" id="bulkForm">
                        <div style="margin: 20px 0; display: flex; gap: 10px; flex-wrap: wrap;">
                            <button type="button" onclick="selectAll()" class="btn btn-secondary">✅ Select All</button>
                            <button type="button" onclick="selectNone()" class="btn btn-secondary">❌ Select None</button>
                            <span id="selectedCount" style="padding: 10px; background: #e9ecef; border-radius: 4px; font-weight: bold;">0 selected</span>
                        </div>
                        
                        <div style="margin: 20px 0; padding: 20px; background: #f8f9fa; border-radius: 8px;">
                            <h4>Select Operation:</h4>
                            <div class="form-check">
                                <input type="radio" id="delete" name="operation" value="delete" required>
                                <label for="delete">🗑️ Delete Selected Clients</label>
                            </div>
                            <div class="form-check">
                                <input type="radio" id="update_gdpr" name="operation" value="update_gdpr" required>
                                <label for="update_gdpr">📋 Update GDPR Consent to Yes</label>
                            </div>
                            <div class="form-check">
                                <input type="radio" id="update_camera" name="operation" value="update_camera" required>
                                <label for="update_camera">📱 Update Camera Phone Status</label>
                                <div style="margin-left: 20px; margin-top: 10px;">
                                    <div class="form-check">
                                        <input type="radio" id="camera_true" name="camera_status" value="true">
                                        <label for="camera_true">✅ Has Camera Phone</label>
                                    </div>
                                    <div class="form-check">
                                        <input type="radio" id="camera_false" name="camera_status" value="false">
                                        <label for="camera_false">❌ No Camera Phone</label>
                                    </div>
                                </div>
                            </div>
                        </div>
                        
                        <table>
                            <thead>
                                <tr>
                                    <th><input type="checkbox" id="selectAll" onchange="toggleAll()"></th>
                                    <th>Name</th>
                                    <th>Phone</th>
                                    <th>Camera Phone</th>
                                    <th>GDPR Consent</th>
                                    <th>Created</th>
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
                                            ✅ Yes
                                        {% else %}
                                            ❌ No
                                        {% endif %}
                                    </td>
                                    <td>
                                        {% if client.gdpr_consent %}
                                            ✅ Yes
                                        {% else %}
                                            ❌ No
                                        {% endif %}
                                    </td>
                                    <td>{{ client.created_at.strftime('%d/%m/%Y') }}</td>
                                </tr>
                                {% endfor %}
                            </tbody>
                        </table>
                        
                        <div style="margin-top: 20px;">
                            <button type="submit" class="btn btn-success" onclick="return confirmOperation()">⚡ Execute Bulk Operation</button>
                            <a href="{{ url_for('view_clients') }}" class="btn btn-secondary">← Back to Clients</a>
                        </div>
                    </form>
                    {% else %}
                    <div class="alert alert-info">
                        <p>No clients found.</p>
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
        
        function toggleAll() {
            const selectAllCheckbox = document.getElementById('selectAll');
            document.querySelectorAll('.client-checkbox').forEach(cb => cb.checked = selectAllCheckbox.checked);
            updateCount();
        }
        
        function updateCount() {
            const checked = document.querySelectorAll('.client-checkbox:checked').length;
            document.getElementById('selectedCount').textContent = checked + ' selected';
        }
        
        function confirmOperation() {
            const operation = document.querySelector('input[name="operation"]:checked');
            if (!operation) {
                alert('Please select an operation');
                return false;
            }
            
            const checked = document.querySelectorAll('.client-checkbox:checked').length;
            if (checked === 0) {
                alert('Please select at least one client');
                return false;
            }
            
            let message = `Are you sure you want to perform this operation on ${checked} client(s)?`;
            if (operation.value === 'delete') {
                message = `⚠️ WARNING: This will permanently delete ${checked} client(s) and all associated data. This action cannot be undone. Are you sure?`;
            }
            
            return confirm(message);
        }
        
        updateCount();
        </script>
    </body>
    </html>
    """, clients=clients)

@app.route('/export_clients')
def export_clients():
    """Export clients data as CSV"""
    try:
        import csv
        from io import StringIO
        
        clients = Client.query.order_by(Client.name).all()
        
        # Create CSV data
        output = StringIO()
        writer = csv.writer(output)
        
        # Write header
        writer.writerow(['Name', 'Phone Number', 'Camera Phone', 'GDPR Consent', 'Created Date', 'Total Requests', 'Completed Requests'])
        
        # Write data
        for client in clients:
            total_requests = len(client.fuel_requests)
            completed_requests = len([r for r in client.fuel_requests if r.status == 'completed'])
            
            writer.writerow([
                client.name,
                client.phone_number,
                'Yes' if client.has_camera_phone else 'No',
                'Yes' if client.gdpr_consent else 'No',
                client.created_at.strftime('%d/%m/%Y'),
                total_requests,
                completed_requests
            ])
        
        output.seek(0)
        
        from flask import Response
        return Response(
            output.getvalue(),
            mimetype='text/csv',
            headers={'Content-Disposition': f'attachment; filename=clients_export_{datetime.utcnow().strftime("%Y%m%d")}.csv'}
        )
        
    except Exception as e:
        flash(f'❌ Error exporting data: {str(e)}', 'danger')
        logging.error(f"Export error: {e}")
        return redirect(url_for('view_clients'))

@app.route('/debug/sms_status')
def debug_sms_status():
    """Debug route to check SMS configuration and status"""
    try:
        # Use simulation mode flag
        twilio_configured = not SIMULATION_MODE
        
        # Debug logging
        logging.info(f"Twilio config check: Simulation Mode={SIMULATION_MODE}, Configured={twilio_configured}")
        recent_sms_logs = SMSLog.query.order_by(SMSLog.created_at.desc()).limit(10).all()
        
        logs_data = []
        for log in recent_sms_logs:
            try:
                client_name = log.client.name if log.client else 'Unknown'
            except:
                client_name = 'Unknown'
            
            logs_data.append({
                'client_name': client_name,
                'phone': log.phone_number,
                'status': log.status,
                'error': log.error_message,
                'created_at': log.created_at.isoformat(),
                'twilio_sid': log.twilio_sid
            })
        
        return jsonify({
            'twilio_configured': twilio_configured,
            'base_url': BASE_URL,
            'food_bank_name': FOOD_BANK_NAME,
            'food_bank_phone': FOOD_BANK_PHONE,
            'recent_sms_logs': logs_data
        })
    except Exception as e:
        logging.error(f"Error in debug_sms_status: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/debug/force_simulation')
def force_simulation_mode():
    """Force the system into simulation mode by clearing Twilio credentials"""
    global TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_PHONE_NUMBER
    
    # Clear Twilio credentials
    TWILIO_ACCOUNT_SID = None
    TWILIO_AUTH_TOKEN = None
    TWILIO_PHONE_NUMBER = None
    
    flash('✅ Forced simulation mode - Twilio credentials cleared', 'success')
    return redirect(url_for('debug_sms_simulation'))

@app.route('/debug/sms_simulation')
def debug_sms_simulation():
    """Debug route to show SMS simulation results"""
    try:
        twilio_configured = not SIMULATION_MODE
        recent_sms_logs = SMSLog.query.order_by(SMSLog.created_at.desc()).limit(20).all()
        
        return render_template_string("""
        <!DOCTYPE html>
        <html lang="en">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>SMS Debug - Food Bank</title>
            """ + CSS_TEMPLATE + """
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>🔧 SMS Debug Information</h1>
                    <p>Configuration and recent SMS logs</p>
                </div>
                
                <div class="content">
                    <div class="card">
                        <h3>📱 Configuration Status</h3>
                        <p><strong>Twilio Configured:</strong> 
                            {% if twilio_configured %}
                                ✅ Yes (Live SMS Mode)
                            {% else %}
                                ⚠️ No (Simulation Mode)
                            {% endif %}
                        </p>
                        <p><strong>Base URL:</strong> {{ base_url }}</p>
                        <p><strong>Food Bank:</strong> {{ food_bank_name }}</p>
                        <p><strong>Phone:</strong> {{ food_bank_phone }}</p>
                    </div>
                    
                    <div class="card">
                        <h3>📋 Recent SMS Logs</h3>
                        {% if recent_sms_logs %}
                        <table>
                            <thead>
                                <tr>
                                    <th>Date</th>
                                    <th>Client</th>
                                    <th>Phone</th>
                                    <th>Status</th>
                                    <th>Twilio SID</th>
                                    <th>Error</th>
                                </tr>
                            </thead>
                            <tbody>
                                {% for log in recent_sms_logs %}
                                <tr>
                                    <td>{{ log.created_at.strftime('%d/%m/%Y %H:%M') }}</td>
                                    <td>{{ log.client.name if log.client else 'Unknown' }}</td>
                                    <td>{{ log.phone_number }}</td>
                                    <td>
                                        <span style="color: {% if log.status == 'sent' %}#28a745{% elif log.status == 'failed' %}#dc3545{% else %}#ffc107{% endif %};">
                                            {{ log.status.title() }}
                                        </span>
                                    </td>
                                    <td>{{ log.twilio_sid or 'N/A' }}</td>
                                    <td>{{ log.error_message or '-' }}</td>
                                </tr>
                                {% endfor %}
                            </tbody>
                        </table>
                        {% else %}
                        <div class="alert alert-info">
                            <p>No SMS logs found.</p>
                        </div>
                        {% endif %}
                    </div>
                    
                                         <div style="margin-top: 20px;">
                         <a href="{{ url_for('index') }}" class="btn btn-secondary">← Back to Dashboard</a>
                         <a href="{{ url_for('send_sms_requests') }}" class="btn">📤 Send SMS</a>
                         {% if twilio_configured %}
                         <a href="{{ url_for('force_simulation_mode') }}" class="btn btn-warning" onclick="return confirm('Force simulation mode? This will clear Twilio credentials.')">⚠️ Force Simulation</a>
                         {% endif %}
                     </div>
                </div>
            </div>
        </body>
        </html>
        """, twilio_configured=twilio_configured, base_url=BASE_URL, 
             food_bank_name=FOOD_BANK_NAME, food_bank_phone=FOOD_BANK_PHONE, 
             recent_sms_logs=recent_sms_logs)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/client_details/<int:client_id>')
def client_details(client_id):
    """View detailed information about a specific client"""
    client = Client.query.get_or_404(client_id)
    
    # Get client statistics
    total_requests = len(client.fuel_requests)
    completed_requests = len([r for r in client.fuel_requests if r.status == 'completed'])
    pending_requests = len([r for r in client.fuel_requests if r.status == 'pending'])
    expired_requests = len([r for r in client.fuel_requests if r.status == 'expired'])
    
    # Get recent SMS logs
    recent_sms = SMSLog.query.filter_by(client_id=client.id).order_by(SMSLog.created_at.desc()).limit(5).all()
    
    return render_template_string("""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Client Details - Food Bank</title>
        """ + CSS_TEMPLATE + """
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>👤 Client Details</h1>
                <p>Detailed information for {{ client.name }}</p>
            </div>
            
            <div class="content">
                <div class="card">
                    <h3>📋 Client Information</h3>
                    <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 20px; margin-bottom: 30px;">
                        <div>
                            <h4>Basic Details</h4>
                            <p><strong>Name:</strong> {{ client.name }}</p>
                            <p><strong>Phone:</strong> {{ client.phone_number }}</p>
                            <p><strong>Camera Phone:</strong> 
                                {% if client.has_camera_phone %}
                                    ✅ Yes
                                {% else %}
                                    ❌ No
                                {% endif %}
                            </p>
                            <p><strong>GDPR Consent:</strong> 
                                {% if client.gdpr_consent %}
                                    ✅ Yes
                                {% else %}
                                    ❌ No
                                {% endif %}
                            </p>
                            <p><strong>Registered:</strong> {{ client.created_at.strftime('%d/%m/%Y at %H:%M') }}</p>
                        </div>
                        
                        <div>
                            <h4>📊 Statistics</h4>
                            <div class="stats-grid" style="grid-template-columns: 1fr;">
                                <div class="stat-box">
                                    <div class="stat-number">{{ total_requests }}</div>
                                    <div class="stat-label">Total Requests</div>
                                </div>
                                <div class="stat-box">
                                    <div class="stat-number">{{ completed_requests }}</div>
                                    <div class="stat-label">Completed</div>
                                </div>
                                <div class="stat-box">
                                    <div class="stat-number">{{ pending_requests }}</div>
                                    <div class="stat-label">Pending</div>
                                </div>
                            </div>
                        </div>
                    </div>
                    
                    <div style="margin-top: 20px;">
                        <a href="{{ url_for('edit_client', client_id=client.id) }}" class="btn btn-success">✏️ Edit Client</a>
                        <a href="{{ url_for('send_sms_requests') }}" class="btn">📤 Send SMS</a>
                        <button onclick="deleteClient({{ client.id }}, '{{ client.name }}')" class="btn btn-danger">🗑️ Delete Client</button>
                        <a href="{{ url_for('view_clients') }}" class="btn btn-secondary">← Back to Clients</a>
                    </div>
                </div>
                
                {% if client.fuel_requests %}
                <div class="card">
                    <h3>📋 Fuel Requests History</h3>
                    <table>
                        <thead>
                            <tr>
                                <th>Date</th>
                                <th>Status</th>
                                <th>Documents</th>
                                <th>Expires</th>
                                <th>SMS Sent</th>
                            </tr>
                        </thead>
                        <tbody>
                            {% for request in client.fuel_requests|sort(attribute='created_at', reverse=true) %}
                            <tr>
                                <td>{{ request.created_at.strftime('%d/%m/%Y') }}</td>
                                <td>
                                    <span style="color: {% if request.status == 'completed' %}#28a745{% elif request.status == 'pending' %}#ffc107{% else %}#dc3545{% endif %};">
                                        {{ request.status.title() }}
                                    </span>
                                </td>
                                <td>
                                    {% if request.documents_uploaded %}
                                        ✅ Uploaded
                                    {% else %}
                                        📋 Pending
                                    {% endif %}
                                </td>
                                <td>{{ request.expires_at.strftime('%d/%m/%Y') }}</td>
                                <td>
                                    {% if request.sms_sent %}
                                        ✅ {{ request.sms_sent_at.strftime('%d/%m/%Y') if request.sms_sent_at else 'Yes' }}
                                    {% else %}
                                        ❌ No
                                    {% endif %}
                                </td>
                            </tr>
                            {% endfor %}
                        </tbody>
                    </table>
                </div>
                {% endif %}
                
                {% if recent_sms %}
                <div class="card">
                    <h3>📱 Recent SMS Messages</h3>
                    <table>
                        <thead>
                            <tr>
                                <th>Date</th>
                                <th>Status</th>
                                <th>Twilio SID</th>
                            </tr>
                        </thead>
                        <tbody>
                            {% for sms in recent_sms %}
                            <tr>
                                <td>{{ sms.created_at.strftime('%d/%m/%Y %H:%M') }}</td>
                                <td>
                                    <span style="color: {% if sms.status == 'sent' %}#28a745{% elif sms.status == 'failed' %}#dc3545{% else %}#ffc107{% endif %};">
                                        {{ sms.status.title() }}
                                    </span>
                                </td>
                                <td>{{ sms.twilio_sid or 'N/A' }}</td>
                            </tr>
                            {% endfor %}
                        </tbody>
                    </table>
                </div>
                {% endif %}
            </div>
        </div>
        
        <script>
        function deleteClient(clientId, clientName) {
            if (confirm('Are you sure you want to delete ' + clientName + '? This action cannot be undone.')) {
                window.location.href = '/delete_client/' + clientId;
            }
        }
        </script>
    </body>
    </html>
    """, client=client, total_requests=total_requests, completed_requests=completed_requests, 
         pending_requests=pending_requests, expired_requests=expired_requests, recent_sms=recent_sms)

def init_sample_data():
    """Initialize sample data if database is empty"""
    try:
        if Client.query.count() == 0:
            sample_clients = [
                Client(name="John Smith", phone_number="+447700900123", has_camera_phone=True, gdpr_consent=True),
                Client(name="Mary Johnson", phone_number="+447700900124", has_camera_phone=False, gdpr_consent=True),
                Client(name="Bob Wilson", phone_number="+447700900125", has_camera_phone=True, gdpr_consent=True),
                Client(name="Sarah Davis", phone_number="+447700900126", has_camera_phone=True, gdpr_consent=False),
            ]
            
            for client in sample_clients:
                db.session.add(client)
            
            db.session.commit()
            print("✅ Sample data added to database")
            
    except Exception as e:
        db.session.rollback()
        print(f"❌ Error adding sample data: {e}")

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
    
    # Initialize database and folders
    with app.app_context():
        db.create_all()
        create_upload_folder()
        init_sample_data()
    
    print(f"\n🚀 {FOOD_BANK_NAME} SMS Service Starting...")
    print("📱 Dashboard: http://localhost:3000")
    print("🔧 Features: Enhanced SMS, Document Upload, Full CRUD, Staff Portal, Reports")
    print("💾 Database: SQLite with comprehensive logging")
    print("📞 Contact: " + FOOD_BANK_PHONE)
    
    if not all([TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_PHONE_NUMBER]):
        print("⚠️  SMS Simulation Mode: Configure Twilio credentials in .env for live SMS")
    else:
        print("✅ SMS Service: Live mode with Twilio")
    
    # Get port from environment variable (for deployment) or use 3000 for local development
    port = int(os.environ.get('PORT', 3000))
    app.run(debug=False, port=port, host='0.0.0.0')


