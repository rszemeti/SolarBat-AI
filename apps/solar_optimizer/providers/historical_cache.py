"""
Historical Data Cache - Persistent storage for prediction data

Caches historical load and pricing data to avoid expensive re-fetching.
Updates incrementally with new data.

Features:
- Persistent JSON storage
- Automatic cleanup (keeps last 30 days)
- Incremental updates (only fetch new data)
- Fast lookups
"""

import json
import os
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from pathlib import Path


class HistoricalDataCache:
    """
    Manages persistent cache for historical time-series data.
    
    Each cache file stores:
    - Historical datapoints (timestamp + value)
    - Last update timestamp
    - Metadata (sensor name, data type)
    """
    
    def __init__(self, cache_dir: str = "/config/appdaemon/cache", cache_name: str = "default"):
        """
        Initialize cache.
        
        Args:
            cache_dir: Directory to store cache files
            cache_name: Name for this cache (e.g., "load_sensor", "agile_prices")
        """
        self.cache_dir = Path(cache_dir)
        self.cache_name = cache_name
        self.cache_file = self.cache_dir / f"{cache_name}.json"
        
        # In-memory cache
        self.data = []  # List of {'timestamp': datetime, 'value': float}
        self.last_update = None
        self.metadata = {}
        
        # Ensure cache directory exists
        try:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            print(f"[CACHE] Warning: Could not create cache dir: {e}")
    
    def load(self) -> bool:
        """
        Load cache from disk.
        
        Returns:
            True if cache loaded successfully
        """
        try:
            if not self.cache_file.exists():
                return False
            
            with open(self.cache_file, 'r') as f:
                cache_data = json.load(f)
            
            # Parse timestamps
            self.data = [
                {
                    'timestamp': datetime.fromisoformat(item['timestamp']),
                    'value': item['value']
                }
                for item in cache_data.get('data', [])
            ]
            
            # Load metadata
            self.last_update = datetime.fromisoformat(cache_data['last_update']) if cache_data.get('last_update') else None
            self.metadata = cache_data.get('metadata', {})
            
            # Cleanup old data (keep last 30 days)
            self._cleanup_old_data()
            
            return True
            
        except Exception as e:
            print(f"[CACHE] Error loading cache {self.cache_name}: {e}")
            return False
    
    def save(self) -> bool:
        """
        Save cache to disk.
        
        Returns:
            True if saved successfully
        """
        try:
            # Cleanup before saving
            self._cleanup_old_data()
            
            # Prepare data for JSON
            cache_data = {
                'last_update': self.last_update.isoformat() if self.last_update else None,
                'metadata': self.metadata,
                'data': [
                    {
                        'timestamp': item['timestamp'].isoformat(),
                        'value': item['value']
                    }
                    for item in self.data
                ]
            }
            
            # Write to temp file then rename (atomic operation)
            temp_file = self.cache_file.with_suffix('.tmp')
            with open(temp_file, 'w') as f:
                json.dump(cache_data, f, indent=2)
            
            # Atomic rename
            temp_file.replace(self.cache_file)
            
            return True
            
        except Exception as e:
            print(f"[CACHE] Error saving cache {self.cache_name}: {e}")
            return False
    
    def add_data(self, new_data: List[Dict], deduplicate: bool = True):
        """
        Add new data to cache.
        
        Args:
            new_data: List of {'timestamp': datetime, 'value': float}
            deduplicate: Remove duplicates by timestamp
        """
        self.data.extend(new_data)
        
        if deduplicate:
            # Remove duplicates, keeping most recent
            seen = {}
            for item in sorted(self.data, key=lambda x: x['timestamp'], reverse=True):
                ts_key = item['timestamp'].isoformat()
                if ts_key not in seen:
                    seen[ts_key] = item
            
            self.data = sorted(seen.values(), key=lambda x: x['timestamp'])
        else:
            # Just sort
            self.data.sort(key=lambda x: x['timestamp'])
        
        # Update last_update
        if self.data:
            self.last_update = max(item['timestamp'] for item in self.data)
    
    def get_data(self, start_time: Optional[datetime] = None, 
                 end_time: Optional[datetime] = None) -> List[Dict]:
        """
        Get cached data within time range.
        
        Args:
            start_time: Start of range (None = no limit)
            end_time: End of range (None = no limit)
            
        Returns:
            List of {'timestamp': datetime, 'value': float}
        """
        filtered = self.data
        
        if start_time:
            filtered = [d for d in filtered if d['timestamp'] >= start_time]
        
        if end_time:
            filtered = [d for d in filtered if d['timestamp'] <= end_time]
        
        return filtered
    
    def get_latest_timestamp(self) -> Optional[datetime]:
        """Get timestamp of most recent data point"""
        if self.data:
            return max(item['timestamp'] for item in self.data)
        return None
    
    def needs_update(self, max_age_hours: int = 1) -> bool:
        """
        Check if cache needs updating.
        
        Args:
            max_age_hours: Consider cache stale after this many hours
            
        Returns:
            True if cache should be updated
        """
        if not self.data:
            return True
        
        latest = self.get_latest_timestamp()
        if not latest:
            return True
        
        age = datetime.now() - latest
        return age > timedelta(hours=max_age_hours)
    
    def get_missing_range(self) -> Optional[tuple]:
        """
        Calculate what time range of data is missing.
        
        Returns:
            Tuple of (start_time, end_time) for missing data, or None if up to date
        """
        if not self.data:
            # No data - fetch last 7 days
            end_time = datetime.now()
            start_time = end_time - timedelta(days=7)
            return (start_time, end_time)
        
        latest = self.get_latest_timestamp()
        now = datetime.now()
        
        if (now - latest) > timedelta(hours=1):
            # Fetch from latest to now
            return (latest, now)
        
        return None
    
    def _cleanup_old_data(self):
        """Remove data older than 30 days"""
        cutoff = datetime.now() - timedelta(days=30)
        self.data = [d for d in self.data if d['timestamp'] > cutoff]
    
    def get_stats(self) -> Dict:
        """Get cache statistics"""
        if not self.data:
            return {
                'count': 0,
                'oldest': None,
                'newest': None,
                'span_days': 0
            }
        
        timestamps = [d['timestamp'] for d in self.data]
        oldest = min(timestamps)
        newest = max(timestamps)
        span = (newest - oldest).total_seconds() / 86400
        
        return {
            'count': len(self.data),
            'oldest': oldest,
            'newest': newest,
            'span_days': span
        }
    
    def clear(self):
        """Clear all cached data"""
        self.data = []
        self.last_update = None
        self.metadata = {}
        
        try:
            if self.cache_file.exists():
                self.cache_file.unlink()
        except Exception as e:
            print(f"[CACHE] Error clearing cache: {e}")


def get_cache_directory() -> str:
    """
    Get appropriate cache directory based on environment.
    
    Returns:
        Path to cache directory
    """
    # Try AppDaemon config directory
    if os.path.exists('/config/appdaemon'):
        return '/config/appdaemon/cache'
    
    # Try Home Assistant config
    if os.path.exists('/config'):
        return '/config/solar_optimizer_cache'
    
    # Fallback to temp directory
    import tempfile
    return os.path.join(tempfile.gettempdir(), 'solar_optimizer_cache')
