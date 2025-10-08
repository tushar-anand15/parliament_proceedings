#!/usr/bin/env python3
"""
Parliament API Batch Download Scheduler and Monitor

Schedules downloads in batches and monitors progress in real-time.
Shows statistics updates DURING wait periods between batches.

Usage:
    python batch_download_and_monitor.py --batches 5
    python batch_download_and_monitor.py --monitor-only
    python batch_download_and_monitor.py --type ls --batches 10
"""

import requests
import time
import sys
import argparse
import redis
import subprocess
from datetime import datetime
from typing import Dict, List, Any, Optional

# Configuration
BASE_URL = "https://api.opensansad.co.in"
TOKEN = "***REMOVED_SECRET***"

# Queue monitoring configuration
MAX_QUEUE_SIZE = 10000  # Maximum acceptable queue size before pausing
QUEUE_CHECK_INTERVAL = 30  # How often to check queue when waiting
REDIS_HOST = 'localhost'
REDIS_PORT = 6379
REDIS_DB = 0

HEADERS = {
    "Authorization": f"Token {TOKEN}",
    "Content-Type": "application/json",
    "Accept": "application/json, text/plain, */*",
    "Origin": "https://www.opensansad.co.in",
    "Referer": "https://www.opensansad.co.in/",
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36"
}

# Colors
class Colors:
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKCYAN = '\033[96m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    MAGENTA = '\033[95m'


def get_redis_connection() -> Optional[redis.Redis]:
    """Get Redis connection for queue monitoring"""
    try:
        r = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, db=REDIS_DB, decode_responses=True)
        r.ping()
        return r
    except (redis.ConnectionError, redis.TimeoutError) as e:
        print(f"{Colors.WARNING}Warning: Could not connect to Redis: {e}{Colors.ENDC}")
        return None


def get_celery_queue_length() -> Dict[str, Any]:
    """Get current Celery queue lengths and worker status"""
    result = {
        'queue_length': 0,
        'active_tasks': 0,
        'reserved_tasks': 0,
        'workers': 0,
        'error': None
    }
    
    try:
        # Try Redis first
        r = get_redis_connection()
        if r:
            # Check main celery queue
            queue_length = r.llen('celery')
            result['queue_length'] = queue_length
            
            # Check for reserved tasks (being processed)
            reserved_count = 0
            for key in r.keys('celery-task-meta-*'):
                try:
                    task_data = r.get(key)
                    if task_data and 'PENDING' in str(task_data):
                        reserved_count += 1
                except:
                    pass
            result['reserved_tasks'] = reserved_count
            
            # Try to get worker count from Celery inspect
            try:
                from celery import Celery
                app = Celery('parliament_api', broker=f'redis://{REDIS_HOST}:{REDIS_PORT}/{REDIS_DB}')
                inspect = app.control.inspect()
                active = inspect.active()
                if active:
                    result['workers'] = len(active.keys())
                    result['active_tasks'] = sum(len(tasks) for tasks in active.values())
            except:
                # Fallback to process count
                try:
                    ps_output = subprocess.check_output(['ps', 'aux'], text=True)
                    worker_count = ps_output.count('celery -A parliament_api worker')
                    result['workers'] = worker_count
                except:
                    pass
        else:
            # Fallback to command line
            try:
                queue_output = subprocess.check_output(
                    ['redis-cli', 'LLEN', 'celery'],
                    text=True,
                    stderr=subprocess.DEVNULL
                ).strip()
                result['queue_length'] = int(queue_output)
            except (subprocess.CalledProcessError, ValueError) as e:
                result['error'] = f"Could not check queue: {e}"
                
    except Exception as e:
        result['error'] = f"Queue check failed: {e}"
    
    return result


def display_queue_status(queue_info: Dict[str, Any], prefix: str = ""):
    """Display queue status information"""
    if queue_info.get('error'):
        print(f"{prefix}{Colors.WARNING}Queue status unavailable: {queue_info['error']}{Colors.ENDC}")
        return
    
    queue_length = queue_info.get('queue_length', 0)
    active_tasks = queue_info.get('active_tasks', 0)
    workers = queue_info.get('workers', 0)
    
    # Color code based on queue size
    if queue_length == 0:
        color = Colors.OKGREEN
        status = "Empty"
    elif queue_length < 1000:
        color = Colors.OKGREEN
        status = "Healthy"
    elif queue_length < 5000:
        color = Colors.OKCYAN
        status = "Moderate"
    elif queue_length < 10000:
        color = Colors.WARNING
        status = "High"
    else:
        color = Colors.FAIL
        status = "OVERLOADED"
    
    print(f"{prefix}{Colors.BOLD}Queue Status:{Colors.ENDC} "
          f"{color}{queue_length:,} pending{Colors.ENDC} ({status}) | "
          f"Active: {active_tasks} | Workers: {workers}")


