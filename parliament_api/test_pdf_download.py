#!/usr/bin/env python3
"""
Parliament API PDF Download Test Script

This script sends HTTP requests to the deployed Parliament API to schedule
scraping and downloading of 50 random questions and debates from LS and RS.

Usage:
    python test_pdf_download.py

Requirements:
    pip install requests
"""

import requests
import json
import random
import time
from datetime import datetime
from typing import Dict, List, Any

# Configuration
BASE_URL = "https://api.opensansad.co.in"
TOKEN = "***REMOVED_SECRET***"

HEADERS = {
    "Authorization": f"Token {TOKEN}",
    "Content-Type": "application/json"
}

# Color codes for terminal output
class Colors:
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKCYAN = '\033[96m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'

def print_header(text: str):
    """Print formatted header"""
    print(f"\n{Colors.HEADER}{Colors.BOLD}{'='*80}{Colors.ENDC}")
    print(f"{Colors.HEADER}{Colors.BOLD}{text.center(80)}{Colors.ENDC}")
    print(f"{Colors.HEADER}{Colors.BOLD}{'='*80}{Colors.ENDC}\n")

def print_success(text: str):
    """Print success message"""
    print(f"{Colors.OKGREEN}✓ {text}{Colors.ENDC}")

def print_error(text: str):
    """Print error message"""
    print(f"{Colors.FAIL}✗ {text}{Colors.ENDC}")

def print_info(text: str):
    """Print info message"""
    print(f"{Colors.OKCYAN}→ {text}{Colors.ENDC}")

def print_warning(text: str):
    """Print warning message"""
    print(f"{Colors.WARNING}! {text}{Colors.ENDC}")


def check_api_health() -> bool:
    """Check if API is accessible"""
    print_header("API Health Check")
    
    try:
        response = requests.get(f"{BASE_URL}/health/", timeout=10)
        if response.status_code == 200:
            print_success(f"API is healthy: {response.json()}")
            return True
        else:
            print_error(f"API returned status {response.status_code}")
            return False
    except Exception as e:
        print_error(f"Failed to connect to API: {e}")
        return False


def get_statistics() -> Dict[str, Any]:
    """Get current statistics for debates and questions"""
    print_header("Current Download Statistics")
    
    try:
        # Get debate statistics
        debate_stats = requests.get(
            f"{BASE_URL}/api/debates/statistics/",
            headers=HEADERS,
            timeout=30
        ).json()
        
        # Get LS question statistics
        ls_q_stats = requests.get(
            f"{BASE_URL}/api/questions/ls/download-statistics/",
            headers=HEADERS,
            timeout=30
        ).json()
        
        # Get RS question statistics
        rs_q_stats = requests.get(
            f"{BASE_URL}/api/questions/rs/statistics/",
            headers=HEADERS,
            timeout=30
        ).json()
        
        print(f"{Colors.BOLD}Debates:{Colors.ENDC}")
        if 'total_debates' in debate_stats:
            total = debate_stats['total_debates']
            downloaded = debate_stats.get('downloaded_debates', 0)
            pending = debate_stats.get('pending_debates', 0)
            print(f"  Total: {total}")
            print(f"  Downloaded: {downloaded}/{total} ({downloaded/total*100:.1f}%)" if total > 0 else "  Downloaded: 0")
            print(f"  Pending: {pending}")
            
            # Breakdown by institution
            by_inst = debate_stats.get('by_institution', {})
            if by_inst:
                for inst_name, inst_stats in by_inst.items():
                    inst_total = inst_stats.get('total', 0)
                    inst_with_url = inst_stats.get('with_pdf_url', 0)
                    inst_downloaded = inst_stats.get('downloaded', 0)
                    print(f"    • {inst_name}: {inst_downloaded}/{inst_with_url} downloaded ({inst_with_url - inst_downloaded} pending)")
        
        print(f"\n{Colors.BOLD}LS Questions:{Colors.ENDC}")
        if 'total_questions' in ls_q_stats:
            total = ls_q_stats['total_questions']
            with_url = ls_q_stats.get('questions_with_pdf', 0)
            downloaded = ls_q_stats.get('pdfs_downloaded', 0)
            print(f"  Total: {total}")
            print(f"  With PDF URL: {with_url}/{total} ({with_url/total*100:.1f}%)" if total > 0 else "  With PDF URL: 0")
            print(f"  Downloaded: {downloaded}/{with_url} ({downloaded/with_url*100:.1f}%)" if with_url > 0 else "  Downloaded: 0")
            print(f"  Pending: {with_url - downloaded}")
        
        print(f"\n{Colors.BOLD}RS Questions:{Colors.ENDC}")
        rs_data = rs_q_stats.get('data', {})
        if rs_data:
            total = rs_data.get('total_questions', 0)
            with_url = rs_data.get('questions_with_pdf_url', 0)
            downloaded = rs_data.get('pdfs_downloaded', 0)
            print(f"  Total: {total}")
            print(f"  With PDF URL: {with_url}/{total} ({with_url/total*100:.1f}%)" if total > 0 else "  With PDF URL: 0")
            print(f"  Downloaded: {downloaded}/{with_url} ({downloaded/with_url*100:.1f}%)" if with_url > 0 else "  Downloaded: 0")
            print(f"  Pending: {with_url - downloaded}")
        
        return {
            'debate_stats': debate_stats,
            'ls_q_stats': ls_q_stats,
            'rs_q_stats': rs_q_stats
        }
        
    except Exception as e:
        print_error(f"Failed to fetch statistics: {e}")
        return {}


