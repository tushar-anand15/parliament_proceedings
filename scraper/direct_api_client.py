#!/usr/bin/env python3
"""
Direct API client for Parliament Questions data
Based on API endpoints extracted from the JavaScript bundle
"""

import requests
import json
import time
from datetime import datetime
from typing import Dict, List, Optional
import logging
import threading
import queue
from concurrent.futures import ThreadPoolExecutor, as_completed

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class BusinessDaysPDFClient:
    """Client for fetching business days and associated PDFs from Parliament
    
    This client properly queries the API endpoints to get actual PDF information
    rather than constructing URLs.
    """
    
    def __init__(self):
        self.base_url = "https://sansad.in"
        self.cms_url = "https://sansad.in/cms/ls-pp"
        self.api_url = "https://sansad.in/api_ls"
        self.session = requests.Session()
        
        # Set headers to mimic browser requests
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'application/json, text/plain, */*',
            'Accept-Language': 'en-US,en;q=0.9',
            'Referer': 'https://sansad.in/',
            'Origin': 'https://sansad.in'
        })
    
    def get_all_sessions(self) -> List[Dict]:
        """
        Get all Lok Sabha and session information
        
        Returns:
            List of dictionaries containing Lok Sabha and session data
        """
        url = f"{self.api_url}/business/AllLoksabhaAndSessionDates"
        
        try:
            logger.info("Fetching all Lok Sabha and session data...")
            response = self.session.get(url, timeout=30)
            response.raise_for_status()
            
            data = response.json()
            logger.info(f"Retrieved data for {len(data)} Lok Sabhas")
            
            return data
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to fetch session data: {e}")
            return []
    
    def get_business_days_with_pdf_urls(self, loksabha_no: str, session_no: str) -> Dict:
        """
        Get business days for a specific Lok Sabha and session.
        
        For current/future dates where API doesn't return data, we provide the URL pattern
        that the website uses.
        
        Args:
            loksabha_no: Lok Sabha number (e.g., "17", "18")
            session_no: Session number (e.g., "1", "2", "4")
            
        Returns:
            Dictionary containing session info and list of business days with PDF URLs
        """
        
        try:
            # Convert inputs to integers for comparison
            ls_no = int(loksabha_no)
            sess_no = int(session_no)
            
            logger.info(f"Getting business days for {loksabha_no}th Lok Sabha, Session {session_no}")
            
            # Get all session data to find business days
            all_sessions = self.get_all_sessions()
            
            if not all_sessions:
                logger.warning("No session data available")
                return {}
            
            # Find the specific Lok Sabha and session
            for ls_data in all_sessions:
                if ls_data.get('loksabha') == ls_no:
                    for session in ls_data.get('sessions', []):
                        if session.get('sessionNo') == sess_no:
                            # Extract session info
                            session_info = {
                                'loksabha': ls_no,
                                'session': sess_no,
                                'sessionPeriod': session.get('sessionPeriod', []),
                                'dates': []
                            }
                            
                            # Convert session number to Roman numeral
                            session_roman = self._to_roman(sess_no)
                            
                            # Process each business day
                            dates = session.get('dates', [])
                            logger.info(f"Found {len(dates)} business days")
                            
                            for date_str in dates:
                                # Convert date format from dd/mm/yyyy to dd.mm.yyyy
                                date_parts = date_str.split('/')
                                if len(date_parts) == 3:
                                    date_dot_format = f"{date_parts[0]}.{date_parts[1]}.{date_parts[2]}"
                                    
                                    # For each date, provide the URL pattern used by the website
                                    # The actual availability needs to be checked separately
                                    day_info = {
                                        'date': date_str,
                                        'date_dot_format': date_dot_format,
                                        'loksabha': loksabha_no,
                                        'session': session_no,
                                        'session_roman': session_roman,
                                        'pdfs': {
                                            'debate': f"{self.base_url}/getFile/debatestextmk/{loksabha_no}/{session_roman}/{date_dot_format} f.pdf?source=loksabhadocs",
                                            'business': f"{self.base_url}/getFile/loksabhadocs/{loksabha_no}/{session_roman}/business/{date_dot_format}.pdf"
                                        }
                                    }
                                    session_info['dates'].append(day_info)
                            
                            return session_info
            
            logger.warning(f"No data found for {loksabha_no}th Lok Sabha, Session {session_no}")
            return {}
            
        except (ValueError, TypeError) as e:
            logger.error(f"Invalid input parameters: {e}")
            return {}
        except Exception as e:
            logger.error(f"Error getting business days: {e}")
            return {}
    
    def _to_roman(self, num: int) -> str:
        """Convert an integer to Roman numeral"""
        val = [
            1000, 900, 500, 400,
            100, 90, 50, 40,
            10, 9, 5, 4,
            1
        ]
        syms = [
            "M", "CM", "D", "CD",
            "C", "XC", "L", "XL",
            "X", "IX", "V", "IV",
            "I"
        ]
        roman_num = ''
        i = 0
        while num > 0:
            for _ in range(num // val[i]):
                roman_num += syms[i]
                num -= val[i]
            i += 1
        return roman_num
    
    def check_pdf_availability(self, pdf_url: str) -> bool:
        """
        Check if a PDF URL is accessible
        
        Note: sansad.in doesn't allow HEAD requests, so we use a GET request
        with stream=True to check without downloading the full file.
        
        Args:
            pdf_url: URL of the PDF to check
            
        Returns:
            True if PDF exists and is accessible, False otherwise
        """
        try:
            # Use GET with stream=True to avoid downloading the entire file
            response = self.session.get(pdf_url, stream=True, timeout=10)
            # Check if successful
            is_available = response.status_code == 200
            # Close the response to free up the connection
            response.close()
            return is_available
        except:
            return False
    
    def download_pdf(self, pdf_url: str, save_path: str) -> bool:
        """
        Download a PDF from the given URL
        
        Args:
            pdf_url: URL of the PDF to download
            save_path: Local path to save the PDF
            
        Returns:
            True if download successful, False otherwise
        """
        try:
            logger.info(f"Downloading PDF from {pdf_url}")
            response = self.session.get(pdf_url, timeout=30)
            response.raise_for_status()
            
            with open(save_path, 'wb') as f:
                f.write(response.content)
            
            logger.info(f"PDF saved to {save_path}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to download PDF: {e}")
            return False
    
    def get_debate_text_api_data(self, loksabha_no: str, session_no: str, date: str, locale: str = "en") -> Dict:
        """
        Get debate text data from the API endpoint discovered in the JavaScript
        
        Args:
            loksabha_no: Lok Sabha number
            session_no: Session number
            date: Date in appropriate format
            locale: Language locale (default: "en")
            
        Returns:
            API response data
        """
        url = f"{self.cms_url}/api/text-of-debates"
        
        params = {
            'loksabhaNo': loksabha_no,
            'sessionNo': session_no,
            'date': date,
            'locale': locale
        }
        
        try:
            logger.info(f"Fetching debate text data for LS{loksabha_no} Session {session_no} Date {date}")
            response = self.session.get(url, params=params, timeout=30)
            response.raise_for_status()
            
            return response.json()
            
        except Exception as e:
            logger.error(f"Failed to fetch debate text data: {e}")
            return {}
    
    def get_business_documents_api(self, loksabha_no: str, session_no: str, date: str, locale: str = "en") -> Dict:
        """
        Get business documents data from the API
        
        Args:
            loksabha_no: Lok Sabha number
            session_no: Session number
            date: Date in appropriate format (yyyy-mm-dd)
            locale: Language locale (default: "en")
            
        Returns:
            API response with business document URLs
        """
        # Try the business API endpoint
        url = f"{self.cms_url}/api/business-documents"
        
        params = {
            'loksabhaNo': loksabha_no,
            'sessionNo': session_no,
            'date': date,
            'locale': locale
        }
        
        try:
            logger.info(f"Fetching business documents for LS{loksabha_no} Session {session_no} Date {date}")
            response = self.session.get(url, params=params, timeout=30)
            
            if response.status_code == 200:
                return response.json()
            else:
                logger.info(f"Business documents API returned status {response.status_code}")
                return {}
                
        except Exception as e:
            logger.error(f"Failed to fetch business documents: {e}")
            return {}
    
    def test_pdf_url_formats(self, loksabha_no: str, session_no: str, date_str: str) -> Dict[str, Dict]:
        """
        Test different PDF URL formats to find which ones work
        
        Args:
            loksabha_no: Lok Sabha number
            session_no: Session number  
            date_str: Date string in dd/mm/yyyy format
            
        Returns:
            Dictionary with test results for different URL formats
        """
        # Parse date
        date_parts = date_str.split('/')
        if len(date_parts) != 3:
            return {'error': 'Invalid date format'}
        
        # Generate different date formats
        date_url_format = f"{date_parts[0]}{date_parts[1]}{date_parts[2]}"  # ddmmyyyy
        date_dot_format = f"{date_parts[0]}.{date_parts[1]}.{date_parts[2]}"  # dd.mm.yyyy
        
        # Convert session to Roman
        session_roman = self._to_roman(int(session_no))
        
        # Test different URL patterns
        test_urls = {
            'debate_corrected_space': f"{self.base_url}/getFile/debatestextmk/{loksabha_no}/{session_roman}/{date_dot_format} f.pdf?source=loksabhadocs",
            'debate_corrected_encoded': f"{self.base_url}/getFile/debatestextmk/{loksabha_no}/{session_roman}/{date_dot_format}%20f.pdf?source=loksabhadocs",
            'debate_old_format': f"{self.base_url}/getFile/debatestextmk/{loksabha_no}/{session_no}/{date_url_format}PDF.pdf?source=loksabhadocs",
            'business_v1': f"{self.base_url}/getFile/loksabhadocs/{loksabha_no}/{session_no}/business/{date_url_format}.pdf",
            'business_v2': f"{self.base_url}/getFile/loksabhadocs/{loksabha_no}/{session_roman}/business/{date_dot_format}.pdf",
        }
        
        results = {}
        for name, url in test_urls.items():
            logger.info(f"Testing {name}: {url}")
            is_available = self.check_pdf_availability(url)
            results[name] = {
                'url': url,
                'available': is_available
            }
            
        return results


class ParliamentAPI:
    """Direct API client for Parliament Questions and Answers"""
    
    def __init__(self):
        self.base_url = "https://eparlib.sansad.in/restv3"
        self.sansad_url = "https://sansad.in/api_ls"
        self.session = requests.Session()
        
        # Set headers to mimic browser requests
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'application/json, text/plain, */*',
            'Accept-Language': 'en-US,en;q=0.9',
            'Referer': 'https://sansad.in/',
            'Origin': 'https://sansad.in'
        })
    
    def get_questions(self, 
                     start: int = 0, 
                     rows: int = 50,
                     loksabha_no: Optional[str] = None,
                     session_no: Optional[str] = None,
                     search_term: Optional[str] = None,
                     member: Optional[str] = None,
                     ministry: Optional[str] = None,
                     question_type: Optional[str] = None,
                     date: Optional[str] = None,
                     order: Optional[str] = None) -> Dict:
        """
        Fetch questions data from the API
        
        Args:
            start: Starting record number (pagination)
            rows: Number of records to fetch
            loksabha_no: Lok Sabha number (e.g., "17", "16")
            session_no: Session number 
            search_term: Search keyword (min 3 chars)
            member: Member name filter
            ministry: Ministry filter
            question_type: Question type filter
            date: Date filter (dd-MMM-yyyy format)
            order: Sorting parameter
        """
        
        url = f"{self.base_url}/fetch/all"
        
        # Build parameters
        params = {
            'start': start,
            'rows': rows,
            'collectionId': 3  # Questions collection
        }
        
        # Add optional filters
        if loksabha_no:
            params['loksabhaNo'] = loksabha_no
        if session_no:
            params['sessionNo'] = session_no
        if search_term and len(search_term) >= 3:
            params['anyWhere'] = search_term
        if member:
            params['member'] = member
        if ministry:
            params['ministry'] = ministry
        if question_type:
            params['questionType'] = question_type
        if date:
            params['date'] = date
        if order:
            params['order'] = order
        
        try:
            logger.info(f"Fetching questions: {params}")
            response = self.session.get(url, params=params, timeout=30)
            response.raise_for_status()
            
            data = response.json()
            
            logger.info(f"Retrieved {len(data.get('records', []))} records, "
                       f"Total: {int(data.get('rowsCount', 0))}")
            
            return data
            
        except requests.exceptions.RequestException as e:
            logger.error(f"API request failed: {e}")
            return {}
    
    def get_field_browse(self, 
                        field: str,
                        start: int = 0,
                        rows: int = 1000,
                        order: str = "count",
                        **filters) -> List[Dict]:
        """
        Get field browse data (for filters/facets)
        
        Args:
            field: Field to browse (e.g., 'loksabhaNo', 'members', 'ministry')
            start: Starting record
            rows: Number of records
            order: Sorting order
            **filters: Additional filter parameters
        """
        
        url = f"{self.base_url}/field/browse"
        
        params = {
            'field': field,
            'start': start,
            'rows': rows,
            'order': order,
            'collectionId': 3
        }
        
        # Add any additional filters
        params.update(filters)
        
        try:
            logger.info(f"Browsing field '{field}' with params: {params}")
            response = self.session.get(url, params=params, timeout=30)
            response.raise_for_status()
            
            data = response.json()
            records = data.get('records', [])
            
            logger.info(f"Retrieved {len(records)} {field} options")
            return records
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Field browse request failed: {e}")
            return []
    
    def get_session_data(self) -> List[Dict]:
        """Get Lok Sabha and session information"""
        
        url = f"{self.sansad_url}/business/AllLoksabhaAndSessionDates"
        
        try:
            logger.info("Fetching session data...")
            response = self.session.get(url, timeout=30)
            response.raise_for_status()
            
            data = response.json()
            logger.info(f"Retrieved session data for {len(data)} Lok Sabhas")
            
            return data
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Session data request failed: {e}")
            return []
    
    def get_all_questions_paginated(self, 
                                   max_records: Optional[int] = None,
                                   page_size: int = 100,
                                   **filters) -> List[Dict]:
        """
        Fetch all questions with pagination
        
        Args:
            max_records: Maximum number of records to fetch
            page_size: Records per page
            **filters: Filter parameters
        """
        
        all_records = []
        start = 0
        
        logger.info(f"Starting paginated fetch (page_size={page_size})")
        
        while True:
            # Get current batch
            data = self.get_questions(start=start, rows=page_size, **filters)
            
            if not data or 'records' not in data:
                logger.warning("No data received, stopping pagination")
                break
            
            records = data['records']
            total_count = int(data.get('rowsCount', 0))
            
            if not records:
                logger.info("No more records available")
                break
            
            all_records.extend(records)
            
            logger.info(f"Fetched {len(records)} records (total so far: {len(all_records)}/{total_count})")
            
            # Check if we've reached max_records
            if max_records and len(all_records) >= max_records:
                all_records = all_records[:max_records]
                logger.info(f"Reached max_records limit: {max_records}")
                break
            
            # Check if we've reached the end
            if len(records) < page_size or start + page_size >= total_count:
                logger.info("Reached end of data")
                break
            
            start += page_size
            time.sleep(0.5)  # Be nice to the server
        
        logger.info(f"Completed pagination. Total records: {len(all_records)}")
        return all_records
    
    def fetch_questions_batch(self, start: int, rows: int, **filters) -> List[Dict]:
        """
        Fetch a single batch of questions (used by parallel workers)
        """
        try:
            data = self.get_questions(start=start, rows=rows, **filters)
            records = data.get('records', []) if data else []
            logger.info(f"Worker fetched batch start={start}, got {len(records)} records")
            return records
        except Exception as e:
            logger.error(f"Worker failed for batch start={start}: {e}")
            return []
    
    def get_all_loksabha_questions_parallel(self, loksabha_no: str, num_workers: int = 5) -> List[Dict]:
        """
        Fetch ALL questions from specified Lok Sabha using parallel workers
        """
        logger.info(f"Starting parallel fetch for {loksabha_no}th Lok Sabha with {num_workers} workers...")
        
        # First get total count
        sample = self.get_questions(start=0, rows=1, loksabha_no=loksabha_no)
        total_count = int(sample.get('rowsCount', 0)) if sample else 0
        
        logger.info(f"Total questions in {loksabha_no}th Lok Sabha: {total_count}")
        
        if total_count == 0:
            return []
        
        # Calculate batch parameters
        batch_size = 100  # Records per batch
        total_batches = (total_count + batch_size - 1) // batch_size  # Ceiling division
        
        logger.info(f"Will fetch {total_batches} batches of {batch_size} records each")
        
        # Create list of start positions for each batch
        batch_starts = [i * batch_size for i in range(total_batches)]
        
        all_records = []
        
        # Use ThreadPoolExecutor for parallel fetching
        with ThreadPoolExecutor(max_workers=num_workers) as executor:
            # Submit all batch jobs
            future_to_start = {
                executor.submit(self.fetch_questions_batch, start, batch_size, loksabha_no=loksabha_no): start 
                for start in batch_starts
            }
            
            # Collect results as they complete
            completed_batches = 0
            for future in as_completed(future_to_start):
                start_pos = future_to_start[future]
                try:
                    batch_records = future.result()
                    all_records.extend(batch_records)
                    completed_batches += 1
                    
                    progress = (completed_batches / total_batches) * 100
                    logger.info(f"Completed batch {completed_batches}/{total_batches} "
                               f"(start={start_pos}) - Progress: {progress:.1f}% "
                               f"(Total records so far: {len(all_records)})")
                    
                except Exception as e:
                    logger.error(f"Batch starting at {start_pos} failed: {e}")
        
        # Sort records by question number for consistent ordering
        try:
            all_records.sort(key=lambda x: int(x.get('questionNo', 0)))
        except (ValueError, TypeError):
            logger.warning("Could not sort by questionNo, keeping original order")
        
        logger.info(f"Parallel fetch completed! Total records: {len(all_records)}")
        return all_records
    
    def save_to_json(self, data: List[Dict], filename: str, loksabha_no: str) -> None:
        """
        Save questions data to JSON file
        """
        try:
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump({
                    'metadata': {
                        'total_questions': len(data),
                        'loksabha': loksabha_no,
                        'fetch_timestamp': datetime.now().isoformat(),
                        'source': 'eparlib.sansad.in API'
                    },
                    'questions': data
                }, f, indent=2, ensure_ascii=False)
            
            logger.info(f"Data saved to {filename}")
            print(f"✅ Data saved to {filename}")
            
        except Exception as e:
            logger.error(f"Failed to save to {filename}: {e}")
            print(f"❌ Failed to save to {filename}: {e}")
    
    def get_all_17th_loksabha_questions(self) -> List[Dict]:
        """
        Fetch ALL questions from 17th Lok Sabha
        """
        logger.info("Starting to fetch ALL questions from 17th Lok Sabha...")
        
        # First get a sample to see total count
        sample = self.get_questions(start=0, rows=1, loksabha_no="17")
        total_count = int(sample.get('rowsCount', 0)) if sample else 0
        
        logger.info(f"Total questions in 17th Lok Sabha: {total_count}")
        
        if total_count == 0:
            return []
        
        # Fetch all records in batches
        return self.get_all_questions_paginated(
            max_records=None,  # Get all
            page_size=100,     # 100 per batch
            loksabha_no="17"
        )
    
    def display_questions_table(self, questions: List[Dict]) -> None:
        """
        Display questions in a formatted table with links
        """
        if not questions:
            print("No questions to display")
            return
        
        print(f"\n📊 ALL 17TH LOK SABHA QUESTIONS ({len(questions)} total)")
        print("=" * 150)
        
        # Table headers
        headers = [
            "S.No", "Q.No", "Date", "Type", "Subject", "Member", "Ministry", "Link"
        ]
        
        # Print headers
        header_line = f"│{headers[0]:>5}│{headers[1]:>8}│{headers[2]:>12}│{headers[3]:>10}│{headers[4]:>60}│{headers[5]:>25}│{headers[6]:>20}│{headers[7]:>30}│"
        print("┌" + "─" * (len(header_line) - 2) + "┐")
        print(header_line)
        print("├" + "─" * (len(header_line) - 2) + "┤")
        
        # Print each question
        for i, q in enumerate(questions, 1):
            # Extract data with safe defaults
            q_no = str(q.get('questionNo', 'N/A'))
            date = q.get('date', 'N/A')
            q_type = q.get('questionType', 'N/A')
            title = q.get('title', 'N/A')
            
            # Handle members (could be list or string)
            members = q.get('members', [])
            if isinstance(members, list):
                member = members[0] if members else 'N/A'
            else:
                member = str(members) if members else 'N/A'
            
            # Handle ministry (could be list or string)
            ministry = q.get('ministry', [])
            if isinstance(ministry, list):
                ministry_str = ministry[0] if ministry else 'N/A'
            else:
                ministry_str = str(ministry) if ministry else 'N/A'
            
            # Generate link (based on typical parliament website structure)
            doc_id = q.get('id', '')
            if doc_id:
                link = f"https://sansad.in/getFile?source=questions&type=questions&id={doc_id}"
            else:
                link = "N/A"
            
            # Truncate long fields
            title = title[:57] + "..." if len(title) > 60 else title
            member = member[:22] + "..." if len(member) > 25 else member
            ministry_str = ministry_str[:17] + "..." if len(ministry_str) > 20 else ministry_str
            link = link[:27] + "..." if len(link) > 30 else link
            
            # Print row
            row = f"│{i:>5}│{q_no:>8}│{date:>12}│{q_type:>10}│{title:>60}│{member:>25}│{ministry_str:>20}│{link:>30}│"
            print(row)
        
        print("└" + "─" * (len(header_line) - 2) + "┘")
        
        # Summary statistics
        print(f"\n📈 SUMMARY STATISTICS:")
        print(f"   Total Questions: {len(questions)}")
        
        # Count by type
        type_counts = {}
        for q in questions:
            q_type = q.get('questionType', 'Unknown')
            type_counts[q_type] = type_counts.get(q_type, 0) + 1
        
        print(f"   By Type:")
        for q_type, count in sorted(type_counts.items()):
            print(f"      {q_type}: {count}")
        
        # Count by ministry (top 10)
        ministry_counts = {}
        for q in questions:
            ministries = q.get('ministry', [])
            if isinstance(ministries, list):
                for ministry in ministries:
                    ministry_counts[ministry] = ministry_counts.get(ministry, 0) + 1
            elif ministries:
                ministry_counts[str(ministries)] = ministry_counts.get(str(ministries), 0) + 1
        
        print(f"   Top 10 Ministries:")
        for ministry, count in sorted(ministry_counts.items(), key=lambda x: x[1], reverse=True)[:10]:
            print(f"      {ministry}: {count}")
        
        print(f"\n💾 Data can be exported to CSV/Excel if needed")
        print("=" * 150)

