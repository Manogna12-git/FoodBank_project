#!/usr/bin/env python3
"""
Database Migration Script for Lewisham Food Bank
This script adds the new columns to the existing database
"""

import sqlite3
import os

def migrate_database():
    """Add new columns to existing database"""
    db_path = os.path.join('instance', 'foodbank.db')
    
    if not os.path.exists(db_path):
        print("❌ Database file not found at:", db_path)
        return False
    
    try:
        # Connect to the database
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        print("🔍 Checking existing database schema...")
        
        # Check if new columns already exist
        cursor.execute("PRAGMA table_info(client)")
        client_columns = [column[1] for column in cursor.fetchall()]
        
        cursor.execute("PRAGMA table_info(fuel_request)")
        fuel_request_columns = [column[1] for column in cursor.fetchall()]
        
        print(f"📋 Existing client columns: {client_columns}")
        print(f"📋 Existing fuel_request columns: {fuel_request_columns}")
        
        # Add missing columns to client table
        if 'referrer_name' not in client_columns:
            print("➕ Adding referrer_name column to client table...")
            cursor.execute("ALTER TABLE client ADD COLUMN referrer_name VARCHAR(100)")
        
        if 'referrer_email' not in client_columns:
            print("➕ Adding referrer_email column to client table...")
            cursor.execute("ALTER TABLE client ADD COLUMN referrer_email VARCHAR(100)")
        
        # Add missing columns to fuel_request table
        new_fuel_request_columns = [
            ('meter_reading_text', 'TEXT'),
            ('id_type', 'VARCHAR(50)'),
            ('id_details', 'TEXT'),
            ('client_postcode', 'VARCHAR(20)'),
            ('missing_documents_reason', 'TEXT'),
            ('staff_notes', 'TEXT')
        ]
        
        for column_name, column_type in new_fuel_request_columns:
            if column_name not in fuel_request_columns:
                print(f"➕ Adding {column_name} column to fuel_request table...")
                cursor.execute(f"ALTER TABLE fuel_request ADD COLUMN {column_name} {column_type}")
        
        # Commit changes
        conn.commit()
        conn.close()
        
        print("✅ Database migration completed successfully!")
        print("🎉 All new columns have been added to the database.")
        return True
        
    except Exception as e:
        print(f"❌ Migration failed: {e}")
        if 'conn' in locals():
            conn.rollback()
            conn.close()
        return False

if __name__ == "__main__":
    print("🚀 Starting Lewisham Food Bank Database Migration...")
    print("=" * 50)
    
    success = migrate_database()
    
    if success:
        print("=" * 50)
        print("🎉 Migration completed! You can now run the application.")
        print("Run: python FoodBank_Testing.py")
    else:
        print("=" * 50)
        print("❌ Migration failed. Please check the error messages above.")

