import sys
import os
from datetime import datetime, time, timedelta
import pytz

# Add parent directory to path so we can import calendar_service
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config
from calendar_service import CalendarService

def remove_duplicates():
    print("Starting duplicate removal for today...")
    
    cal = CalendarService()
    
    # Get today's events (Feb 18th)
    TZ = pytz.timezone(config.TIMEZONE)
    now = datetime.now(TZ)
    start_of_day = TZ.localize(datetime.combine(now.date(), time.min))
    end_of_day = TZ.localize(datetime.combine(now.date(), time.max))
    
    print(f"Scanning for duplicates between {start_of_day} and {end_of_day}...")
    
    events = cal.list_events(start_of_day, end_of_day)
    
    # Group by summary
    summary_map = {}
    for event in events:
        summary = event.get("summary", "")
        # Filter only for tasks (all-day events) or specific renewed tasks
        # Assuming only tasks are duplicated as per user complaint "todas las tareas"
        start = event.get("start", {})
        if "date" not in start:
            # Skip non-all-day events if they are not the problem?
            # User said "todas las tareas", usually these are all-day events.
            # But let's check duplicates for EVERYTHING just in case, logic is same.
            pass
            
        if summary not in summary_map:
            summary_map[summary] = []
        summary_map[summary].append(event)
        
    duplicates_found = 0
    deleted_count = 0
    
    for summary, dup_events in summary_map.items():
        if len(dup_events) > 1:
            duplicates_found += 1
            print(f"Found {len(dup_events)} copies of: {summary}")
            
            # Sort by creation time if possible? Google Calendar API doesn't always give creation time easily in basic list.
            # But IDs are usually somewhat sequential or random.
            # We'll just keep the first one found in the list (usually earliest start time, but here start times are same)
            # The list_events returns ordered by startTime.
            
            # Keep the first one, delete the rest
            events_to_delete = dup_events[1:]
            
            for event_to_delete in events_to_delete:
                print(f"  Deleting duplicate ID: {event_to_delete['id']}")
                try:
                    cal.delete_event(event_to_delete['id'])
                    deleted_count += 1
                except Exception as e:
                    print(f"  Error deleting {event_to_delete['id']}: {e}")
                    
    print(f"\nFinished. Found {duplicates_found} duplicated summaries. Deleted {deleted_count} events.")

if __name__ == "__main__":
    remove_duplicates()