def wait_for_queue_to_clear(max_queue_size: int = MAX_QUEUE_SIZE, 
                           check_interval: int = QUEUE_CHECK_INTERVAL,
                           max_wait_time: int = 1800) -> bool:
    """Wait for the queue to drop below threshold before continuing
    
    Args:
        max_queue_size: Maximum acceptable queue size
        check_interval: How often to check the queue (seconds)
        max_wait_time: Maximum time to wait (seconds)
    
    Returns:
        True if queue cleared, False if timeout
    """
    start_time = time.time()
    initial_queue_info = get_celery_queue_length()
    initial_size = initial_queue_info.get('queue_length', 0)
    
    if initial_size <= max_queue_size:
        return True
    
    print(f"\n{Colors.WARNING}⚠ Queue has {initial_size:,} pending tasks (threshold: {max_queue_size:,}){Colors.ENDC}")
    print(f"{Colors.YELLOW}Waiting for queue to clear before scheduling more tasks...{Colors.ENDC}")
    print(f"Will check every {check_interval}s (max wait: {max_wait_time}s)\n")
    
    check_count = 0
    last_size = initial_size
    
    while (time.time() - start_time) < max_wait_time:
        check_count += 1
        elapsed = int(time.time() - start_time)
        
        # Get current queue status
        queue_info = get_celery_queue_length()
        current_size = queue_info.get('queue_length', 0)
        
        # Calculate processing rate
        if current_size < last_size:
            rate = (last_size - current_size) / check_interval
            eta_seconds = int(current_size / rate) if rate > 0 else 0
            eta_minutes = eta_seconds // 60
            eta_str = f" | ETA: {eta_minutes}m" if rate > 0 else ""
        else:
            eta_str = ""
        
        # Display status
        print(f"  Check #{check_count} [{elapsed}s]: ", end='')
        display_queue_status(queue_info, prefix="")
        
        if current_size > last_size:
            print(f"    {Colors.WARNING}⚠ Queue is growing! ({current_size - last_size:+,} items){Colors.ENDC}")
        elif current_size < last_size:
            print(f"    {Colors.OKGREEN}✓ Processing... (-{last_size - current_size:,} items){eta_str}{Colors.ENDC}")
        
        last_size = current_size
        
        # Check if queue is clear enough
        if current_size <= max_queue_size:
            print(f"\n{Colors.OKGREEN}✓ Queue cleared to acceptable level ({current_size:,} <= {max_queue_size:,}){Colors.ENDC}")
            return True
        
        # Get current download stats
        stats = get_statistics()
        if stats:
            print("    ", end='')
            display_compact_stats(stats, prefix="")
        
        # Wait before next check
        time.sleep(check_interval)
    
    print(f"\n{Colors.FAIL}✗ Timeout waiting for queue to clear (waited {max_wait_time}s){Colors.ENDC}")
    print(f"Queue still has {last_size:,} pending tasks")
    return False


def fetch_with_retry(url, headers, max_retries=3, timeout=90):
    """Fetch URL with retry logic"""
    for attempt in range(max_retries):
        try:
            response = requests.get(url, headers=headers, timeout=timeout)
            response.raise_for_status()
            return response
        except (requests.RequestException, requests.Timeout) as e:
            if attempt < max_retries - 1:
                print(f"Attempt {attempt + 1} failed for {url}, retrying in 5s...")
                time.sleep(5)
            else:
                raise e
    return None

def get_statistics() -> Dict[str, Any]:
    """Get current download statistics - OPTIMIZED"""
    try:
        # Use FAST endpoints with retry (optimized for monitoring)
        debate_response = fetch_with_retry(
            f"{BASE_URL}/api/debates/download-stats/",
            headers=HEADERS,
            timeout=30
        )
        debate_stats = debate_response.json()
        
        # Use FAST questions endpoint with retry (both LS and RS in one call)
        questions_response = fetch_with_retry(
            f"{BASE_URL}/api/questions/fast-stats/",
            headers=HEADERS,
            timeout=30
        )
        questions_stats = questions_response.json()
        
        # Transform to match old format
        return {
            'debates': debate_stats,
            'ls_questions': {
                'master_data_statistics': {
                    'pdf_availability': {
                        'with_pdf': questions_stats['lok_sabha']['total_with_pdf']
                    }
                },
                'download_statistics': {
                    'master_data': {
                        'pdfs_downloaded': questions_stats['lok_sabha']['downloaded']
                    }
                }
            },
            'rs_questions': {
                'data': {
                    'pdf_download_status': {
                        'questions_with_pdf_url': questions_stats['rajya_sabha']['total_with_pdf'],
                        'pdfs_downloaded': questions_stats['rajya_sabha']['downloaded']
                    }
                }
            },
            '_raw_responses': {
                'debates_status': debate_response.status_code,
                'questions_status': questions_response.status_code
            }
        }
    except Exception as e:
        print(f"{Colors.FAIL}Error fetching statistics: {e}{Colors.ENDC}")
        import traceback
        traceback.print_exc()
        return {}