def get_ls_questions_for_download(limit: int = 100) -> List[int]:
    """Get random LS questions that have PDF URLs"""
    print_header(f"Fetching LS Questions (limit: {limit})")
    
    try:
        # Fetch master data with PDF URLs
        response = requests.get(
            f"{BASE_URL}/api/questions/ls/master-data/list/",
            headers=HEADERS,
            params={
                "limit": limit,
                "lok_sabha_number": "18",  # Current Lok Sabha
                "is_processed": "false"  # Not yet processed
            },
            timeout=30
        )
        
        if response.status_code == 200:
            data = response.json()
            master_data = data.get("master_data", [])
            
            # Filter questions that have PDF URLs
            questions_with_pdfs = [
                q for q in master_data 
                if q.get("has_pdf_url") and not q.get("is_processed")
            ]
            
            print_success(f"Found {len(questions_with_pdfs)} LS questions with PDF URLs")
            
            # Get IDs
            question_ids = [q["id"] for q in questions_with_pdfs]
            return question_ids
            
        else:
            print_error(f"Failed to fetch LS questions: {response.status_code}")
            print_error(f"Response: {response.text}")
            return []
            
    except Exception as e:
        print_error(f"Error fetching LS questions: {e}")
        return []


def get_rs_questions_for_download(limit: int = 100) -> List[int]:
    """Get random RS questions that have PDF URLs"""
    print_header(f"Fetching RS Questions (limit: {limit})")
    
    try:
        # Fetch RS master data with PDF URLs
        response = requests.get(
            f"{BASE_URL}/api/questions/rs/master-data/list/",
            headers=HEADERS,
            params={
                "limit": limit,
                "has_pdf": "true",
                "session_number": "268"  # Recent session
            },
            timeout=30
        )
        
        if response.status_code == 200:
            data = response.json()
            questions = data.get("data", {}).get("questions", [])
            
            print_success(f"Found {len(questions)} RS questions with PDF URLs")
            
            # Get IDs
            question_ids = [q["id"] for q in questions if not q.get("pdf_downloaded")]
            return question_ids
            
        else:
            print_error(f"Failed to fetch RS questions: {response.status_code}")
            print_error(f"Response: {response.text}")
            return []
            
    except Exception as e:
        print_error(f"Error fetching RS questions: {e}")
        return []


def schedule_ls_question_downloads(question_ids: List[int], count: int = 50) -> Dict[str, Any]:
    """Schedule LS question PDF downloads"""
    print_header(f"Scheduling LS Question Downloads ({count} questions)")
    
    # Select random questions
    selected_ids = random.sample(question_ids, min(count, len(question_ids)))
    
    print_info(f"Selected {len(selected_ids)} random LS question master data IDs")
    print_info(f"Master Data IDs: {selected_ids[:10]}{'...' if len(selected_ids) > 10 else ''}")
    
    try:
        # Use master-data/bulk-download endpoint for master data IDs
        response = requests.post(
            f"{BASE_URL}/api/questions/ls/master-data/bulk-download/",
            headers=HEADERS,
            json={
                "limit": count,
                "use_celery": True
            },
            timeout=30
        )
        
        if response.status_code == 200:
            result = response.json()
            print_success("LS question downloads scheduled successfully!")
            print_info(f"Task ID: {result.get('task_id')}")
            print_info(f"Questions queued: {result.get('questions_queued')}")
            return result
        else:
            print_error(f"Failed to schedule LS downloads: {response.status_code}")
            print_error(f"Response: {response.text}")
            return {}
            
    except Exception as e:
        print_error(f"Error scheduling LS downloads: {e}")
        return {}