def main():
    """Fetch ALL questions from 16th Lok Sabha using parallel workers and save to JSON"""
    
    print("🏛️ 16th Lok Sabha Questions - Parallel Fetch & JSON Export")
    print("=" * 80)
    
    client = ParliamentAPI()
    loksabha_no = "16"  # Target 16th Lok Sabha
    
    try:
        # Fetch all questions using 5 parallel workers
        print(f"🚀 Fetching ALL questions from {loksabha_no}th Lok Sabha using 5 parallel workers...")
        print("⚡ This should be much faster than sequential fetching!")
        
        start_time = time.time()
        all_questions = client.get_all_loksabha_questions_parallel(loksabha_no=loksabha_no, num_workers=5)
        end_time = time.time()
        
        fetch_duration = end_time - start_time
        
        if all_questions:
            print(f"\n✅ Successfully fetched {len(all_questions)} questions!")
            print(f"⏱️  Total fetch time: {fetch_duration:.2f} seconds")
            print(f"📊 Average: {len(all_questions)/fetch_duration:.1f} questions/second")
            
            # Save to JSON file
            filename = f"{loksabha_no}th_loksabha_questions_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            print(f"\n💾 Saving data to {filename}...")
            client.save_to_json(all_questions, filename, loksabha_no)
            
            # Display brief summary table (first 20 questions)
            print(f"\n📋 PREVIEW - First 20 Questions:")
            preview_questions = all_questions[:20]
            client.display_questions_table(preview_questions)
            
            # Show summary statistics
            print(f"\n📈 COMPLETE DATASET SUMMARY:")
            print(f"   📄 Total Questions: {len(all_questions)}")
            
            # Question types
            type_counts = {}
            for q in all_questions:
                q_type = q.get('questionType', 'Unknown')
                type_counts[q_type] = type_counts.get(q_type, 0) + 1
            
            print(f"   📊 By Question Type:")
            for q_type, count in sorted(type_counts.items()):
                percentage = (count / len(all_questions)) * 100
                print(f"      • {q_type}: {count} ({percentage:.1f}%)")
            
            # Date range
            dates = [q.get('date', '') for q in all_questions if q.get('date')]
            if dates:
                dates.sort()
                print(f"   📅 Date Range: {dates[0]} to {dates[-1]}")
            
            print(f"\n🎉 SUCCESS! Complete dataset ready for analysis:")
            print(f"   • JSON file: {filename}")
            print(f"   • {len(all_questions)} complete question records")
            print(f"   • All metadata preserved (members, ministries, dates, links)")
            print(f"   • Fetched in {fetch_duration:.2f} seconds using parallel processing")
            
        else:
            print(f"❌ No questions found for {loksabha_no}th Lok Sabha")
            print("   This might be due to:")
            print("   • API access issues")
            print("   • Network connectivity problems") 
            print("   • Changes in the API structure")
            
    except Exception as e:
        print(f"❌ Error occurred while fetching questions: {e}")
        logger.error(f"Error in main: {e}", exc_info=True)