def display_compact_stats(stats: Dict[str, Any], prefix: str = ""):
    """Display compact single-line statistics"""
    if not stats:
        print(f"{prefix}Stats unavailable")
        return
    
    # Extract LS Questions stats
    ls_q = stats.get('ls_questions', {})
    ls_master_stats = ls_q.get('master_data_statistics', {})
    ls_download_stats = ls_q.get('download_statistics', {})
    ls_downloaded = ls_download_stats.get('master_data', {}).get('pdfs_downloaded', 0)
    ls_total = ls_master_stats.get('pdf_availability', {}).get('with_pdf', 0)
    
    # Extract RS Questions stats
    rs_data = stats.get('rs_questions', {}).get('data', {})
    rs_pdf_status = rs_data.get('pdf_download_status', {})
    # Try new format first, fallback to old format
    rs_downloaded = rs_pdf_status.get('pdfs_downloaded', 0)
    rs_total = rs_pdf_status.get('questions_with_pdf_url', 0)
    # Fallback to old format if new fields not present
    if rs_total == 0 and rs_data:
        rs_total = rs_data.get('pdf_availability', {}).get('with_pdf', 0)
    
    # Extract Debates stats
    debates = stats.get('debates', {})
    debates_total = debates.get('total_debates', 0)
    status_breakdown = debates.get('status_breakdown', {})
    debates_downloaded = status_breakdown.get('completed', 0)
    
    # Calculate totals
    total_downloaded = ls_downloaded + rs_downloaded + debates_downloaded
    total = ls_total + rs_total + debates_total
    
    pct = (total_downloaded / total * 100) if total > 0 else 0
    
    # Also show queue status inline if available
    queue_info = get_celery_queue_length()
    queue_str = ""
    if not queue_info.get('error'):
        queue_length = queue_info.get('queue_length', 0)
        if queue_length > 0:
            queue_color = Colors.FAIL if queue_length > 10000 else Colors.WARNING if queue_length > 5000 else Colors.OKCYAN
            queue_str = f" | {queue_color}Queue: {queue_length:,}{Colors.ENDC}"
    
    print(f"{prefix}{Colors.BOLD}Progress:{Colors.ENDC} LS:{Colors.OKGREEN}{ls_downloaded:,}{Colors.ENDC}/{ls_total:,} | RS:{Colors.OKGREEN}{rs_downloaded:,}{Colors.ENDC}/{rs_total:,} | Debates:{Colors.OKGREEN}{debates_downloaded:,}{Colors.ENDC}/{debates_total:,} | {Colors.BOLD}Total: {total_downloaded:,}/{total:,} ({pct:.1f}%){Colors.ENDC}{queue_str}")


def display_full_stats(stats: Dict[str, Any]):
    """Display detailed statistics"""
    print(f"\n{Colors.HEADER}{Colors.BOLD}{'='*80}{Colors.ENDC}")
    print(f"{Colors.HEADER}{Colors.BOLD}{'DOWNLOAD PROGRESS':^80}{Colors.ENDC}")
    print(f"{Colors.HEADER}{Colors.BOLD}{'='*80}{Colors.ENDC}\n")
    
    if not stats:
        print(f"{Colors.WARNING}No statistics available{Colors.ENDC}")
        return
    
    # Debates
    debate_stats = stats.get('debates', {})
    if debate_stats:
        total = debate_stats.get('total_debates', 0)
        status_breakdown = debate_stats.get('status_breakdown', {})
        downloaded = status_breakdown.get('completed', 0)
        pending = status_breakdown.get('pending', 0)
        failed = status_breakdown.get('failed', 0)
        pct = (downloaded / total * 100) if total > 0 else 0
        
        print(f"{Colors.BOLD}DEBATES:{Colors.ENDC}")
        print(f"  Downloaded: {Colors.OKGREEN}{downloaded:,}{Colors.ENDC} / {total:,} ({pct:.1f}%)")
        print(f"  Pending: {pending:,}")
        if failed > 0:
            print(f"  Failed: {Colors.FAIL}{failed:,}{Colors.ENDC}")
    
    # LS Questions
    ls_q = stats.get('ls_questions', {})
    ls_master_stats = ls_q.get('master_data_statistics', {})
    ls_download_stats = ls_q.get('download_statistics', {})
    if ls_master_stats or ls_download_stats:
        with_url = ls_master_stats.get('pdf_availability', {}).get('with_pdf', 0)
        downloaded = ls_download_stats.get('master_data', {}).get('pdfs_downloaded', 0)
        pct = (downloaded / with_url * 100) if with_url > 0 else 0
        
        print(f"\n{Colors.BOLD}LOK SABHA QUESTIONS:{Colors.ENDC}")
        print(f"  Downloaded: {Colors.OKGREEN}{downloaded:,}{Colors.ENDC} / {with_url:,} ({pct:.1f}%)")
        print(f"  Remaining: {with_url - downloaded:,}")
    
    # RS Questions
    rs_data = stats.get('rs_questions', {}).get('data', {})
    if rs_data:
        rs_pdf_status = rs_data.get('pdf_download_status', {})
        # Try new format first, fallback to old format
        with_url = rs_pdf_status.get('questions_with_pdf_url', 0)
        downloaded = rs_pdf_status.get('pdfs_downloaded', 0)
        # Fallback to old format if new fields not present
        if with_url == 0:
            with_url = rs_data.get('pdf_availability', {}).get('with_pdf', 0)
        
        pct = (downloaded / with_url * 100) if with_url > 0 else 0
        
        print(f"\n{Colors.BOLD}RAJYA SABHA QUESTIONS:{Colors.ENDC}")
        print(f"  Downloaded: {Colors.OKGREEN}{downloaded:,}{Colors.ENDC} / {with_url:,} ({pct:.1f}%)")
        print(f"  Remaining: {with_url - downloaded:,}")
    
    print(f"\n{Colors.BOLD}{'='*80}{Colors.ENDC}")
    
    # Add queue status to full stats display
    queue_info = get_celery_queue_length()
    print(f"\n{Colors.BOLD}CELERY QUEUE:{Colors.ENDC}")
    display_queue_status(queue_info, prefix="  ")


