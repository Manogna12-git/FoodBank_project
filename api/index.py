import sys
import os

# Add the parent directory to the Python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from foodbank_app import app

# Vercel serverless handler - export the Flask app directly
app.debug = False
