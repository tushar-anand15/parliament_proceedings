import time
import csv
import json
import re
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.keys import Keys
from selenium.common.exceptions import TimeoutException, NoSuchElementException, ElementClickInterceptedException
import pandas as pd
import logging
from bs4 import BeautifulSoup

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class SansadScraper:
    def __init__(self, headless=False):
        self.driver = None
        self.headless = headless
        self.data = []
        self.current_page = 1
        self.total_pages = None
        
    def initialize_webdriver(self):
        """Initialize Chrome WebDriver with appropriate options"""
        try:
            chrome_options = Options()
            
            if self.headless:
                chrome_options.add_argument("--headless")
            
            # Add additional options for stability
            chrome_options.add_argument("--no-sandbox")
            chrome_options.add_argument("--disable-dev-shm-usage")
            chrome_options.add_argument("--disable-gpu")
            chrome_options.add_argument("--window-size=1920,1080")
            chrome_options.add_argument("--user-agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
            
            # Initialize the driver
            self.driver = webdriver.Chrome(options=chrome_options)
            self.driver.implicitly_wait(10)
            
            logger.info("WebDriver initialized successfully")
            return True
            
        except Exception as e:
            logger.error(f"Failed to initialize WebDriver: {e}")
            return False
    
    def navigate_to_url(self, url="https://sansad.in/ls/questions/questions-and-answers"):
        """Navigate to the Parliament questions page"""
        try:
            logger.info(f"Navigating to: {url}")
            self.driver.get(url)
            
            # Wait for the page to load
            WebDriverWait(self.driver, 20).until(
                EC.presence_of_element_located((By.CLASS_NAME, "MuiTable-root"))
            )
            
            logger.info("Page loaded successfully")
            return True
            
        except TimeoutException:
            logger.error("Timeout waiting for page to load")
            return False
        except Exception as e:
            logger.error(f"Failed to navigate to URL: {e}")
            return False
    
    def set_rows_per_page(self, rows=100):
        """Set the number of rows per page to 100 for faster processing"""
        try:
            logger.info(f"Setting rows per page to {rows}")
            time.sleep(3)
            
            # Try multiple selectors for pagination dropdown in order of specificity
            pagination_selectors = [
                "#rows-per-page",  # Most specific - the actual ID
                "div[role='combobox'][aria-haspopup='listbox']",
                "div[role='combobox'][id='rows-per-page']",
                ".MuiSelect-select[role='combobox']",
                "div[aria-labelledby*='rows-per-page']",
                ".MuiSelect-select",
                "div[class*='MuiSelect-select']"
            ]
            
            dropdown_found = False
            dropdown_element = None
            
            for selector in pagination_selectors:
                try:
                    dropdown_element = WebDriverWait(self.driver, 5).until(
                        EC.element_to_be_clickable((By.CSS_SELECTOR, selector))
                    )
                    logger.info(f"Found dropdown with selector: {selector}")
                    dropdown_found = True
                    break
                except Exception as e:
                    logger.debug(f"Selector {selector} failed: {e}")
                    continue
            
            if dropdown_found and dropdown_element:
                try:
                    # Scroll element into view and wait for it to be stable
                    self.driver.execute_script("arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});", dropdown_element)
                    time.sleep(2)
                    
                    # Wait for element to be clickable
                    WebDriverWait(self.driver, 10).until(
                        EC.element_to_be_clickable((By.CSS_SELECTOR, "#rows-per-page"))
                    )
                    
                    # Try multiple clicking methods for Material-UI dropdown
                    dropdown_clicked = False
                    
                    # Method 1: ActionChains with hover then click (most reliable for MUI)
                    try:
                        ActionChains(self.driver).move_to_element(dropdown_element).pause(0.5).click().perform()
                        logger.info("Clicked rows per page dropdown using ActionChains")
                        dropdown_clicked = True
                    except Exception as e:
                        logger.debug(f"ActionChains click failed: {e}")
                    
                    # Method 2: Simulate real mouse events with JavaScript
                    if not dropdown_clicked:
                        try:
                            self.driver.execute_script("""
                                var element = arguments[0];
                                var event = new MouseEvent('mousedown', {bubbles: true, cancelable: true, view: window});
                                element.dispatchEvent(event);
                                var event2 = new MouseEvent('mouseup', {bubbles: true, cancelable: true, view: window});
                                element.dispatchEvent(event2);
                                var event3 = new MouseEvent('click', {bubbles: true, cancelable: true, view: window});
                                element.dispatchEvent(event3);
                            """, dropdown_element)
                            logger.info("Clicked rows per page dropdown using JavaScript mouse events")
                            dropdown_clicked = True
                        except Exception as e:
                            logger.debug(f"JavaScript mouse events failed: {e}")
                    
                    # Method 3: Focus and use keyboard
                    if not dropdown_clicked:
                        try:
                            dropdown_element.click()
                            dropdown_element.send_keys(Keys.SPACE)
                            logger.info("Clicked rows per page dropdown using keyboard")
                            dropdown_clicked = True
                        except Exception as e:
                            logger.debug(f"Keyboard interaction failed: {e}")
                    
                    # Method 4: Direct click as last resort
                    if not dropdown_clicked:
                        try:
                            dropdown_element.click()
                            logger.info("Clicked rows per page dropdown using direct click")
                            dropdown_clicked = True
                        except Exception as e:
                            logger.warning(f"All dropdown click methods failed: {e}")
                    
                    if not dropdown_clicked:
                        logger.warning("Could not click dropdown, proceeding without changing rows per page")
                    
                    time.sleep(3)
                    
                    # Check if dropdown actually opened by looking for options
                    dropdown_opened = False
                    try:
                        WebDriverWait(self.driver, 5).until(
                            EC.presence_of_element_located((By.CSS_SELECTOR, "li[role='option'], .MuiMenuItem-root"))
                        )
                        dropdown_opened = True
                        logger.info("Dropdown opened successfully")
                    except:
                        logger.warning("Dropdown may not have opened, trying to proceed anyway")
                    
                    if dropdown_opened or dropdown_clicked:
                        # Look for the options in the opened dropdown
                        option_selectors = [
                            "li[role='option']",
                            ".MuiMenuItem-root",
                            "div[role='option']",
                            "[data-value='100']",
                            "li[data-value='100']",
                            ".MuiList-root li"
                        ]
                        
                        option_found = False
                        for option_selector in option_selectors:
                            try:
                                # Wait for dropdown options to be visible and clickable
                                options = WebDriverWait(self.driver, 5).until(
                                    EC.presence_of_all_elements_located((By.CSS_SELECTOR, option_selector))
                                )
                                
                                logger.debug(f"Found {len(options)} options with selector: {option_selector}")
                                
                                for option in options:
                                    option_text = option.text.strip()
                                    option_value = option.get_attribute('data-value')
                                    
                                    logger.debug(f"Option text: '{option_text}', value: '{option_value}'")
                                    
                                    if option_text == "100" or option_value == "100":
                                        # Try multiple ways to click the option
                                        try:
                                            ActionChains(self.driver).move_to_element(option).click().perform()
                                            logger.info(f"Selected 100 rows per page using ActionChains")
                                            option_found = True
                                            break
                                        except:
                                            try:
                                                option.click()
                                                logger.info(f"Selected 100 rows per page using direct click")
                                                option_found = True
                                                break
                                            except:
                                                logger.debug("Failed to click option, trying next")
                                
                                if option_found:
                                    time.sleep(2)
                                    break
                                    
                            except Exception as e:
                                logger.debug(f"Option selector {option_selector} failed: {e}")
                                continue
                        
                        if not option_found:
                            logger.warning("100 rows option not found in dropdown, proceeding with default")
                    else:
                        logger.warning("Could not open dropdown, proceeding with default rows per page")
                    
                except Exception as e:
                    logger.warning(f"Could not interact with dropdown: {e}")
                    
            else:
                logger.warning("Rows per page dropdown not found, proceeding with default")
                
            return True
            
        except Exception as e:
            logger.error(f"Failed to set rows per page: {e}")
            return False
    
    # def extract_pdf_url_from_expanded_row(self, expand_button):
    #     """DISABLED: Extract PDF URL by expanding a row - not used in fast mode"""
    #     # This method is disabled to speed up processing
    #     # We only check for visible PDF link indicators now
    #     return "Available"
    
    def process_table_data(self):
        """Extract data from the current table view using FAST HTML parsing"""
        try:
            logger.info("Processing table data - INSTANT HTML parsing mode...")
            
            # Wait for table to be present
            WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, ".MuiTableBody-root"))
            )
            
            # Get the raw HTML of the entire table
            logger.info("Getting raw table HTML...")
            table_element = self.driver.find_element(By.CSS_SELECTOR, ".MuiTable-root")
            table_html = table_element.get_attribute('outerHTML')
            
            # Parse with BeautifulSoup
            logger.info("Parsing HTML with BeautifulSoup...")
            soup = BeautifulSoup(table_html, 'html.parser')
            
            # Find all data rows
            rows = soup.select('.MuiTableBody-root .MuiTableRow-root')
            logger.info(f"Found {len(rows)} total rows to process")
            
            processed_count = 0
            
            for row_index, row in enumerate(rows):
                try:
                    # Get all cells in the row
                    cells = row.select('td')
                    if len(cells) < 8:  # Should have at least 8 columns
                        continue
                    
                    # Extract data from each cell using text content
                    question_no = cells[0].get_text(strip=True)
                    if not question_no or not question_no.isdigit():
                        continue  # Skip if not a valid question number
                    
                    subject = cells[1].get_text(strip=True)
                    lok_sabha = cells[2].get_text(strip=True)
                    session = cells[3].get_text(strip=True)
                    
                    # Members can be multiple - get all p tags
                    member_ps = cells[4].select('p')
                    members = [p.get_text(strip=True) for p in member_ps if p.get_text(strip=True)]
                    member_text = "; ".join(members) if members else cells[4].get_text(strip=True)
                    
                    ministry = cells[5].get_text(strip=True)
                    question_type = cells[6].get_text(strip=True)
                    date = cells[7].get_text(strip=True)
                    
                    # Extract PDF link - look for actual URLs in HTML
                    pdf_link = "Not Found"
                    
                    # Method 1: Check for direct links in any cell
                    for cell in cells:
                        # Look for any href attributes containing PDF or getFile
                        links = cell.select('a[href]')
                        for link in links:
                            href = link.get('href', '')
                            if href and ('pdf' in href.lower() or 'getfile' in href.lower() or 'sansad.in' in href.lower()):
                                pdf_link = href if href.startswith('http') else f"https://sansad.in{href}"
                                break
                        if pdf_link != "Not Found":
                            break
                    
                    # Method 2: Check onclick handlers and data attributes
                    if pdf_link == "Not Found":
                        for cell in cells:
                            # Check buttons with onclick
                            buttons = cell.select('button[onclick]')
                            for button in buttons:
                                onclick = button.get('onclick', '')
                                if onclick and ('pdf' in onclick.lower() or 'getfile' in onclick.lower()):
                                    # Extract URL from onclick
                                    url_match = re.search(r"'([^']*(?:pdf|getFile)[^']*)'", onclick)
                                    if url_match:
                                        url = url_match.group(1)
                                        pdf_link = url if url.startswith('http') else f"https://sansad.in{url}"
                                        break
                            if pdf_link != "Not Found":
                                break
                    
                    # Method 3: Check for data attributes that might contain URLs
                    if pdf_link == "Not Found":
                        for cell in cells:
                            elements = cell.select('[data-url], [data-href], [data-link]')
                            for elem in elements:
                                for attr in ['data-url', 'data-href', 'data-link']:
                                    url = elem.get(attr, '')
                                    if url and ('pdf' in url.lower() or 'getfile' in url.lower()):
                                        pdf_link = url if url.startswith('http') else f"https://sansad.in{url}"
                                        break
                                if pdf_link != "Not Found":
                                    break
                            if pdf_link != "Not Found":
                                break
                    
                    # Method 4: Build potential PDF URL based on question number
                    if pdf_link == "Not Found":
                        # Check if there's a link or expand button indicating PDF exists
                        has_link_button = any(cell.select_one('button') for cell in cells[8:])
                        if has_link_button:
                            # Try to construct PDF URL pattern (common for government sites)
                            potential_urls = [
                                f"https://sansad.in/getFile/loksabhaquestions/annex/184/AS{question_no}.pdf",
                                f"https://sansad.in/getFile/loksabhaquestions/annex/184/AS{question_no}_kcKX5O.pdf",
                                f"https://sansad.in/getFile/loksabhaquestions/AS{question_no}.pdf"
                            ]
                            pdf_link = f"Probable: {potential_urls[0]}"
                        else:
                            pdf_link = "Not Found"
                    
                    # Fallback: If we still haven't found a URL but there are buttons, mark as Available
                    if pdf_link == "Not Found":
                        has_any_button = any(cell.select_one('button') for cell in cells[8:])
                        if has_any_button:
                            pdf_link = "Available (URL not extracted)"
                    
                    # Create data record
                    record = {
                        'question_no': question_no,
                        'subject': subject,
                        'lok_sabha': lok_sabha,
                        'session': session,
                        'members': member_text,
                        'ministry': ministry,
                        'type': question_type,
                        'date': date,
                        'pdf_link': pdf_link,
                        'scraped_at': datetime.now().isoformat()
                    }
                    
                    self.data.append(record)
                    processed_count += 1
                    
                except Exception as e:
                    logger.warning(f"Error processing row {row_index}: {e}")
                    continue
            
            logger.info(f"⚡ INSTANTLY processed {processed_count} records from current page!")
            return processed_count
            
        except Exception as e:
            logger.error(f"Failed to process table data: {e}")
            return 0
    
    def navigate_to_next_page(self):
        """Navigate to the next page if available"""
        try:
            # Look for next page button
            next_button_selectors = [
                "button[aria-label='Go to next page']",
                "button[title='Go to next page']",
                ".MuiPagination-root button[aria-label*='next']",
                ".MuiTablePagination-actions button:last-child",
                "button[aria-label='Next page']"
            ]
            
            for selector in next_button_selectors:
                try:
                    next_button = self.driver.find_element(By.CSS_SELECTOR, selector)
                    if (next_button.is_enabled() and 
                        not next_button.get_attribute("disabled") and
                        "disabled" not in next_button.get_attribute("class")):
                        
                        next_button.click()
                        logger.info(f"Navigated to page {self.current_page + 1}")
                        self.current_page += 1
                        
                        # Wait for new data to load
                        time.sleep(3)
                        return True
                except:
                    continue
            
            logger.info("No next page available or next button not found")
            return False
            
        except Exception as e:
            logger.error(f"Failed to navigate to next page: {e}")
            return False
    
    def get_table_info(self):
        """Get information about the table (total rows, pages, etc.)"""
        try:
            # Try to find pagination info
            pagination_info = None
            try:
                pagination_elements = self.driver.find_elements(By.CSS_SELECTOR, ".MuiTablePagination-displayedRows")
                if pagination_elements:
                    pagination_info = pagination_elements[0].text
                    logger.info(f"Pagination info: {pagination_info}")
            except:
                pass
            
            # Count current visible rows
            rows = self.driver.find_elements(By.CSS_SELECTOR, ".MuiTableBody-root .MuiTableRow-root")
            visible_rows = len([row for row in rows if row.find_elements(By.CSS_SELECTOR, "td")])
            
            logger.info(f"Visible data rows in current view: {visible_rows}")
            return visible_rows, pagination_info
            
        except Exception as e:
            logger.error(f"Failed to get table info: {e}")
            return 0, None
    
    def save_data_to_csv(self, filename=None):
        """Save scraped data to CSV file"""
        try:
            if not self.data:
                logger.warning("No data to save")
                return False
            
            if filename is None:
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                filename = f"parliament_questions_{timestamp}.csv"
            
            df = pd.DataFrame(self.data)
            df.to_csv(filename, index=False, encoding='utf-8')
            
            logger.info(f"Saved {len(self.data)} records to {filename}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to save data to CSV: {e}")
            return False
    
    def save_data_to_json(self, filename=None):
        """Save scraped data to JSON file"""
        try:
            if not self.data:
                logger.warning("No data to save")
                return False
            
            if filename is None:
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                filename = f"parliament_questions_{timestamp}.json"
            
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(self.data, f, indent=2, ensure_ascii=False)
            
            logger.info(f"Saved {len(self.data)} records to {filename}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to save data to JSON: {e}")
            return False
    
    def scrape_all_pages(self, max_pages=None):
        """Scrape all available pages"""
        try:
            logger.info("Starting to scrape all pages...")
            
            page_count = 0
            while True:
                if max_pages and page_count >= max_pages:
                    logger.info(f"Reached maximum pages limit: {max_pages}")
                    break
                
                logger.info(f"Scraping page {self.current_page}")
                
                # Process current page
                records_processed = self.process_table_data()
                if records_processed == 0:
                    logger.warning("No records processed, stopping")
                    break
                
                page_count += 1
                
                # Try to navigate to next page
                if not self.navigate_to_next_page():
                    logger.info("No more pages available")
                    break
                
                # Add a small delay between pages
                time.sleep(2)
            
            logger.info(f"Scraping completed. Total pages: {page_count}, Total records: {len(self.data)}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to scrape all pages: {e}")
            return False
    
    def close(self):
        """Close the WebDriver"""
        if self.driver:
            self.driver.quit()
            logger.info("WebDriver closed")

def main():
    """Main function to run the scraper in FAST mode"""
    scraper = SansadScraper(headless=False)  # Set to True for headless mode
    
    try:
        # Initialize and navigate
        logger.info("🚀 Starting FAST table scraping (no PDF expansion)")
        if not scraper.initialize_webdriver():
            return
        
        if not scraper.navigate_to_url():
            return
        
        # Set rows per page to 100
        scraper.set_rows_per_page(100)
        
        # Get table info
        visible_rows, pagination_info = scraper.get_table_info()
        logger.info(f"Table info - Visible rows: {visible_rows}, Pagination: {pagination_info}")
        
        # Scrape all pages (limit to 5 pages for testing)
        scraper.scrape_all_pages(max_pages=5)
        
        # Save data
        scraper.save_data_to_csv()
        scraper.save_data_to_json()
        
        logger.info("✅ Fast scraping completed successfully!")
        
    except Exception as e:
        logger.error(f"Scraping failed: {e}")
    
    finally:
        scraper.close()

if __name__ == "__main__":
    main()