def calculate_proportional_batch_sizes(base_batch_size: int) -> Dict[str, int]:
    """Calculate proportional batch sizes based on total items"""
    TOTAL_LS = 378235
    TOTAL_RS = 309986
    TOTAL_DEBATES = 44179
    TOTAL_ALL = TOTAL_LS + TOTAL_RS + TOTAL_DEBATES
    
    return {
        'ls_questions': int(base_batch_size * (TOTAL_LS / TOTAL_ALL)),
        'rs_questions': int(base_batch_size * (TOTAL_RS / TOTAL_ALL)),
        'debates': int(base_batch_size * (TOTAL_DEBATES / TOTAL_ALL))
    }


def schedule_sub_batch(batch_type: str, batch_size: int, sub_batch_size: int = 50, 
                       delay_between_sub_batches: int = 5, show_progress: bool = True) -> Dict[str, Any]:
    """
    Schedule a batch download in smaller sub-batches to avoid overwhelming the queue
    
    Args:
        batch_type: Type of batch ('ls_questions', 'rs_questions', 'debates')
        batch_size: Total number of items to schedule
        sub_batch_size: Number of items to schedule in each sub-batch
        delay_between_sub_batches: Seconds to wait between sub-batches
    
    Returns:
        Dict with results including total scheduled count
    """
    scheduled_count = 0
    errors = []
    
    try:
        # Calculate number of sub-batches needed
        num_sub_batches = (batch_size + sub_batch_size - 1) // sub_batch_size
        
        if batch_type == 'ls_questions':
            # Schedule LS questions in sub-batches
            for i in range(num_sub_batches):
                current_sub_batch = min(sub_batch_size, batch_size - scheduled_count)
                if current_sub_batch <= 0:
                    break
                
                if show_progress:
                    # Show progress bar
                    progress = (i + 1) / num_sub_batches
                    bar_length = 30
                    filled_length = int(bar_length * progress)
                    bar = '█' * filled_length + '░' * (bar_length - filled_length)
                    print(f"\r    Scheduling LS: [{bar}] {i+1}/{num_sub_batches} sub-batches ({scheduled_count:,}/{batch_size:,} items)", end='', flush=True)
                
                try:
                    response = requests.post(
                        f"{BASE_URL}/api/questions/ls/master-data/bulk-download/",
                        headers=HEADERS,
                        json={
                            "limit": current_sub_batch,
                            "use_celery": True,
                            "pending_only": True  # Only schedule items without PDFs
                        },
                        timeout=90
                    )
                    
                    if response.status_code == 200:
                        result = response.json()
                        scheduled_count += current_sub_batch
                    else:
                        errors.append(f"Sub-batch {i+1}: HTTP {response.status_code}")
                    
                    # Wait between sub-batches (except after last one)
                    if i < num_sub_batches - 1 and scheduled_count < batch_size:
                        time.sleep(delay_between_sub_batches)
                        
                except Exception as e:
                    errors.append(f"Sub-batch {i+1}: {str(e)}")
            
            if show_progress:
                print()  # New line after progress bar
            
            return {
                'success': True,
                'scheduled_count': scheduled_count,
                'target': batch_size,
                'sub_batches': num_sub_batches,
                'errors': errors if errors else None
            }
        
        elif batch_type == 'rs_questions':
            # RS questions - use limit parameter WITHOUT session restriction
            for i in range(num_sub_batches):
                current_sub_batch = min(sub_batch_size, batch_size - scheduled_count)
                if current_sub_batch <= 0:
                    break
                
                if show_progress:
                    # Show progress bar
                    progress = (i + 1) / num_sub_batches
                    bar_length = 30
                    filled_length = int(bar_length * progress)
                    bar = '█' * filled_length + '░' * (bar_length - filled_length)
                    print(f"\r    Scheduling RS: [{bar}] {i+1}/{num_sub_batches} sub-batches ({scheduled_count:,}/{batch_size:,} items)", end='', flush=True)
                
                try:
                    response = requests.post(
                        f"{BASE_URL}/api/questions/rs/bulk-download/",
                        headers=HEADERS,
                        json={
                            "limit": current_sub_batch,
                            "pending_only": True  # Only schedule items without PDFs
                        },
                        timeout=90
                    )
                    
                    if response.status_code == 200:
                        result = response.json()
                        scheduled_count += current_sub_batch
                    else:
                        errors.append(f"Sub-batch {i+1}: HTTP {response.status_code}")
                    
                    if i < num_sub_batches - 1 and scheduled_count < batch_size:
                        time.sleep(delay_between_sub_batches)
                        
                except Exception as e:
                    errors.append(f"Sub-batch {i+1}: {str(e)}")
            
            if show_progress:
                print()  # New line after progress bar
            
            return {
                'success': True,
                'scheduled_count': scheduled_count,
                'target': batch_size,
                'sub_batches': num_sub_batches,
                'errors': errors if errors else None
            }
        
        elif batch_type == 'debates':
            # Get pending debates and schedule in sub-batches
            search_response = requests.get(
                f"{BASE_URL}/api/debates/search/",
                headers=HEADERS,
                params={
                    "status": "pending",  # Only get debates without PDFs
                    "limit": batch_size
                },
                timeout=90
            )
            
            if search_response.status_code != 200:
                return {'error': f'Failed to search debates: {search_response.status_code}'}
            
            debates_data = search_response.json()
            all_debate_ids = [d['id'] for d in debates_data.get('results', [])]
            
            if not all_debate_ids:
                return {'message': 'No pending debates found'}
            
            # Schedule debates in sub-batches
            total_debate_batches = (len(all_debate_ids) + sub_batch_size - 1) // sub_batch_size
            for batch_num, i in enumerate(range(0, len(all_debate_ids), sub_batch_size), 1):
                debate_ids_batch = all_debate_ids[i:i + sub_batch_size]
                
                if show_progress:
                    # Show progress bar
                    progress = batch_num / total_debate_batches
                    bar_length = 30
                    filled_length = int(bar_length * progress)
                    bar = '█' * filled_length + '░' * (bar_length - filled_length)
                    print(f"\r    Scheduling Debates: [{bar}] {batch_num}/{total_debate_batches} sub-batches ({scheduled_count:,}/{len(all_debate_ids):,} items)", end='', flush=True)
                
                try:
                    response = requests.post(
                        f"{BASE_URL}/api/debates/bulk-download/",
                        headers=HEADERS,
                        json={"debate_ids": debate_ids_batch},
                        timeout=90
                    )
                    
                    if response.status_code == 200:
                        scheduled_count += len(debate_ids_batch)
                    else:
                        errors.append(f"Sub-batch {batch_num}: HTTP {response.status_code}")
                    
                    # Wait between sub-batches (except after last one)
                    if i + sub_batch_size < len(all_debate_ids):
                        time.sleep(delay_between_sub_batches)
                        
                except Exception as e:
                    errors.append(f"Sub-batch {batch_num}: {str(e)}")
            
            if show_progress:
                print()  # New line after progress bar
            
            return {
                'success': True,
                'scheduled_count': scheduled_count,
                'target': len(all_debate_ids),
                'sub_batches': (len(all_debate_ids) + sub_batch_size - 1) // sub_batch_size,
                'errors': errors if errors else None
            }
        
        else:
            return {'error': 'Invalid batch type'}
    
    except requests.exceptions.Timeout:
        return {'warning': 'Timeout (tasks may still be queued)', 'scheduled_count': scheduled_count}
    except Exception as e:
        return {'error': str(e), 'scheduled_count': scheduled_count}


