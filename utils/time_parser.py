"""
Unified time parsing utility for Discord bot
Provides consistent natural language time parsing for both reminders and tasks
"""

import logging
import pytz
from datetime import datetime, timedelta
from typing import Optional

logger = logging.getLogger(__name__)


class TimeParser:
    """Unified natural language time parser for Discord bot systems"""
    
    def __init__(self):
        self.word_to_number = {
            'one': 1, 'two': 2, 'three': 3, 'four': 4, 'five': 5,
            'six': 6, 'seven': 7, 'eight': 8, 'nine': 9, 'ten': 10,
            'eleven': 11, 'twelve': 12, 'fifteen': 15, 'twenty': 20,
            'thirty': 30, 'forty': 40, 'fifty': 50, 'sixty': 60
        }
        
        self.unit_mapping = {
            'second': 'seconds', 'sec': 'seconds', 's': 'seconds',
            'minute': 'minutes', 'min': 'minutes', 'm': 'minutes',
            'hour': 'hours', 'hr': 'hours', 'h': 'hours',
            'day': 'days', 'd': 'days',
            'week': 'weeks', 'w': 'weeks',
            'month': 'months'
        }
        
        self.day_mapping = {
            "monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3, 
            "friday": 4, "saturday": 5, "sunday": 6
        }
    
    def parse_natural_time(self, time_str: str, user_timezone: str) -> Optional[datetime]:
        """Parse natural language time string into a datetime object"""
        try:
            local_tz = pytz.timezone(user_timezone)
            now = datetime.now(local_tz)
            time_str = time_str.lower().strip()
            
            # Handle basic keywords first
            if time_str == "tomorrow":
                return (now + timedelta(days=1)).replace(hour=9, minute=0, second=0, microsecond=0)
            elif time_str == "noon" or time_str == "midday":
                if now.hour >= 12:
                    return (now + timedelta(days=1)).replace(hour=12, minute=0, second=0, microsecond=0)
                else:
                    return now.replace(hour=12, minute=0, second=0, microsecond=0)
            elif time_str == "midnight":
                return (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
            elif time_str == "tonight":
                return now.replace(hour=20, minute=0, second=0, microsecond=0)
            
            # Handle compound "tonight" patterns - NEW FUNCTIONALITY
            if "tonight" in time_str:
                return self._parse_tonight_patterns(time_str, now)
            
            # Handle "today" patterns
            if "today" in time_str:
                return self._parse_today_patterns(time_str, now)
            
            # Handle relative time patterns
            relative_result = self._parse_relative_time(time_str, now)
            if relative_result:
                return relative_result
            
            # Handle "tomorrow at X" patterns
            if "tomorrow" in time_str and "at" in time_str:
                return self._parse_tomorrow_at_patterns(time_str, now)
            
            # Handle day names
            day_result = self._parse_day_names(time_str, now)
            if day_result:
                return day_result
            
            # Handle standalone times (like "6pm", "3:30pm")
            standalone_result = self._parse_standalone_time(time_str, now)
            if standalone_result:
                return standalone_result
            
            return None
            
        except Exception as e:
            logger.error(f"Error parsing natural time '{time_str}': {e}")
            return None
    
    def _parse_tonight_patterns(self, time_str: str, now: datetime) -> Optional[datetime]:
        """Parse patterns like '6pm tonight', 'tonight at 6pm', 'midnight tonight'"""
        # Handle "midnight tonight" specifically
        if "midnight" in time_str:
            return (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
        
        # Extract time part from "X tonight" or "tonight at X"
        time_part = None
        if " tonight" in time_str:
            # Pattern: "6pm tonight"
            time_part = time_str.replace(" tonight", "").strip()
        elif "tonight at " in time_str:
            # Pattern: "tonight at 6pm"
            time_part = time_str.replace("tonight at ", "").strip()
        elif "tonight" in time_str and "at" in time_str:
            # Pattern: "tonight at 6pm" with extra words
            parts = time_str.split("at")
            if len(parts) >= 2:
                time_part = parts[-1].strip()
        
        if time_part:
            parsed_time = self._parse_time_component(time_part)
            if parsed_time:
                hour, minute = parsed_time
                target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
                # If the time has passed today, it means tomorrow
                if target <= now:
                    target = target + timedelta(days=1)
                return target
        
        # Fallback to default "tonight" (8 PM)
        return now.replace(hour=20, minute=0, second=0, microsecond=0)
    
    def _parse_today_patterns(self, time_str: str, now: datetime) -> Optional[datetime]:
        """Parse patterns like 'today at 3pm', '3pm today'"""
        time_part = None
        if " today" in time_str:
            # Pattern: "3pm today"
            time_part = time_str.replace(" today", "").strip()
        elif "today at " in time_str:
            # Pattern: "today at 3pm"
            time_part = time_str.replace("today at ", "").strip()
        elif "today" in time_str and "at" in time_str:
            # Pattern: "today at 3pm" with extra words
            parts = time_str.split("at")
            if len(parts) >= 2:
                time_part = parts[-1].strip()
        
        if time_part:
            parsed_time = self._parse_time_component(time_part)
            if parsed_time:
                hour, minute = parsed_time
                target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
                # If the time has passed today, it means tomorrow
                if target <= now:
                    target = target + timedelta(days=1)
                return target
        
        # Fallback to default "today" (5 PM)
        return now.replace(hour=17, minute=0, second=0, microsecond=0)
    
    def _parse_relative_time(self, time_str: str, now: datetime) -> Optional[datetime]:
        """Parse relative time patterns like 'in 5 minutes', '2 hours from now'"""
        relative_patterns = [
            ("in ", 3),           # "in 5 minutes"
            ("", 0),              # Handle "X minutes from now" and other patterns
        ]
        
        for prefix, prefix_len in relative_patterns:
            if prefix and not time_str.startswith(prefix):
                continue
                
            remaining = time_str[prefix_len:].strip()
            
            # Handle "X minutes from now", "X mins from now", etc.
            if "from now" in remaining:
                remaining = remaining.replace("from now", "").strip()
            
            # Handle "in about X", "around X", etc.
            remaining = remaining.replace("about ", "").replace("around ", "").strip()
            
            # Handle informal patterns
            if remaining in ["a minute", "1 minute", "one minute"]:
                return now + timedelta(minutes=1)
            elif remaining in ["a few minutes", "few minutes"]:
                return now + timedelta(minutes=3)
            elif remaining in ["a second", "1 second", "one second"]:
                return now + timedelta(seconds=1)
            elif remaining in ["a few seconds", "few seconds"]:
                return now + timedelta(seconds=5)
            
            # Parse numerical patterns
            parts = remaining.split()
            if len(parts) >= 2:
                try:
                    if parts[0].lower() in self.word_to_number:
                        amount = self.word_to_number[parts[0].lower()]
                    else:
                        amount = int(parts[0])
                    
                    unit = parts[1].rstrip('s').lower()
                    unit = self.unit_mapping.get(unit, unit)
                    
                    if unit == 'seconds':
                        return now + timedelta(seconds=amount)
                    elif unit == 'minutes':
                        return now + timedelta(minutes=amount)
                    elif unit == 'hours':
                        return now + timedelta(hours=amount)
                    elif unit == 'days':
                        return now + timedelta(days=amount)
                    elif unit == 'weeks':
                        return now + timedelta(weeks=amount)
                    elif unit == 'months':
                        return now + timedelta(days=amount * 30)
                except ValueError:
                    continue
            
            # If we found a matching prefix, don't try other patterns
            if prefix:
                break
        
        return None
    
    def _parse_tomorrow_at_patterns(self, time_str: str, now: datetime) -> Optional[datetime]:
        """Parse patterns like 'tomorrow at 3pm'"""
        time_part = time_str.split("at")[-1].strip()
        tomorrow = now + timedelta(days=1)
        
        # Parse time formats
        for fmt in ["%I:%M %p", "%I:%M%p", "%I %p", "%I%p", "%H:%M"]:
            try:
                parsed_time = datetime.strptime(time_part.upper(), fmt)
                return tomorrow.replace(
                    hour=parsed_time.hour, 
                    minute=parsed_time.minute, 
                    second=0, 
                    microsecond=0
                )
            except ValueError:
                continue
        
        return None
    
    def _parse_day_names(self, time_str: str, now: datetime) -> Optional[datetime]:
        """Parse day names like 'Friday at 3pm', 'next Monday'"""
        for day_name, day_num in self.day_mapping.items():
            if day_name in time_str:
                current_day = now.weekday()
                days_ahead = (day_num - current_day) % 7
                
                # Check if "next" is mentioned
                is_next = "next" in time_str
                
                if days_ahead == 0:  # Today
                    if is_next or now.hour >= 12:
                        days_ahead = 7
                
                target_date = now + timedelta(days=days_ahead)
                target_time = "9:00 AM"  # Default time
                
                # Extract time if specified
                if "at" in time_str:
                    time_part = time_str.split("at")[-1].strip()
                    for fmt in ["%I:%M %p", "%I:%M%p", "%I %p", "%H:%M"]:
                        try:
                            parsed_time = datetime.strptime(time_part.upper(), fmt)
                            target_time = parsed_time.strftime("%H:%M")
                            break
                        except ValueError:
                            continue
                
                # Parse the final time
                try:
                    hour, minute = map(int, target_time.split(":")[:2])
                    return target_date.replace(hour=hour, minute=minute, second=0, microsecond=0)
                except ValueError:
                    pass
        
        return None
    
    def _parse_standalone_time(self, time_str: str, now: datetime) -> Optional[datetime]:
        """Parse standalone times like '6pm', '3:30am', '15:30'"""
        parsed_time = self._parse_time_component(time_str)
        if parsed_time:
            hour, minute = parsed_time
            target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
            
            # If the time has passed today, assume tomorrow
            if target <= now:
                target = target + timedelta(days=1)
            
            return target
        
        return None
    
    def _parse_time_component(self, time_str: str) -> Optional[tuple[int, int]]:
        """Parse a time component like '6pm', '3:30am', '15:30' into (hour, minute)"""
        time_str = time_str.strip().lower()
        
        # Try different time formats
        formats_to_try = [
            "%I:%M %p",    # 3:30 PM
            "%I:%M%p",     # 3:30PM
            "%I %p",       # 3 PM  
            "%I%p",        # 3PM
            "%H:%M",       # 15:30 (24-hour)
        ]
        
        for fmt in formats_to_try:
            try:
                parsed = datetime.strptime(time_str.upper(), fmt)
                return (parsed.hour, parsed.minute)
            except ValueError:
                continue
        
        return None


# Create singleton instance
time_parser = TimeParser()