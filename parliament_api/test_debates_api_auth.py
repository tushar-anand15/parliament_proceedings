#!/usr/bin/env python3
"""
Test script for the Debates API endpoints with authentication

Key API Behavior:
1. External Sansad.in API:
   - Session numbers use Roman numerals (e.g., 'I', 'II', 'V')
   - Dates format: dd/mm/yyyy for listing, m/d/yyyy for debate queries
   - Returns JSON with 'pdfUrl' key: {"pdfUrl": "https://..."}
   
2. Our Django API:
   - Session numbers use numeric format (e.g., '1', '2', '5')
   - Converts to Roman numerals internally when calling Sansad.in
   - Dates format: YYYY-MM-DD for API input
   - Caches session dates (refreshes if >10 days old)
   - Stores debate info with proper PDF URLs
"""

import requests
import json
import time
from datetime import datetime
import sys

# Base URL for the API
BASE_URL = "http://localhost:8000/api/debates"

# Authentication credentials
USERNAME = "tushar"
PASSWORD = "anand123"
TOKEN = None  # Will be set if using token auth

# Session for maintaining auth
session = requests.Session()

def setup_auth(use_token=True):
    """Setup authentication for API requests"""
    global TOKEN, session
    
    if use_token:
        # Get token first
        print("🔐 Getting authentication token...")
        response = requests.post('http://localhost:8000/api/auth/login/', json={
            'username': USERNAME,
            'password': PASSWORD
        })
        
        if response.status_code == 200:
            TOKEN = response.json().get('token')
            print(f"✅ Got token: {TOKEN[:20]}...")
            
            # Set token in session headers
            session.headers.update({
                'Authorization': f'Token {TOKEN}'
            })
        else:
            print("❌ Failed to get token, trying basic auth...")
            session.auth = (USERNAME, PASSWORD)
    else:
        # Use basic auth
        print("🔐 Using basic authentication...")
        session.auth = (USERNAME, PASSWORD)

def print_response(response, title):
    """Pretty print API response"""
    print(f"\n{'='*60}")
    print(f"{title}")
    print(f"{'='*60}")
    print(f"Status Code: {response.status_code}")
    
    if response.status_code == 401:
        print("❌ Authentication failed! Make sure to create the user first.")
        print("   Run: python create_test_user.py")
    
    try:
        data = response.json()
        print(json.dumps(data, indent=2))
    except:
        print(response.text)
    print(f"{'='*60}\n")

def test_debate_statistics():
    """Test the debate statistics endpoint"""
    print("\n🔍 Testing Debate Statistics Endpoint...")
    
    # Test overall statistics
    response = session.get(f"{BASE_URL}/statistics/")
    print_response(response, "Overall Debate Statistics")
    
    # Test statistics for specific Lok Sabha
    response = session.get(f"{BASE_URL}/statistics/?loksabha=18")
    print_response(response, "18th Lok Sabha Debate Statistics")

def test_list_debates():
    """Test listing debates"""
    print("\n📋 Testing List Debates Endpoint...")
    
    # List all debates
    response = session.get(f"{BASE_URL}/")
    print_response(response, "List All Debates")
    
    # Get available sessions to use real session number
    available = get_available_sessions()
    if '18' in available and available['18']:
        session_no = available['18'][0]['session']
        print(f"\n📌 Using real session number: {session_no}")
        print(f"   Note: External API uses Roman numerals (e.g., 'I') but our Django API accepts numeric (e.g., '1')")
    else:
        session_no = '1'  # fallback to session 1
        print(f"\n📌 Using default session number: {session_no}")
    
    # List debates with filters
    response = session.get(f"{BASE_URL}/?loksabha=18&session={session_no}")
    print_response(response, f"List Debates for 18th LS Session {session_no}")

def test_search_debates():
    """Test searching debates"""
    print("\n🔎 Testing Search Debates Endpoint...")
    
    # Search debates
    response = session.get(f"{BASE_URL}/search/?loksabha=18&year=2024")
    print_response(response, "Search Debates for 18th LS in 2024")

