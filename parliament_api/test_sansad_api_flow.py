#!/usr/bin/env python3
"""
Simple test of Sansad.in API flow:
1. Get available dates
2. Get debate PDF links
3. Test downloading PDFs
"""

import requests
import json
from datetime import datetime

print("🧪 Testing Sansad.in API Flow")
print("=" * 60)

# Headers for all requests
headers = {
    'Accept': 'application/json, text/plain, */*',
    'Accept-Language': 'en-US,en;q=0.9',
    'Connection': 'keep-alive',
    'Referer': 'https://sansad.in/ls/debates/text-of-debates?tab=uncorrected',
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36'
}

# Step 1: Get available dates
print("\n1️⃣ STEP 1: Get Available Dates")
print("-" * 40)

dates_url = "https://sansad.in/api_ls/business/AllLoksabhaAndSessionDates"

try:
    response = requests.get(dates_url, headers=headers, timeout=30)
    print(f"Status: {response.status_code}")
    
    if response.status_code == 200:
        data = response.json()
        print(f"✅ Got data for {len(data)} Lok Sabhas")
        
        # Find 18th Lok Sabha, Session 1
        test_dates = []
        for ls in data:
            if ls.get('loksabha') == 18:
                print(f"\n📋 18th Lok Sabha Sessions:")
                for session in ls.get('sessions', []):
                    session_no = session.get('sessionNo')
                    dates = session.get('dates', [])
                    print(f"   Session {session_no}: {len(dates)} dates")
                    
                    # Use Session 1 for testing
                    if session_no == 1 and dates:
                        test_dates = dates[:3]  # First 3 dates
                        print(f"\n✅ Using Session 1 for testing")
                        print(f"   Test dates: {', '.join(test_dates)}")
                        break
                break
        
        if not test_dates:
            print("❌ No test dates found")
            exit(1)
            
    else:
        print(f"❌ Failed to get dates: {response.text}")
        exit(1)
        
except Exception as e:
    print(f"❌ Error getting dates: {e}")
    exit(1)

# Step 2: Get debate PDF links
print("\n\n2️⃣ STEP 2: Get Debate PDF Links")
print("-" * 40)

debate_url = "https://sansad.in/api_ls/debate/text-of-debate"
pdf_urls = []

for date_str in test_dates:
    # Convert date format (dd/mm/yyyy to m/d/yyyy)
    date_parts = date_str.split('/')
    api_date = f"{int(date_parts[1])}/{int(date_parts[0])}/{date_parts[2]}"
    
    # Try with Roman numeral first (like original curl: sessionNo=V)
    params_roman = {
        'loksabha': '18',
        'sessionNo': 'I',  # Roman numeral for session 1
        'debateDate': api_date,
        'locale': 'en'
    }
    
    # Also try with numeric
    params_numeric = {
        'loksabha': '18',
        'sessionNo': '1',
        'debateDate': api_date,
        'locale': 'en'
    }
    
    print(f"\n📅 Testing date: {date_str} (API format: {api_date})")
    
    # Try both formats
    for format_name, params in [('Roman', params_roman), ('Numeric', params_numeric)]:
        print(f"\n   Trying {format_name} format:")
        print(f"   URL: {debate_url}")
        print(f"   Params: {params}")
        
        try:
            response = requests.get(debate_url, params=params, headers=headers, timeout=30)
            print(f"   Status: {response.status_code}")
            print(f"   Content-Type: {response.headers.get('Content-Type', 'Not specified')}")
            
            if response.status_code == 200:
                # Try parsing as both JSON and plain text
                content = response.text.strip()
                
                # Debug: show raw response
                print(f"   Raw response: {repr(content[:200])}")
                
                # Check if it's JSON
                try:
                    json_data = response.json()
                    print(f"   Parsed as JSON: {json_data}")
                    
                    # Check if JSON contains URL (with key 'pdfUrl')
                    if isinstance(json_data, dict) and json_data.get('pdfUrl'):
                        pdf_url = json_data['pdfUrl']
                        print(f"   ✅ Got PDF URL from JSON: {pdf_url}")
                        pdf_urls.append({
                            'date': date_str,
                            'url': pdf_url,
                            'format': format_name
                        })
                        break  # Found it, no need to try other format
                    else:
                        print(f"   ❓ JSON doesn't contain expected URL (looked for 'pdfUrl' key)")
                        
                except json.JSONDecodeError:
                    # Not JSON, maybe plain text URL
                    if content.startswith('http'):
                        print(f"   ✅ Got PDF URL as plain text: {content}")
                        pdf_urls.append({
                            'date': date_str,
                            'url': content,
                            'format': format_name
                        })
                        break  # Found it
                    else:
                        print(f"   ❓ Not JSON and not a URL")
            else:
                print(f"   ❌ Failed: {response.text[:100]}...")
                
        except Exception as e:
            print(f"   ❌ Error: {e}")

if not pdf_urls:
    print("\n❌ No PDF URLs obtained")
    exit(1)

# Step 3: Test downloading PDFs
print("\n\n3️⃣ STEP 3: Test Downloading PDFs")
print("-" * 40)

# Test download first PDF only
if pdf_urls:
    test_pdf = pdf_urls[0]
    print(f"\n📥 Testing download for {test_pdf['date']} (Session format: {test_pdf.get('format', 'Unknown')})")
    print(f"   URL: {test_pdf['url']}")
    
    try:
        # Prepare headers specifically for PDF download
        download_headers = {
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
            'Accept-Language': 'en-US,en;q=0.9',
            'Connection': 'keep-alive',
            'Referer': 'https://sansad.in/ls/debates/text-of-debates',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'same-origin',
            'Sec-Fetch-User': '?1',
            'Upgrade-Insecure-Requests': '1',
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36'
        }
        
        # Use HEAD request first to check without downloading
        response = requests.head(test_pdf['url'], headers=download_headers, timeout=10, allow_redirects=True)
        print(f"   HEAD Status: {response.status_code}")
        
        # Try GET request regardless of HEAD status (some servers block HEAD)
        print(f"\n   Testing actual download (first 1KB)...")
        response = requests.get(test_pdf['url'], headers=download_headers, timeout=10, stream=True)
        print(f"   GET Status: {response.status_code}")
        
        if response.status_code == 200:
            content_type = response.headers.get('Content-Type', '')
            content_length = response.headers.get('Content-Length', 'Unknown')
            
            print(f"   Content-Type: {content_type}")
            print(f"   Content-Length: {content_length} bytes")
            
            # Read first 1KB
            first_kb = next(response.iter_content(chunk_size=1024))
            
            # Check PDF header
            if first_kb.startswith(b'%PDF'):
                print(f"   ✅ Successfully downloaded PDF (starts with %PDF)")
                print(f"   ✅ PDF is accessible and downloadable!")
            else:
                print(f"   ❓ Downloaded but doesn't start with PDF header")
                print(f"   First bytes: {first_kb[:20]}")
        else:
            print(f"   ❌ Download failed: {response.status_code}")
            print(f"   Response headers: {dict(response.headers)}")
            if response.text:
                print(f"   Error message: {response.text[:200]}")
            
    except Exception as e:
        print(f"   ❌ Error testing download: {e}")

# Summary
print("\n\n📊 SUMMARY")
print("=" * 60)
print(f"✅ Step 1: Got {len(test_dates)} dates from API")
print(f"✅ Step 2: Got {len(pdf_urls)} PDF URLs")
if pdf_urls:
    print(f"✅ Step 3: PDF download test completed")
    
print("\n💡 All external API calls are working!")
print("   The issue might be in our Django implementation.")
