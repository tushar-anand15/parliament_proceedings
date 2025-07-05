#!/usr/bin/env python3
"""
Simple runner for the Parliament Questions Scraper
"""

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), 'scraper'))

from scraper.sansad import SansadScraper
import logging

def main():
    """Run the scraper with configurable options"""
    
    # Configuration
    HEADLESS = False  # Set to True to run without browser window
    MAX_PAGES = 2     # Limit pages for testing (set to None for all pages)
    
    print("🚀 Starting Parliament Questions Scraper...")
    print(f"   Headless mode: {HEADLESS}")
    print(f"   Max pages: {MAX_PAGES if MAX_PAGES else 'All'}")
    print()
    
    scraper = SansadScraper(headless=HEADLESS)
    
    try:
        # Initialize and navigate
        print("🔧 Initializing WebDriver...")
        if not scraper.initialize_webdriver():
            print("❌ Failed to initialize WebDriver")
            return
        
        print("🌐 Navigating to Parliament website...")
        if not scraper.navigate_to_url():
            print("❌ Failed to navigate to website")
            return
        
        print("⚙️ Setting rows per page to 100...")
        scraper.set_rows_per_page(100)
        
        # Get table info
        print("📊 Getting table information...")
        visible_rows, pagination_info = scraper.get_table_info()
        print(f"   Visible rows: {visible_rows}")
        print(f"   Pagination: {pagination_info}")
        
        # Scrape pages
        print(f"🔍 Starting to scrape (max {MAX_PAGES} pages)...")
        scraper.scrape_all_pages(max_pages=MAX_PAGES)
        
        # Save data
        print("💾 Saving data...")
        csv_saved = scraper.save_data_to_csv()
        json_saved = scraper.save_data_to_json()
        
        if csv_saved and json_saved:
            print(f"✅ Successfully scraped {len(scraper.data)} records!")
            print("   Data saved to CSV and JSON files")
        else:
            print("⚠️ Some files failed to save")
        
    except KeyboardInterrupt:
        print("\n⏹️ Scraping interrupted by user")
    except Exception as e:
        print(f"❌ Scraping failed: {e}")
        logging.error(f"Scraping failed: {e}")
    
    finally:
        print("🔚 Closing browser...")
        scraper.close()
        print("Done!")

if __name__ == "__main__":
    main() 