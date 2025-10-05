#!/usr/bin/env python3
"""
Simple authentication test for Parliament API
"""

import requests
import json

def test_authentication():
    """Test authentication with the Parliament API"""
    
    base_url = "http://localhost:8000"
    admin_token = "***REMOVED_SECRET***"
    
    print("🔐 Testing Parliament API Authentication")
    print("=" * 50)
    
    # Test without authentication
    print("\n1. Testing without authentication...")
    response = requests.get(f"{base_url}/api/debates/statistics/")
    print(f"   Status: {response.status_code}")
    if response.status_code == 401:
        print("   ✅ Authentication required (as expected)")
    elif response.status_code == 200:
        print("   ⚠️  Endpoint accessible without auth (unexpected)")
    else:
        print(f"   ❌ Unexpected status: {response.status_code}")
    
    # Test with authentication
    print("\n2. Testing with authentication...")
    headers = {
        'Authorization': f'Token {admin_token}',
        'Content-Type': 'application/json'
    }
    
    response = requests.get(f"{base_url}/api/debates/statistics/", headers=headers)
    print(f"   Status: {response.status_code}")
    if response.status_code == 200:
        print("   ✅ Authentication successful")
        data = response.json()
        print(f"   📊 Response: {json.dumps(data, indent=2)}")
    elif response.status_code == 401:
        print("   ❌ Authentication failed - token may be invalid")
    else:
        print(f"   ❌ Unexpected status: {response.status_code}")
    
    # Test admin endpoint
    print("\n3. Testing admin endpoint...")
    response = requests.get(f"{base_url}/api/debates/scraping-status/", headers=headers)
    print(f"   Status: {response.status_code}")
    if response.status_code == 200:
        print("   ✅ Admin endpoint accessible")
        data = response.json()
        print(f"   📊 Active jobs: {len(data.get('active_jobs', []))}")
    else:
        print(f"   ❌ Admin endpoint failed: {response.status_code}")
    
    print("\n" + "=" * 50)
    print("✅ Authentication test completed")

if __name__ == "__main__":
    test_authentication()