def schedule_rs_question_downloads(question_ids: List[int], count: int = 50) -> Dict[str, Any]:
    """Schedule RS question PDF downloads"""
    print_header(f"Scheduling RS Question Downloads ({count} questions)")
    
    # Select random questions
    selected_ids = random.sample(question_ids, min(count, len(question_ids)))
    
    print_info(f"Selected {len(selected_ids)} random RS questions")
    print_info(f"Question IDs: {selected_ids[:10]}{'...' if len(selected_ids) > 10 else ''}")
    
    try:
        response = requests.post(
            f"{BASE_URL}/api/questions/rs/bulk-download/",
            headers=HEADERS,
            json={
                "master_data_ids": selected_ids
            },
            timeout=30
        )
        
        if response.status_code == 200:
            result = response.json()
            print_success("RS question downloads scheduled successfully!")
            print_info(f"Task ID: {result.get('data', {}).get('task_id')}")
            print_info(f"Questions queued: {result.get('data', {}).get('questions_queued')}")
            return result
        else:
            print_error(f"Failed to schedule RS downloads: {response.status_code}")
            print_error(f"Response: {response.text}")
            return {}
            
    except Exception as e:
        print_error(f"Error scheduling RS downloads: {e}")
        return {}


def get_debate_ids_for_download(count: int = 100) -> List[int]:
    """Get debate IDs that need PDF downloads"""
    print_header(f"Fetching Debates for Download (limit: {count})")
    
    try:
        # Search for debates that haven't been downloaded
        response = requests.get(
            f"{BASE_URL}/api/debates/search/",
            headers=HEADERS,
            params={
                "status": "pending",
                "loksabha": "18"
            },
            timeout=30
        )
        
        if response.status_code == 200:
            data = response.json()
            debates = data.get("results", [])
            
            # Filter debates that are not downloaded
            pending_debates = [
                d for d in debates 
                if not d.get("is_downloaded")
            ]
            
            print_success(f"Found {len(pending_debates)} pending debates")
            
            # Get IDs
            debate_ids = [d["id"] for d in pending_debates]
            return debate_ids
            
        else:
            print_error(f"Failed to fetch debates: {response.status_code}")
            print_error(f"Response: {response.text}")
            return []
            
    except Exception as e:
        print_error(f"Error fetching debates: {e}")
        return []


def schedule_debate_scraping(count: int = 50) -> Dict[str, Any]:
    """Schedule debate scraping for a specific session"""
    print_header(f"Scheduling Debate Scraping")
    
    print_info("Scheduling scraping for LS 18, Session 5")
    
    try:
        response = requests.post(
            f"{BASE_URL}/api/debates/start-scraping/",
            headers=HEADERS,
            json={
                "loksabha_no": "18",
                "session_no": "5",
                "download_pdfs": True,
                "job_name": f"Test Scraping Job - {datetime.now().strftime('%Y-%m-%d %H:%M')}"
            },
            timeout=30
        )
        
        if response.status_code == 200:
            result = response.json()
            print_success("Debate scraping scheduled successfully!")
            print_info(f"Job ID: {result.get('job_id')}")
            print_info(f"Task ID: {result.get('task_id')}")
            print_info(f"Status: {result.get('status')}")
            return result
        elif response.status_code == 400:
            # Job might already be running
            result = response.json()
            if "already running" in result.get("error", "").lower():
                print_warning("A debate scraping job is already running for this session")
                print_info(f"Active job ID: {result.get('active_job_id')}")
                return result
            else:
                print_error(f"Failed to schedule debate scraping: {result.get('error')}")
                return {}
        else:
            print_error(f"Failed to schedule debate scraping: {response.status_code}")
            print_error(f"Response: {response.text}")
            return {}
            
    except Exception as e:
        print_error(f"Error scheduling debate scraping: {e}")
        return {}


