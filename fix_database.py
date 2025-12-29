#!/usr/bin/env python3
"""
Complete Database Fix Script for Lewisham Food Bank
This script will completely fix the database schema
"""

import sqlite3
import os

def fix_database():
    """Fix the database schema completely"""
    db_path = os.path.join('instance', 'foodbank.db')
    
    if not os.path.exists(db_path):
        print("❌ Database file not found at:", db_path)
        return False
    
    try:
        # Connect to the database
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        print("🔍 Checking and fixing database schema...")
        
        # Check existing columns
        cursor.execute("PRAGMA table_info(client)")
        client_columns = [column[1] for column in cursor.fetchall()]
        print(f"📋 Existing client columns: {client_columns}")
        
        cursor.execute("PRAGMA table_info(fuel_request)")
        fuel_request_columns = [column[1] for column in cursor.fetchall()]
        print(f"📋 Existing fuel_request columns: {fuel_request_columns}")
        
        # Add missing columns to client table
        if 'referrer_name' not in client_columns:
            print("➕ Adding referrer_name column to client table...")
            cursor.execute("ALTER TABLE client ADD COLUMN referrer_name VARCHAR(100)")
        
        if 'referrer_email' not in client_columns:
            print("➕ Adding referrer_email column to client table...")
            cursor.execute("ALTER TABLE client ADD COLUMN referrer_email VARCHAR(100)")
        
        # Add missing columns to fuel_request table
        missing_columns = [
            ('meter_reading_text', 'TEXT'),
            ('id_type', 'VARCHAR(50)'),
            ('id_details', 'TEXT'),
            ('client_postcode', 'VARCHAR(20)'),
            ('missing_documents_reason', 'TEXT'),
            ('staff_notes', 'TEXT')
        ]
        
        for column_name, column_type in missing_columns:
            if column_name not in fuel_request_columns:
                print(f"➕ Adding {column_name} column to fuel_request table...")
                cursor.execute(f"ALTER TABLE fuel_request ADD COLUMN {column_name} {column_type}")
        
        # Commit changes
        conn.commit()
        
        # Verify the changes
        cursor.execute("PRAGMA table_info(client)")
        updated_client_columns = [column[1] for column in cursor.fetchall()]
        print(f"✅ Updated client columns: {updated_client_columns}")
        
        cursor.execute("PRAGMA table_info(fuel_request)")
        updated_fuel_request_columns = [column[1] for column in cursor.fetchall()]
        print(f"✅ Updated fuel_request columns: {updated_fuel_request_columns}")
        
        conn.close()
        print("🎉 Database schema fixed successfully!")
        return True
        
    except Exception as e:
        print(f"❌ Error fixing database: {e}")
        return False

if __name__ == "__main__":
    print("🚀 Starting Lewisham Food Bank Database Fix...")
    success = fix_database()
    if success:
        print("✅ Database fix completed successfully!")
    else:
        print("❌ Database fix failed!")