def test_scraping_status():
    """Test the scraping status endpoint"""
    print("\n📊 Testing Scraping Status Endpoint...")
    
    response = session.get(f"{BASE_URL}/scraping-status/")
    print_response(response, "Debate Scraping Status")

def get_available_sessions():
    """Get available sessions from the API"""
    print("\n📅 Checking available sessions...")
    
    url = "https://sansad.in/api_ls/business/AllLoksabhaAndSessionDates"
    headers = {
        'Accept': 'application/json, text/plain, */*',
        'Accept-Language': 'en-US,en;q=0.9',
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36'
    }
    
    try:
        response = requests.get(url, headers=headers, timeout=30)
        data = response.json()
        
        available = {}
        for ls_data in data:
            ls_no = str(ls_data.get('loksabha'))
            available[ls_no] = []
            for session in ls_data.get('sessions', []):
                session_no = str(session.get('sessionNo'))
                dates = session.get('dates', [])
                if dates:
                    available[ls_no].append({
                        'session': session_no,
                        'dates': dates,
                        'first_date': dates[0],
                        'last_date': dates[-1],
                        'count': len(dates)
                    })
        
        return available
    except Exception as e:
        print(f"❌ Failed to fetch available sessions: {e}")
        return {}

def test_start_scraping():
    """Test starting debate scraping"""
    print("\n🚀 Testing Start Scraping Endpoint...")
    
    # Get available sessions first
    available = get_available_sessions()
    
    # Look for 18th Lok Sabha sessions
    if '18' in available and available['18']:
        print(f"\n📋 Available sessions for 18th Lok Sabha:")
        for sess in available['18']:
            print(f"   Session {sess['session']}: {sess['count']} dates ({sess['first_date']} to {sess['last_date']})")
        
        # Use the first available session
        test_session = available['18'][0]
        print(f"\n✅ Using Session {test_session['session']} for testing")
        print(f"   Note: Our Django API uses numeric session numbers (e.g., '1') but converts to Roman internally (e.g., 'I')")
        
        # Show sample dates
        sample_dates = test_session['dates'][:5] if len(test_session['dates']) > 5 else test_session['dates']
        print(f"   Sample dates: {', '.join(sample_dates)}")
    else:
        print("❌ No sessions found for 18th Lok Sabha, using default")
        test_session = {'session': '1'}  # Use session 1 as default
    
    # Start scraping for the available session
    payload = {
        "loksabha_no": "18",
        "session_no": test_session['session'],  # Django API expects numeric, converts to Roman internally
        "download_pdfs": False,  # Skip PDF downloads for testing
        "job_name": "Test Debate Scraping",
        # Dates should be in YYYY-MM-DD format for the API
        "start_date": datetime.strptime(test_session['first_date'], '%d/%m/%Y').strftime('%Y-%m-%d') if 'first_date' in test_session else None,
        "end_date": datetime.strptime(test_session['dates'][2], '%d/%m/%Y').strftime('%Y-%m-%d') if 'dates' in test_session and len(test_session['dates']) > 2 else None  # Only first 3 dates for testing
    }
    
    # Remove None values
    payload = {k: v for k, v in payload.items() if v is not None}
    
    response = session.post(f"{BASE_URL}/start-scraping/", json=payload)
    print_response(response, "Start Debate Scraping")
    
    if response.status_code == 200:
        data = response.json()
        job_id = data.get('job_id')
        print(f"✅ Scraping job started with ID: {job_id}")
        
        # Wait a bit and check status
        print("\n⏳ Waiting 5 seconds before checking status...")
        time.sleep(5)
        
        # Check status again
        response = session.get(f"{BASE_URL}/scraping-status/")
        print_response(response, "Updated Scraping Status")
        
        return job_id
    
    return None

def test_download_queue():
    """Test the download queue endpoint"""
    print("\n📥 Testing Download Queue Endpoint...")
    
    response = session.get(f"{BASE_URL}/download-queue/")
    print_response(response, "Debate Download Queue Status")

def test_bulk_download():
    """Test bulk download endpoint"""
    print("\n📦 Testing Bulk Download Endpoint...")
    
    # Test downloading all pending debates
    payload = {
        "download_all_pending": True
    }
    
    response = session.post(f"{BASE_URL}/bulk-download/", json=payload)
    print_response(response, "Bulk Download All Pending Debates")