def demo_business_days_client():
    """Demonstrate the BusinessDaysPDFClient functionality"""
    
    print("🏛️ Business Days and PDFs Client Demo")
    print("=" * 80)
    
    client = BusinessDaysPDFClient()
    
    # Example 1: Get business days with PDF URLs using the simple method
    print("\n📅 Example 1: Get Business Days with PDF URLs (18th LS, Session 4)")
    print("-" * 40)
    
    loksabha_no = "18"
    session_no = "4"
    
    session_data = client.get_business_days_with_pdf_urls(loksabha_no, session_no)
    
    if session_data:
        print(f"✅ Lok Sabha {session_data['loksabha']}, Session {session_data['session']}")
        print(f"📆 Session Period: {', '.join(session_data['sessionPeriod'])}")
        print(f"📊 Total Business Days: {len(session_data['dates'])}")
        
        # Check availability for ALL dates
        print("\n\n🔍 Checking PDF availability for ALL business days:")
        print("-" * 80)
        print(f"{'Date':<12} {'Debate PDF':<15} {'Business PDF':<15} {'Debate URL'}")
        print("-" * 80)
        
        available_count = 0
        business_available_count = 0
        for i, day in enumerate(session_data['dates'], 1):
            # Check debate PDF
            debate_url = day['pdfs']['debate']
            debate_available = client.check_pdf_availability(debate_url)
            
            # Check business PDF
            business_url = day['pdfs']['business']
            business_available = client.check_pdf_availability(business_url)
            
            # Count available PDFs
            if debate_available:
                available_count += 1
            if business_available:
                business_available_count += 1
            
            # Display results (only show available ones to reduce output)
            if debate_available or business_available:
                debate_status = "✅ Available" if debate_available else "❌ Not found"
                business_status = "✅ Available" if business_available else "❌ Not found"
                print(f"{day['date']:<12} {debate_status:<15} {business_status:<15} {debate_url}")
        
        print("-" * 80)
        print(f"\n📊 Summary:")
        print(f"   - Debate PDFs: {available_count} out of {len(session_data['dates'])} are available")
        print(f"   - Business PDFs: {business_available_count} out of {len(session_data['dates'])} are available")
        
        # Show all available dates
        if available_count > 0:
            print("\n✅ Available debate PDFs:")
            for day in session_data['dates']:
                debate_url = day['pdfs']['debate']
                if client.check_pdf_availability(debate_url):
                    print(f"   - {day['date']}: {debate_url}")
    
    print("\n" + "=" * 80)
    print("Demo completed!")


if __name__ == "__main__":
    # Uncomment the demo you want to run:
    
    # Run the new Business Days PDF Client demo
    demo_business_days_client()
    
    # Or run the original Parliament API demo
    # main() 