def monitor_with_countdown(duration: int, batch_num: int, total_batches: int):
    """Monitor progress while counting down to next batch"""
    start = time.time()
    update_interval = 30
    
    while time.time() - start < duration:
        elapsed = int(time.time() - start)
        remaining = duration - elapsed
        
        # Get current stats
        stats = get_statistics()
        
        # Clear previous line and show update
        print(f"\r{' ' * 100}", end='')  # Clear line
        print(f"\r  {Colors.OKCYAN}[Batch {batch_num}/{total_batches} complete | Next in {remaining}s]{Colors.ENDC} ", end='', flush=True)
        
        display_compact_stats(stats, prefix="")
        
        # Sleep until next update
        sleep_time = min(update_interval, remaining)
        if sleep_time > 0:
            time.sleep(sleep_time)
    
    print(f"\n  {Colors.OKGREEN}✓ Ready for next batch{Colors.ENDC}")


def continuous_monitor(interval: int = 30):
    """Continuously monitor and display progress"""
    iteration = 0
    start_time = time.time()
    
    try:
        while True:
            iteration += 1
            elapsed = int(time.time() - start_time)
            
            print(f"\n{Colors.HEADER}{Colors.BOLD}{'='*80}{Colors.ENDC}")
            print(f"{Colors.HEADER}{Colors.BOLD}{'CONTINUOUS MONITORING':^80}{Colors.ENDC}")
            print(f"{Colors.HEADER}{Colors.BOLD}{'='*80}{Colors.ENDC}")
            print(f"\nTime: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | Running: {elapsed}s | Update #{iteration}")
            
            # Get and display full stats
            stats = get_statistics()
            display_full_stats(stats)
            
            print(f"\n{Colors.BOLD}Monitoring:{Colors.ENDC}")
            print(f"  Flower: http://localhost:5555/flower/ (via SSH tunnel)")
            print(f"  Logs: sudo tail -f /var/log/parliament_api/celery-worker.log")
            print(f"  Next update in {interval}s (Ctrl+C to stop)")
            
            time.sleep(interval)
            
    except KeyboardInterrupt:
        print(f"\n\n{Colors.WARNING}Monitoring stopped{Colors.ENDC}")


