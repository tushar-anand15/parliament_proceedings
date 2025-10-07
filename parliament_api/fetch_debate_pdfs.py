#!/usr/bin/env python3
"""
Fetch PDF URLs for existing Debate records that don't have them yet

This script updates existing Debate records with PDF URLs from the Parliament API
"""

import os
import django
import sys

# Setup Django
sys.path.insert(0, '/home/tusharanand/parliament_proceedings/parliament_api')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'parliament_api.settings')
django.setup()

from services.debates.models import Debate
from services.debates.debate_scraper_service import DebateScraperService
from django.db.models import Q
import time

def fetch_pdf_urls_for_debates(limit=100):
    """Fetch PDF URLs for debates that don't have them"""
    
    # Get debates without PDF URLs
    debates_without_pdfs = Debate.objects.filter(
        Q(pdf_url='') | Q(pdf_url__isnull=True)
    ).exclude(
        status='not_available'
    ).order_by('-debate_date')[:limit]
    
    total = debates_without_pdfs.count()
    print(f"Found {total} debates without PDF URLs")
    print(f"Fetching PDF URLs for up to {limit} debates...")
    
    scraper = DebateScraperService()
    
    updated = 0
    not_found = 0
    errors = 0
    
    for i, debate in enumerate(debates_without_pdfs, 1):
        try:
            print(f"\n[{i}/{total}] Processing {debate.debate_id}...")
            
            # Convert date to API format
            date_str = debate.debate_date.strftime('%d/%m/%Y')
            
            # Fetch debate info with PDF URL
            debate_info = scraper._fetch_debate_info_with_fallback(
                debate.lok_sabha.number,
                debate.session.session_number,
                date_str
            )
            
            if debate_info and debate_info.get('pdf_url'):
                # Update debate with PDF URL
                debate.pdf_url = debate_info['pdf_url']
                debate.raw_api_data = {
                    **debate.raw_api_data,
                    'pdf_fetched': True,
                    'pdf_fetch_api_response': debate_info
                }
                debate.status = 'pending'
                debate.save()
                
                updated += 1
                print(f"  ✓ Updated with PDF URL: {debate_info['pdf_url'][:80]}...")
            else:
                debate.status = 'not_available'
                debate.save()
                not_found += 1
                print(f"  ✗ No PDF URL found")
            
            # Small delay between requests
            time.sleep(0.3)
            
        except Exception as e:
            errors += 1
            print(f"  ✗ Error: {e}")
            continue
    
    print(f"\n{'='*80}")
    print(f"Summary:")
    print(f"  Updated: {updated}")
    print(f"  Not found: {not_found}")
    print(f"  Errors: {errors}")
    print(f"{'='*80}")
    
    return {
        'updated': updated,
        'not_found': not_found,
        'errors': errors
    }

if __name__ == '__main__':
    import argparse
    
    parser = argparse.ArgumentParser(description='Fetch PDF URLs for existing debates')
    parser.add_argument('--limit', type=int, default=100, help='Limit number of debates to process')
    
    args = parser.parse_args()
    
    result = fetch_pdf_urls_for_debates(limit=args.limit)