def schedule_debate_downloads(debate_ids: List[int], count: int = 50) -> Dict[str, Any]:
    """Schedule debate PDF downloads"""
    print_header(f"Scheduling Debate Downloads ({count} debates)")
    
    if not debate_ids:
        print_warning("No debate IDs available, using download_all_pending instead")
        
        try:
            response = requests.post(
                f"{BASE_URL}/api/debates/bulk-download/",
                headers=HEADERS,
                json={
                    "download_all_pending": True
                },
                timeout=30
            )
            
            if response.status_code == 200:
                result = response.json()
                print_success("All pending debates queued for download!")
                print_info(f"Queued count: {result.get('queued_count')}")
                return result
            else:
                print_error(f"Failed to schedule debate downloads: {response.status_code}")
                return {}
                
        except Exception as e:
            print_error(f"Error scheduling debate downloads: {e}")
            return {}
    
    # Select random debates
    selected_ids = random.sample(debate_ids, min(count, len(debate_ids)))
    
    print_info(f"Selected {len(selected_ids)} random debates")
    print_info(f"Debate IDs: {selected_ids[:10]}{'...' if len(selected_ids) > 10 else ''}")
    
    try:
        response = requests.post(
            f"{BASE_URL}/api/debates/bulk-download/",
            headers=HEADERS,
            json={
                "debate_ids": selected_ids
            },
            timeout=30
        )
        
        if response.status_code == 200:
            result = response.json()
            print_success("Debate downloads scheduled successfully!")
            print_info(f"Queued count: {result.get('queued_count')}")
            print_info(f"Already downloaded: {result.get('already_downloaded', 0)}")
            return result
        else:
            print_error(f"Failed to schedule debate downloads: {response.status_code}")
            print_error(f"Response: {response.text}")
            return {}
            
    except Exception as e:
        print_error(f"Error scheduling debate downloads: {e}")
        return {}


def check_task_status(task_id: str, task_type: str = "ls_question") -> Dict[str, Any]:
    """Check status of a task"""
    endpoints = {
        "ls_question": f"/api/questions/ls/task-status/{task_id}/",
        "rs_question": f"/api/questions/rs/task-status/{task_id}/",
        "debate": f"/api/debates/task-status/{task_id}/"
    }
    
    endpoint = endpoints.get(task_type, endpoints["ls_question"])
    
    try:
        response = requests.get(
            f"{BASE_URL}{endpoint}",
            headers=HEADERS,
            timeout=10
        )
        
        if response.status_code == 200:
            return response.json()
        else:
            return {}
            
    except Exception as e:
        print_error(f"Error checking task status: {e}")
        return {}


def monitor_tasks(task_info: Dict[str, Any], duration: int = 60):
    """Monitor tasks for a specified duration"""
    print_header(f"Monitoring Tasks for {duration} seconds")
    
    start_time = time.time()
    
    while time.time() - start_time < duration:
        print(f"\n{Colors.BOLD}--- Status Update ({int(time.time() - start_time)}s elapsed) ---{Colors.ENDC}")
        
        # Check LS question task
        if task_info.get("ls_question_task_id"):
            status = check_task_status(task_info["ls_question_task_id"], "ls_question")
            if status:
                print_info(f"LS Questions: {status.get('status', 'unknown').upper()}")
        
        # Check RS question task
        if task_info.get("rs_question_task_id"):
            status = check_task_status(task_info["rs_question_task_id"], "rs_question")
            if status:
                print_info(f"RS Questions: {status.get('status', 'unknown').upper()}")
        
        # Check debate task
        if task_info.get("debate_task_id"):
            status = check_task_status(task_info["debate_task_id"], "debate")
            if status:
                print_info(f"Debates: {status.get('status', 'unknown').upper()}")
        
        time.sleep(10)  # Check every 10 seconds
    
    print_success(f"Monitoring complete after {duration} seconds")