def test_auth_methods():
    """Test different authentication methods"""
    print("\n🔐 Testing Authentication Methods...")
    
    # Test without auth
    print("\n1. Testing without authentication:")
    response = requests.get(f"{BASE_URL}/")
    print(f"   Status: {response.status_code}")
    
    # Test with basic auth
    print("\n2. Testing with basic auth:")
    response = requests.get(f"{BASE_URL}/", auth=(USERNAME, PASSWORD))
    print(f"   Status: {response.status_code}")
    
    # Test with token auth
    if TOKEN:
        print("\n3. Testing with token auth:")
        response = requests.get(f"{BASE_URL}/", headers={'Authorization': f'Token {TOKEN}'})
        print(f"   Status: {response.status_code}")

def test_debate_details():
    """Test getting specific debate details after scraping"""
    print("\n🔍 Testing Debate Details...")
    
    # First check if we have any debates
    response = session.get(f"{BASE_URL}/?loksabha=18&limit=1")
    if response.status_code == 200 and response.json().get('debates'):
        debate = response.json()['debates'][0]
        print(f"\n📄 Found debate: {debate.get('debate_id')}")
        print(f"   Date: {debate.get('debate_date')}")
        print(f"   PDF URL: {debate.get('pdf_url')}")
        print(f"   Downloaded: {debate.get('is_downloaded')}")
        
        # Check if PDF URL is in correct format
        if debate.get('pdf_url'):
            if debate['pdf_url'].startswith('https://sansad.in/getFile/debatestextmk/'):
                print("   ✅ PDF URL format is correct!")
            else:
                print("   ⚠️  PDF URL format might be incorrect")
    else:
        print("   ℹ️  No debates found yet. Run scraping first.")

def main():
    """Run all tests"""
    print("🏛️  Parliament Debates API Test Suite (with Authentication)")
    print(f"📍 Testing against: {BASE_URL}")
    print(f"👤 Username: {USERNAME}")
    print(f"🕐 Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # Show available sessions upfront
    print("\n📊 Checking available Lok Sabha sessions...")
    available = get_available_sessions()
    if available:
        for ls_no in sorted(available.keys(), reverse=True)[:3]:  # Show latest 3 Lok Sabhas
            if available[ls_no]:
                print(f"\n{ls_no}th Lok Sabha:")
                for sess in available[ls_no][:3]:  # Show first 3 sessions
                    print(f"  Session {sess['session']}: {sess['count']} dates ({sess['first_date']} to {sess['last_date']})")
    
    # Setup authentication
    use_token = '--basic' not in sys.argv
    setup_auth(use_token=use_token)
    
    # Test authentication methods
    test_auth_methods()
    
    # Test endpoints in order
    test_debate_statistics()
    test_list_debates()
    test_search_debates()
    test_scraping_status()
    test_download_queue()
    test_debate_details()  # Check debate details format
    
    # Test starting a scraping job (optional)
    print("\n⚠️  The next test will start an actual scraping job.")
    user_input = input("Do you want to start a test scraping job? (y/N): ")
    
    if user_input.lower() == 'y':
        job_id = test_start_scraping()
        
        if job_id:
            print(f"\n💡 To stop the scraping job, use the scraper API:")
            print(f"   POST http://localhost:8000/api/scraper/stop/")
            print(f"   Body: {{'job_id': {job_id}}}")
            
            # Wait and check debate details again
            print("\n⏳ Waiting 10 seconds for scraping to process some debates...")
            time.sleep(10)
            test_debate_details()  # Check again after scraping
    else:
        print("⏭️  Skipping scraping test")
    
    # Test bulk download (optional)
    print("\n⚠️  The next test will queue all pending debates for download.")
    user_input = input("Do you want to test bulk download? (y/N): ")
    
    if user_input.lower() == 'y':
        test_bulk_download()
    else:
        print("⏭️  Skipping bulk download test")
    
    print(f"\n✅ Test suite completed at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

if __name__ == "__main__":
    main()