def batch_schedule_and_monitor(
    batch_size: int = 5000,
    num_batches: int = 10,
    delay_between_batches: int = 300,
    download_type: str = 'all',
    sub_batch_size: int = 50,
    delay_between_sub_batches: int = 5,
    max_queue_size: int = MAX_QUEUE_SIZE,
    wait_for_queue: bool = True
):
    """
    Schedule downloads in batches with live monitoring between batches
    
    Args:
        batch_size: Total items per major batch
        num_batches: Number of major batches
        delay_between_batches: Seconds between major batches
        download_type: Type of downloads ('all', 'ls', 'rs', 'debates')
        sub_batch_size: Items per sub-batch (to avoid queue overflow)
        delay_between_sub_batches: Seconds between sub-batches
        max_queue_size: Maximum queue size before waiting
        wait_for_queue: Whether to wait for queue to clear before scheduling
    """
    
    print(f"{Colors.HEADER}{Colors.BOLD}{'='*80}{Colors.ENDC}")
    print(f"{Colors.HEADER}{Colors.BOLD}{'BATCH DOWNLOAD SCHEDULER & MONITOR':^80}{Colors.ENDC}")
    print(f"{Colors.HEADER}{Colors.BOLD}{'='*80}{Colors.ENDC}\n")
    
    # Calculate proportional sizes
    batch_sizes = calculate_proportional_batch_sizes(batch_size)
    
    print(f"Configuration:")
    print(f"  Base batch size: {batch_size:,} items")
    print(f"  Proportional batches:")
    print(f"    • LS Questions: {batch_sizes['ls_questions']:,} items/batch")
    print(f"    • RS Questions: {batch_sizes['rs_questions']:,} items/batch")
    print(f"    • Debates: {batch_sizes['debates']:,} items/batch")
    print(f"  Number of major batches: {num_batches}")
    print(f"  Sub-batch size: {sub_batch_size} items (to prevent queue overflow)")
    print(f"  Delay between sub-batches: {delay_between_sub_batches}s")
    print(f"  Delay between major batches: {delay_between_batches}s (with live monitoring)")
    print(f"  Download type: {download_type}")
    print(f"  Max queue size: {max_queue_size:,} items")
    print(f"  Wait for queue: {wait_for_queue}")
    print(f"  {Colors.BOLD}NOTE:{Colors.ENDC} Only scheduling items without PDFs (pending downloads)")
    
    # Initial stats and queue status
    print(f"\n{Colors.BOLD}Initial Status:{Colors.ENDC}")
    initial_stats = get_statistics()
    display_compact_stats(initial_stats, prefix="  ")
    
    # Check initial queue status
    print(f"\n{Colors.BOLD}Queue Status:{Colors.ENDC}")
    queue_info = get_celery_queue_length()
    display_queue_status(queue_info, prefix="  ")
    
    # Wait for queue to clear if needed
    if wait_for_queue:
        if not wait_for_queue_to_clear(max_queue_size, QUEUE_CHECK_INTERVAL):
            print(f"\n{Colors.WARNING}Proceeding anyway despite high queue size...{Colors.ENDC}")
    
    # Schedule batches
    print(f"\n{Colors.HEADER}{Colors.BOLD}{'='*80}{Colors.ENDC}")
    print(f"{Colors.HEADER}{Colors.BOLD}{'SCHEDULING BATCHES':^80}{Colors.ENDC}")
    print(f"{Colors.HEADER}{Colors.BOLD}{'='*80}{Colors.ENDC}\n")
    
    scheduled_tasks = []
    
    for batch_num in range(1, num_batches + 1):
        # Check queue before each batch
        if wait_for_queue and batch_num > 1:
            queue_info = get_celery_queue_length()
            queue_size = queue_info.get('queue_length', 0)
            if queue_size > max_queue_size:
                print(f"\n{Colors.WARNING}Queue check before batch {batch_num}:{Colors.ENDC}")
                if not wait_for_queue_to_clear(max_queue_size, QUEUE_CHECK_INTERVAL, 600):
                    print(f"{Colors.WARNING}Skipping batch {batch_num} due to queue overload{Colors.ENDC}")
                    continue
        
        print(f"\n{Colors.BOLD}Batch {batch_num}/{num_batches} - {datetime.now().strftime('%H:%M:%S')}:{Colors.ENDC}")
        
        # Schedule LS
        if download_type in ['all', 'ls']:
            target = batch_sizes['ls_questions']
            print(f"  {Colors.OKCYAN}Scheduling LS questions ({target:,} items in {(target + sub_batch_size - 1) // sub_batch_size} sub-batches of {sub_batch_size})...{Colors.ENDC}")
            result = schedule_sub_batch('ls_questions', target, sub_batch_size, delay_between_sub_batches, show_progress=True)
            if result.get('success'):
                scheduled = result.get('scheduled_count', 0)
                sub_batches = result.get('sub_batches', 0)
                if scheduled == target:
                    print(f"    {Colors.OKGREEN}✓ Successfully scheduled all {scheduled:,} items{Colors.ENDC}")
                else:
                    print(f"    {Colors.WARNING}⚠ Scheduled {scheduled:,}/{target:,} items{Colors.ENDC}")
                if result.get('errors'):
                    print(f"    {Colors.WARNING}⚠ Some sub-batches had errors: {len(result['errors'])} errors{Colors.ENDC}")
            elif 'error' in result:
                print(f"    {Colors.FAIL}✗ {result['error']}{Colors.ENDC}")
            else:
                print(f"    {Colors.WARNING}⚠ {result.get('message', 'Unknown result')}{Colors.ENDC}")
        
        # Schedule RS
        if download_type in ['all', 'rs']:
            target = batch_sizes['rs_questions']
            print(f"  {Colors.OKCYAN}Scheduling RS questions ({target:,} items in {(target + sub_batch_size - 1) // sub_batch_size} sub-batches of {sub_batch_size})...{Colors.ENDC}")
            result = schedule_sub_batch('rs_questions', target, sub_batch_size, delay_between_sub_batches, show_progress=True)
            if result.get('success'):
                scheduled = result.get('scheduled_count', 0)
                sub_batches = result.get('sub_batches', 0)
                if scheduled == target:
                    print(f"    {Colors.OKGREEN}✓ Successfully scheduled all {scheduled:,} items{Colors.ENDC}")
                else:
                    print(f"    {Colors.WARNING}⚠ Scheduled {scheduled:,}/{target:,} items{Colors.ENDC}")
                if result.get('errors'):
                    print(f"    {Colors.WARNING}⚠ Some sub-batches had errors: {len(result['errors'])} errors{Colors.ENDC}")
            elif 'error' in result:
                print(f"    {Colors.FAIL}✗ {result['error']}{Colors.ENDC}")
            else:
                print(f"    {Colors.WARNING}⚠ {result.get('message', 'Unknown result')}{Colors.ENDC}")
        
        # Schedule Debates
        if download_type in ['all', 'debates']:
            target = batch_sizes['debates']
            print(f"  {Colors.OKCYAN}Scheduling debates ({target:,} items in {(target + sub_batch_size - 1) // sub_batch_size} sub-batches of {sub_batch_size})...{Colors.ENDC}")
            result = schedule_sub_batch('debates', target, sub_batch_size, delay_between_sub_batches, show_progress=True)
            if result.get('success'):
                scheduled = result.get('scheduled_count', 0)
                actual_target = result.get('target', target)
                if scheduled > 0:
                    print(f"    {Colors.OKGREEN}✓ Successfully scheduled {scheduled:,} items{Colors.ENDC}")
                else:
                    print(f"    {Colors.WARNING}⚠ No items scheduled (may be all complete){Colors.ENDC}")
                if result.get('errors'):
                    print(f"    {Colors.WARNING}⚠ Some sub-batches had errors: {len(result['errors'])} errors{Colors.ENDC}")
            elif 'message' in result:
                print(f"    {Colors.WARNING}⚠ {result['message']}{Colors.ENDC}")
            elif 'error' in result:
                print(f"    {Colors.FAIL}✗ {result.get('error')}{Colors.ENDC}")
            else:
                print(f"    {Colors.WARNING}⚠ Unknown result{Colors.ENDC}")
        
        # Monitor while waiting (except after last batch)
        if batch_num < num_batches:
            monitor_with_countdown(delay_between_batches, batch_num, num_batches)
        else:
            print(f"\n{Colors.OKGREEN}✓ All batches scheduled!{Colors.ENDC}")
    
    # Summary
    print(f"\n{Colors.HEADER}{Colors.BOLD}{'='*80}{Colors.ENDC}")
    print(f"{Colors.HEADER}{Colors.BOLD}{'SCHEDULING COMPLETE':^80}{Colors.ENDC}")
    print(f"{Colors.HEADER}{Colors.BOLD}{'='*80}{Colors.ENDC}\n")
    
    print(f"{Colors.BOLD}Scheduled {len(scheduled_tasks)} tasks:{Colors.ENDC}")
    for task_type, task_id in scheduled_tasks[-10:]:  # Show last 10
        print(f"  • {task_type}: {task_id}")
    if len(scheduled_tasks) > 10:
        print(f"  ... and {len(scheduled_tasks) - 10} more")
    
    print(f"\n{Colors.BOLD}Total batches: {num_batches} | Est. items queued: ~{num_batches * batch_size:,}{Colors.ENDC}")
    
    # Switch to continuous monitoring
    print(f"\n{Colors.OKCYAN}Switching to continuous monitoring mode...{Colors.ENDC}")
    print(f"{Colors.OKCYAN}Press Ctrl+C to stop{Colors.ENDC}")
    
    time.sleep(3)
    continuous_monitor(interval=60)