def print_summary(results: Dict[str, Any]):
    """Print summary of all scheduled tasks"""
    print_header("Summary of Scheduled Tasks")
    
    print(f"{Colors.BOLD}Tasks Scheduled:{Colors.ENDC}")
    print(f"  • LS Questions: {results.get('ls_questions_count', 0)} questions")
    print(f"  • RS Questions: {results.get('rs_questions_count', 0)} questions")
    print(f"  • Debates: {results.get('debates_count', 0)} debates")
    
    print(f"\n{Colors.BOLD}Task IDs:{Colors.ENDC}")
    if results.get('ls_question_task_id'):
        print(f"  • LS Questions: {results['ls_question_task_id']}")
    if results.get('rs_question_task_id'):
        print(f"  • RS Questions: {results['rs_question_task_id']}")
    if results.get('debate_task_id'):
        print(f"  • Debates: {results['debate_task_id']}")
    
    print(f"\n{Colors.BOLD}Monitoring Instructions:{Colors.ENDC}")
    print(f"  1. Access Flower via SSH tunnel:")
    print(f"     ssh -L 5555:localhost:5555 tusharanand@api.opensansad.co.in")
    print(f"     Then open: http://localhost:5555/flower/")
    print(f"  ")
    print(f"  2. Check task status via API:")
    if results.get('ls_question_task_id'):
        print(f"     curl -H 'Authorization: Token {TOKEN}' \\")
        print(f"       {BASE_URL}/api/questions/ls/task-status/{results['ls_question_task_id']}/")
    
    print(f"\n  3. View live logs on server:")
    print(f"     ssh tusharanand@api.opensansad.co.in")
    print(f"     sudo tail -f /var/log/parliament_api/celery-worker.log")
    
    print(f"\n  4. Check statistics:")
    print(f"     curl -H 'Authorization: Token {TOKEN}' \\")
    print(f"       {BASE_URL}/api/questions/ls/download-statistics/")


def main():
    """Main function"""
    print_header("Parliament API PDF Download Test Script")
    print(f"Base URL: {BASE_URL}")
    print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    results = {}
    
    # Step 1: Check API health
    if not check_api_health():
        print_error("API is not accessible. Exiting.")
        return
    
    # Step 2: Show current statistics
    stats = get_statistics()
    
    # Step 3: Fetch LS questions
    ls_question_ids = get_ls_questions_for_download(limit=100)
    if ls_question_ids:
        ls_result = schedule_ls_question_downloads(ls_question_ids, count=50)
        if ls_result:
            results['ls_question_task_id'] = ls_result.get('task_id')
            results['ls_questions_count'] = ls_result.get('questions_queued', 0)
    
    time.sleep(2)  # Brief pause between requests
    
    # Step 4: Fetch RS questions
    rs_question_ids = get_rs_questions_for_download(limit=100)
    if rs_question_ids:
        rs_result = schedule_rs_question_downloads(rs_question_ids, count=50)
        if rs_result:
            results['rs_question_task_id'] = rs_result.get('data', {}).get('task_id')
            results['rs_questions_count'] = rs_result.get('data', {}).get('questions_queued', 0)
    
    time.sleep(2)  # Brief pause between requests
    
    # Step 5: Schedule debate scraping
    debate_result = schedule_debate_scraping(count=50)
    if debate_result:
        results['debate_task_id'] = debate_result.get('task_id')
        results['debate_job_id'] = debate_result.get('job_id')
    
    time.sleep(2)  # Brief pause
    
    # Step 6: Get and schedule debate downloads
    debate_ids = get_debate_ids_for_download(count=100)
    if debate_ids or not debate_result:
        # Only schedule downloads if we haven't just started a scraping job
        if not debate_result:
            debate_download_result = schedule_debate_downloads(debate_ids, count=50)
            if debate_download_result:
                results['debates_count'] = debate_download_result.get('queued_count', 0)
    
    # Step 7: Print summary
    print_summary(results)
    
    # Step 8: Optionally monitor tasks
    print(f"\n{Colors.BOLD}Monitor tasks? (y/n):{Colors.ENDC} ", end="")
    try:
        choice = input().strip().lower()
        if choice == 'y':
            monitor_tasks(results, duration=120)
    except KeyboardInterrupt:
        print("\n\nMonitoring interrupted.")
    
    print_header("Test Complete")
    print_success("All tasks have been scheduled successfully!")
    print_info("Check Flower or logs to monitor progress.")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print(f"\n\n{Colors.WARNING}Script interrupted by user.{Colors.ENDC}")
    except Exception as e:
        print_error(f"Unexpected error: {e}")
        import traceback
        traceback.print_exc()

