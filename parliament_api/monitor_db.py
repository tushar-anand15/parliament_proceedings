#!/usr/bin/env python
"""
Real-time database monitoring script
Shows questions being added to the database as they happen
"""
import os
import sys
import django
import time
from datetime import datetime, timedelta

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'parliament_api.settings')
django.setup()

from services.questions.models import QuestionMasterData, Session, LokSabha, ParliamentInstitution
from services.debates.models import DebateMasterData
from django.utils import timezone
from django.db.models import Count

def clear_screen():
    os.system('clear' if os.name == 'posix' else 'cls')

def monitor_database():
    """Monitor all database writes in real-time"""
    
    print("🔍 Real-time Database Monitor")
    print("=" * 80)
    print("Monitoring ALL database writes (Questions, Debates, Sessions, Institutions)...")
    print("Press Ctrl+C to stop\n")
    
    # Initialize counters
    prev_questions = QuestionMasterData.objects.count()
    prev_debates = DebateMasterData.objects.count()
    prev_sessions = Session.objects.count()
    prev_lok_sabhas = LokSabha.objects.count()
    prev_institutions = ParliamentInstitution.objects.count()
    
    iteration = 0
    
    try:
        while True:
            iteration += 1
            five_secs_ago = timezone.now() - timedelta(seconds=5)
            
            # Current counts
            curr_questions = QuestionMasterData.objects.count()
            curr_debates = DebateMasterData.objects.count()
            curr_sessions = Session.objects.count()
            curr_lok_sabhas = LokSabha.objects.count()
            curr_institutions = ParliamentInstitution.objects.count()
            
            # Calculate differences
            questions_diff = curr_questions - prev_questions
            debates_diff = curr_debates - prev_debates
            sessions_diff = curr_sessions - prev_sessions
            lok_sabhas_diff = curr_lok_sabhas - prev_lok_sabhas
            institutions_diff = curr_institutions - prev_institutions
            
            # Clear and redraw
            if iteration % 10 == 0:  # Full refresh every 10 iterations
                clear_screen()
                print("🔍 Real-time Database Monitor")
                print("=" * 80)
            
            timestamp = datetime.now().strftime("%H:%M:%S")
            print(f"\n[{timestamp}] Database Activity Summary:")
            print(f"  📊 Questions: {curr_questions:,} (+{questions_diff} in last 5s)")
            print(f"  🏛️  Debates: {curr_debates:,} (+{debates_diff} in last 5s)")
            print(f"  📅 Sessions: {curr_sessions:,} (+{sessions_diff} in last 5s)")
            print(f"  🏛️  Lok Sabhas: {curr_lok_sabhas:,} (+{lok_sabhas_diff} in last 5s)")
            print(f"  🏛️  Institutions: {curr_institutions:,} (+{institutions_diff} in last 5s)")
            
            # Show recent activity by type
            total_activity = questions_diff + debates_diff + sessions_diff + lok_sabhas_diff + institutions_diff
            
            if total_activity > 0:
                print(f"\n  ⚡ Total Activity: +{total_activity} records in last 5s")
                
                # Show most active type
                activity_types = [
                    ("Questions", questions_diff),
                    ("Debates", debates_diff),
                    ("Sessions", sessions_diff),
                    ("Lok Sabhas", lok_sabhas_diff),
                    ("Institutions", institutions_diff)
                ]
                active_type = max(activity_types, key=lambda x: x[1])
                if active_type[1] > 0:
                    print(f"  🔥 Most Active: {active_type[0]} (+{active_type[1]})")
                
                # Show rate
                rate_per_min = (total_activity / 5) * 60
                print(f"  📈 Write rate: ~{rate_per_min:.0f} records/minute")
            else:
                print(f"\n  ⏸  No database writes in last 5 seconds...")
            
            # Show recent database writes activity
            if total_activity > 0:
                print(f"\n  🔥 Recent Database Writes:")
                
                # Questions created in last 5 seconds
                if questions_diff > 0:
                    recent_questions = QuestionMasterData.objects.filter(
                        created_at__gte=five_secs_ago
                    ).values('lok_sabha_number', 'session_number').annotate(
                        count=Count('id')
                    ).order_by('-count')[:3]
                    
                    for session in recent_questions:
                        ls_no = session['lok_sabha_number'] or 'Unknown'
                        sess_no = session['session_number'] or 'Unknown'
                        count = session['count']
                        print(f"     📊 Questions: LS{ls_no} Session{sess_no}: +{count}")
                
                # Debates created in last 5 seconds
                if debates_diff > 0:
                    recent_debates = DebateMasterData.objects.filter(
                        created_at__gte=five_secs_ago
                    ).values('lok_sabha_number', 'session_number', 'debate_category').annotate(
                        count=Count('id')
                    ).order_by('-count')[:3]
                    
                    for debate in recent_debates:
                        ls_no = debate['lok_sabha_number'] or 'Unknown'
                        sess_no = debate['session_number'] or 'Unknown'
                        category = debate['debate_category'] or 'Unknown'
                        count = debate['count']
                        print(f"     🏛️  Debates: LS{ls_no} Session{sess_no} ({category}): +{count}")
                
                # Sessions created in last 5 seconds
                if sessions_diff > 0:
                    recent_sessions = Session.objects.filter(
                        created_at__gte=five_secs_ago
                    ).values('session_number', 'lok_sabha__number').annotate(
                        count=Count('id')
                    ).order_by('-count')[:3]
                    
                    for session in recent_sessions:
                        sess_no = session['session_number'] or 'Unknown'
                        ls_no = session['lok_sabha__number'] or 'Unknown'
                        count = session['count']
                        print(f"     📅 Sessions: LS{ls_no} Session{sess_no}: +{count}")
                
                # Institutions created in last 5 seconds
                if institutions_diff > 0:
                    recent_institutions = ParliamentInstitution.objects.filter(
                        created_at__gte=five_secs_ago
                    ).values('name').annotate(
                        count=Count('id')
                    ).order_by('-count')[:3]
                    
                    for inst in recent_institutions:
                        name = inst['name'] or 'Unknown'
                        count = inst['count']
                        print(f"     🏛️  Institutions: {name}: +{count}")
                
                # Lok Sabhas created in last 5 seconds
                if lok_sabhas_diff > 0:
                    recent_lok_sabhas = LokSabha.objects.filter(
                        created_at__gte=five_secs_ago
                    ).values('number').annotate(
                        count=Count('id')
                    ).order_by('-count')[:3]
                    
                    for ls in recent_lok_sabhas:
                        number = ls['number'] or 'Unknown'
                        count = ls['count']
                        print(f"     🏛️  Lok Sabhas: {number}: +{count}")
            
            # Update for next iteration
            prev_questions = curr_questions
            prev_debates = curr_debates
            prev_sessions = curr_sessions
            prev_lok_sabhas = curr_lok_sabhas
            prev_institutions = curr_institutions
            time.sleep(5)
            
    except KeyboardInterrupt:
        print("\n\n✅ Monitoring stopped")
        print(f"Final counts:")
        print(f"  📊 Questions: {curr_questions:,}")
        print(f"  🏛️  Debates: {curr_debates:,}")
        print(f"  📅 Sessions: {curr_sessions:,}")
        print(f"  🏛️  Lok Sabhas: {curr_lok_sabhas:,}")
        print(f"  🏛️  Institutions: {curr_institutions:,}")

if __name__ == '__main__':
    monitor_database()