def simple_monitor(interval: int = 30):
    """Just monitor without scheduling"""
    print(f"{Colors.HEADER}{Colors.BOLD}{'='*80}{Colors.ENDC}")
    print(f"{Colors.HEADER}{Colors.BOLD}{'DOWNLOAD MONITOR':^80}{Colors.ENDC}")
    print(f"{Colors.HEADER}{Colors.BOLD}{'='*80}{Colors.ENDC}\n")
    
    print(f"{Colors.OKCYAN}Monitoring download progress...{Colors.ENDC}")
    print(f"{Colors.OKCYAN}Press Ctrl+C to stop{Colors.ENDC}")
    
    continuous_monitor(interval=interval)


def main():
    parser = argparse.ArgumentParser(
        description='Parliament API Batch Download Scheduler and Monitor',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Schedule 5 batches with monitoring
  python batch_download_and_monitor.py --batches 5
  
  # Just monitor current progress
  python batch_download_and_monitor.py --monitor-only
  
  # Schedule only LS questions
  python batch_download_and_monitor.py --type ls --batches 10
  
  # Faster batching (1 min delay)
  python batch_download_and_monitor.py --batches 10 --delay 60
        """
    )
    
    parser.add_argument('--batch-size', type=int, default=5000,
                       help='Items per major batch (default: 5000)')
    parser.add_argument('--batches', type=int, default=10,
                       help='Number of major batches (default: 10)')
    parser.add_argument('--sub-batch-size', type=int, default=50,
                       help='Items per sub-batch to prevent queue overflow (default: 50)')
    parser.add_argument('--delay', type=int, default=300,
                       help='Seconds between major batches (default: 300)')
    parser.add_argument('--sub-delay', type=int, default=5,
                       help='Seconds between sub-batches (default: 5)')
    parser.add_argument('--type', choices=['all', 'ls', 'rs', 'debates'], default='all',
                       help='What to download (default: all)')
    parser.add_argument('--monitor-only', action='store_true',
                       help='Only monitor, no scheduling')
    parser.add_argument('--interval', type=int, default=30,
                       help='Monitor interval in seconds (default: 30)')
    parser.add_argument('--max-queue-size', type=int, default=MAX_QUEUE_SIZE,
                       help=f'Maximum queue size before waiting (default: {MAX_QUEUE_SIZE})')
    parser.add_argument('--no-wait-queue', action='store_true',
                       help='Do not wait for queue to clear (not recommended)')
    parser.add_argument('--check-queue', action='store_true',
                       help='Just check the current queue status and exit')
    
    args = parser.parse_args()
    
    # Test API with retry - using fast endpoint
    print(f"Testing API connection to {BASE_URL}...")
    for attempt in range(3):
        try:
            response = requests.get(f"{BASE_URL}/api/debates/download-stats/", headers=HEADERS, timeout=30)
            if response.status_code == 200:
                print(f"{Colors.OKGREEN}✓ API is accessible{Colors.ENDC}\n")
                break
            else:
                print(f"{Colors.WARNING}API returned status {response.status_code}, retrying...{Colors.ENDC}")
        except requests.exceptions.Timeout:
            print(f"{Colors.WARNING}Timeout on attempt {attempt + 1}/3, retrying...{Colors.ENDC}")
            if attempt == 2:
                print(f"{Colors.FAIL}API check failed after 3 attempts{Colors.ENDC}")
                print(f"{Colors.WARNING}Continuing anyway - API might be slow but functional{Colors.ENDC}\n")
        except Exception as e:
            print(f"{Colors.WARNING}Connection error: {e}{Colors.ENDC}")
            if attempt == 2:
                print(f"{Colors.WARNING}Continuing anyway...{Colors.ENDC}\n")
        
        time.sleep(2)
    
    try:
        # Check queue status if requested
        if args.check_queue:
            print(f"\n{Colors.BOLD}Current Queue Status:{Colors.ENDC}")
            queue_info = get_celery_queue_length()
            display_queue_status(queue_info, prefix="  ")
            
            # Show detailed info
            if not queue_info.get('error'):
                print(f"\n{Colors.BOLD}Details:{Colors.ENDC}")
                print(f"  Pending tasks: {queue_info.get('queue_length', 0):,}")
                print(f"  Active tasks: {queue_info.get('active_tasks', 0):,}")
                print(f"  Reserved tasks: {queue_info.get('reserved_tasks', 0):,}")
                print(f"  Workers: {queue_info.get('workers', 0)}")
                
                queue_size = queue_info.get('queue_length', 0)
                if queue_size > 0:
                    print(f"\n{Colors.BOLD}Recommendations:{Colors.ENDC}")
                    if queue_size > 50000:
                        print(f"  {Colors.FAIL}✗ CRITICAL: Queue is severely overloaded!{Colors.ENDC}")
                        print(f"    - Stop scheduling new tasks immediately")
                        print(f"    - Consider clearing the queue or adding more workers")
                    elif queue_size > 20000:
                        print(f"  {Colors.WARNING}⚠ Queue is very high{Colors.ENDC}")
                        print(f"    - Avoid scheduling large batches")
                        print(f"    - Wait for queue to process before adding more")
                    elif queue_size > 10000:
                        print(f"  {Colors.WARNING}⚠ Queue is elevated{Colors.ENDC}")
                        print(f"    - Schedule smaller batches")
                        print(f"    - Monitor processing rate")
                    else:
                        print(f"  {Colors.OKGREEN}✓ Queue is at acceptable level{Colors.ENDC}")
            return
        
        if args.monitor_only:
            simple_monitor(interval=args.interval)
        else:
            batch_schedule_and_monitor(
                batch_size=args.batch_size,
                num_batches=args.batches,
                delay_between_batches=args.delay,
                download_type=args.type,
                sub_batch_size=args.sub_batch_size,
                delay_between_sub_batches=args.sub_delay,
                max_queue_size=args.max_queue_size,
                wait_for_queue=not args.no_wait_queue
            )
    
    except KeyboardInterrupt:
        print(f"\n\n{Colors.WARNING}Stopped by user{Colors.ENDC}")
    except Exception as e:
        print(f"\n{Colors.FAIL}Error: {e}{Colors.ENDC}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()