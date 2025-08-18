#!/usr/bin/env python3
"""
Food Bank SMS System - Deployment Helper
"""

import os
import sys
import subprocess
import webbrowser

def print_banner():
    print("🚀 Food Bank SMS System - Deployment Helper")
    print("=" * 50)

def check_requirements():
    """Check if all required files exist"""
    required_files = [
        'foodbank_app.py',
        'requirements.txt',
        'vercel.json'
    ]
    
    missing_files = []
    for file in required_files:
        if not os.path.exists(file):
            missing_files.append(file)
    
    if missing_files:
        print(f"❌ Missing required files: {', '.join(missing_files)}")
        return False
    
    print("✅ All required files found")
    return True

def show_deployment_options():
    """Show deployment options"""
    print("\n📋 Choose Your Deployment Platform:")
    print("1. Vercel (Recommended - Fastest & Free)")
    print("2. Railway (Alternative)")
    print("3. Render (Alternative)")
    print("4. Exit")
    
    choice = input("\nEnter your choice (1-4): ").strip()
    
    if choice == "1":
        deploy_vercel()
    elif choice == "2":
        deploy_railway()
    elif choice == "3":
        deploy_render()
    elif choice == "4":
        print("👋 Goodbye!")
        sys.exit(0)
    else:
        print("❌ Invalid choice. Please try again.")
        show_deployment_options()

def deploy_vercel():
    """Guide through Vercel deployment"""
    print("\n⚡ Vercel Deployment Guide")
    print("=" * 30)
    
    print("\n📋 Prerequisites:")
    print("1. Create a GitHub repository")
    print("2. Push your code to GitHub")
    
    print("\n📋 Steps to Deploy:")
    print("1. Go to https://vercel.com")
    print("2. Sign up/Login with your GitHub account")
    print("3. Click 'New Project'")
    print("4. Import your GitHub repository")
    print("5. Configure settings:")
    print("   - Framework Preset: Other")
    print("   - Build Command: pip install -r requirements.txt")
    print("   - Output Directory: Leave empty")
    print("   - Install Command: Leave empty")
    print("6. Add Environment Variables")
    print("7. Click 'Deploy'")
    
    print("\n🔧 Environment Variables to Add:")
    print("SECRET_KEY=your-secret-key-here")
    print("FOOD_BANK_NAME=Lewisham Food Bank")
    print("FOOD_BANK_PHONE=020-XXXX-XXXX")
    print("BASE_URL=https://your-app-name.vercel.app")
    
    print("\n🌐 After deployment, your app will be available at:")
    print("https://your-app-name.vercel.app")
    
    print("\n🚀 Benefits of Vercel:")
    print("- Free tier with generous limits")
    print("- Automatic HTTPS and CDN")
    print("- Fast global deployment")
    print("- Easy GitHub integration")
    
    open_vercel = input("\nWould you like to open Vercel now? (y/n): ").lower()
    if open_vercel == 'y':
        webbrowser.open('https://vercel.com')

def deploy_railway():
    """Guide through Railway deployment"""
    print("\n🚂 Railway Deployment Guide")
    print("=" * 30)
    
    print("\n📋 Steps to Deploy:")
    print("1. Go to https://railway.app")
    print("2. Sign up with your GitHub account")
    print("3. Click 'New Project'")
    print("4. Select 'Deploy from GitHub repo'")
    print("5. Choose this repository")
    print("6. Wait for deployment to complete")
    
    print("\n🔧 Environment Variables to Add:")
    print("SECRET_KEY=your-secret-key-here")
    print("FOOD_BANK_NAME=Lewisham Food Bank")
    print("FOOD_BANK_PHONE=020-XXXX-XXXX")
    print("BASE_URL=https://your-app-name.railway.app")
    
    print("\n🌐 After deployment, your app will be available at:")
    print("https://your-app-name.railway.app")
    
    open_railway = input("\nWould you like to open Railway now? (y/n): ").lower()
    if open_railway == 'y':
        webbrowser.open('https://railway.app')

def deploy_render():
    """Guide through Render deployment"""
    print("\n🎨 Render Deployment Guide")
    print("=" * 30)
    
    print("\n📋 Steps to Deploy:")
    print("1. Go to https://render.com")
    print("2. Sign up with your GitHub account")
    print("3. Click 'New Web Service'")
    print("4. Connect your GitHub repository")
    print("5. Configure settings:")
    print("   - Build Command: pip install -r requirements.txt")
    print("   - Start Command: python foodbank_app.py")
    print("6. Add environment variables")
    print("7. Deploy")
    
    print("\n🔧 Environment Variables to Add:")
    print("SECRET_KEY=your-secret-key-here")
    print("FOOD_BANK_NAME=Lewisham Food Bank")
    print("FOOD_BANK_PHONE=020-XXXX-XXXX")
    print("BASE_URL=https://your-app-name.onrender.com")
    
    open_render = input("\nWould you like to open Render now? (y/n): ").lower()
    if open_render == 'y':
        webbrowser.open('https://render.com')

def main():
    print_banner()
    
    if not check_requirements():
        print("\n❌ Please ensure all required files are present before deploying.")
        sys.exit(1)
    
    print("\n✅ Your Food Bank SMS System is ready for deployment!")
    print("📱 All features will work including:")
    print("   - SMS simulation (no cost)")
    print("   - Photo upload system")
    print("   - Client management")
    print("   - Staff portal")
    print("   - Reports generation")
    
    show_deployment_options()

if __name__ == "__main__":
    main()
