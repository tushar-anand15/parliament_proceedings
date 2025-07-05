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
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

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
        
        url = f"{self.sansad_url}/business/getAllLoksabhaAndSession"
        
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

if __name__ == "__main__":
    main() 