"""
Historical Data Cache Manager

Caches historical data (load, pricing) to avoid expensive re-fetching.
Updates incrementally with only new data since last cache.

Features:
- Persistent JSON storage
- Incremental updates (only fetch new data)
- Automatic expiry and cleanup
- Thread-safe file operations
"""

import json
import os
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from pathlib import Path
import tempfile

# fcntl is Linux-only, make it optional for Windows
try:
    import fcntl
    HAS_FCNTL = True
except ImportError:
    HAS_FCNTL = False  # Windows doesn't have fcntl


def get_cache_directory() -> str:
    """
    Get appropriate cache directory based on environment.
    
    Returns:
        Path to cache directory that exists and is writable
    """
    # Try AppDaemon config directory (production)
    if os.path.exists('/config/appdaemon'):
        cache_dir = '/config/appdaemon/cache'
        try:
            Path(cache_dir).mkdir(parents=True, exist_ok=True)
            return cache_dir
        except:
            pass
    
    # Try Home Assistant config (alternative)
    if os.path.exists('/config'):
        cache_dir = '/config/solar_optimizer_cache'
        try:
            Path(cache_dir).mkdir(parents=True, exist_ok=True)
            return cache_dir
        except:
            pass
    
    # Fallback to user's temp directory (test harness, Windows)
    cache_dir = os.path.join(tempfile.gettempdir(), 'solar_optimizer_cache')
    Path(cache_dir).mkdir(parents=True, exist_ok=True)
    return cache_dir


class HistoricalDataCache:
    """
    Manages persistent cache of historical time-series data.
    
    Cache structure:
    {
        "last_updated": "2026-01-16T10:00:00",
        "data": [
            {"timestamp": "2026-01-15T10:00:00", "value": 1.25},
            ...
        ]
    }
    """
    
    def __init__(self, cache_name: str, cache_dir: str = None):
        """
        Initialize cache manager.
        
        Args:
            cache_name: Name for this cache (e.g., "load_history", "price_history")
            cache_dir: Directory to store cache files (None = auto-detect)
        """
        if cache_dir is None:
            cache_dir = get_cache_directory()
        
        self.cache_name = cache_name
        self.cache_dir = Path(cache_dir)
        self.cache_file = self.cache_dir / f"{cache_name}.json"
        
        # Create cache directory if it doesn't exist
        try:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            print(f"[CACHE] Warning: Could not create cache dir {cache_dir}: {e}")
    
    def load(self, max_age_days: int = 30) -> Dict:
        """
        Load cached data.
        
        Args:
            max_age_days: Maximum age of data to keep (older data is pruned)
            
        Returns:
            Dict with 'last_updated' and 'data' keys
        """
        if not self.cache_file.exists():
            return {'last_updated': None, 'data': []}
        
        try:
            with open(self.cache_file, 'r') as f:
                # Lock file for reading (Linux only)
                if HAS_FCNTL:
                    fcntl.flock(f.fileno(), fcntl.LOCK_SH)
                try:
                    cache_data = json.load(f)
                finally:
                    if HAS_FCNTL:
                        fcntl.flock(f.fileno(), fcntl.LOCK_UN)
            
            # Parse timestamps
            if cache_data.get('last_updated'):
                cache_data['last_updated'] = datetime.fromisoformat(cache_data['last_updated'])
            
            for item in cache_data.get('data', []):
                if 'timestamp' in item:
                    item['timestamp'] = datetime.fromisoformat(item['timestamp'])
            
            # Prune old data
            if cache_data.get('data'):
                cutoff = datetime.now() - timedelta(days=max_age_days)
                cache_data['data'] = [
                    d for d in cache_data['data']
                    if d.get('timestamp') and d['timestamp'] > cutoff
                ]
            
            return cache_data
            
        except Exception as e:
            print(f"[CACHE] Error loading cache {self.cache_name}: {e}")
            return {'last_updated': None, 'data': []}
    
    def save(self, data: List[Dict], last_updated: datetime = None):
        """
        Save data to cache.
        
        Args:
            data: List of dicts with 'timestamp' and 'value' keys
            last_updated: When this data was last updated (defaults to now)
        """
        if last_updated is None:
            last_updated = datetime.now()
        
        try:
            # Convert to serializable format
            cache_data = {
                'last_updated': last_updated.isoformat(),
                'data': [
                    {
                        'timestamp': d['timestamp'].isoformat(),
                        'value': d['value']
                    }
                    for d in data if 'timestamp' in d and 'value' in d
                ]
            }
            
            # Write atomically (write to temp file, then rename)
            temp_file = self.cache_file.with_suffix('.tmp')
            
            with open(temp_file, 'w') as f:
                # Lock file for writing (Linux only)
                if HAS_FCNTL:
                    fcntl.flock(f.fileno(), fcntl.LOCK_EX)
                try:
                    json.dump(cache_data, f, indent=2)
                    f.flush()
                    os.fsync(f.fileno())
                finally:
                    if HAS_FCNTL:
                        fcntl.flock(f.fileno(), fcntl.LOCK_UN)
            
            # Atomic rename
            temp_file.replace(self.cache_file)
            
        except Exception as e:
            print(f"[CACHE] Error saving cache {self.cache_name}: {e}")
    
    def update_incremental(self, new_data: List[Dict], max_age_days: int = 30):
        """
        Add new data to existing cache (incremental update).
        
        Args:
            new_data: New data points to add
            max_age_days: Maximum age to keep
            
        Returns:
            Complete dataset (old + new, deduplicated)
        """
        # Load existing cache
        cache = self.load(max_age_days=max_age_days)
        existing_data = cache['data']
        
        # Combine with new data
        all_data = existing_data + new_data
        
        # Deduplicate by timestamp (keep most recent entry for each timestamp)
        timestamp_map = {}
        for item in all_data:
            if 'timestamp' in item:
                ts = item['timestamp'].isoformat()
                timestamp_map[ts] = item
        
        # Sort by timestamp
        deduplicated = sorted(timestamp_map.values(), key=lambda x: x['timestamp'])
        
        # Save updated cache
        self.save(deduplicated)
        
        return deduplicated
    
    def get_last_updated(self) -> Optional[datetime]:
        """Get timestamp of when cache was last updated"""
        cache = self.load()
        return cache.get('last_updated')
    
    def clear(self):
        """Clear the cache file"""
        try:
            if self.cache_file.exists():
                self.cache_file.unlink()
        except Exception as e:
            print(f"[CACHE] Error clearing cache {self.cache_name}: {e}")
    
    def get_stats(self) -> Dict:
        """Get cache statistics"""
        cache = self.load()
        data = cache['data']
        
        if not data:
            return {
                'entries': 0,
                'last_updated': None,
                'oldest_entry': None,
                'newest_entry': None,
                'age_days': 0
            }
        
        timestamps = [d['timestamp'] for d in data if 'timestamp' in d]
        
        if timestamps:
            oldest = min(timestamps)
            newest = max(timestamps)
            age_days = (datetime.now() - oldest).days
        else:
            oldest = newest = None
            age_days = 0
        
        return {
            'entries': len(data),
            'last_updated': cache.get('last_updated'),
            'oldest_entry': oldest,
            'newest_entry': newest,
            'age_days': age_days
        }


class CachedHistoricalDataFetcher:
    """
    Helper class to fetch historical data with intelligent caching.
    
    Usage:
        fetcher = CachedHistoricalDataFetcher("load_history")
        data = fetcher.fetch(fetch_func, days_back=7)
    """
    
    def __init__(self, cache_name: str, cache_dir: str = None):
        if cache_dir is None:
            cache_dir = get_cache_directory()
        
        self.cache = HistoricalDataCache(cache_name, cache_dir)
        print(f"[CACHE] Initialized cache '{cache_name}' at: {cache_dir}")
    
    def fetch(self, fetch_func, days_back: int = 7, force_refresh: bool = False) -> List[Dict]:
        """
        Fetch historical data with caching.
        
        Args:
            fetch_func: Function(start_time, end_time) -> List[Dict] that fetches data
            days_back: How many days of history to maintain
            force_refresh: If True, ignore cache and fetch everything
            
        Returns:
            List of historical data points
        """
        if force_refresh:
            # Full refresh - fetch everything
            print(f"[CACHE] Force refresh: fetching {days_back} days")
            start_time = datetime.now() - timedelta(days=days_back)
            end_time = datetime.now()
            
            new_data = fetch_func(start_time, end_time)
            self.cache.save(new_data)
            
            return new_data
        
        # Try to use cache
        cache = self.cache.load(max_age_days=days_back)
        last_updated = cache.get('last_updated')
        cached_data = cache['data']
        
        if last_updated is None or not cached_data:
            # No cache - full fetch
            print(f"[CACHE] No cache found: fetching {days_back} days")
            start_time = datetime.now() - timedelta(days=days_back)
            end_time = datetime.now()
            
            new_data = fetch_func(start_time, end_time)
            self.cache.save(new_data)
            
            return new_data
        
        # We have cache - check if it's recent enough
        cache_age = datetime.now() - last_updated
        
        if cache_age.total_seconds() < 1800:  # Less than 30 minutes old
            # Cache is fresh - use it directly
            print(f"[CACHE] Using fresh cache ({len(cached_data)} entries, age: {cache_age.total_seconds()/60:.0f}min)")
            return cached_data
        
        # Cache is stale - fetch only new data since last update
        print(f"[CACHE] Incremental update: fetching data since {last_updated.strftime('%Y-%m-%d %H:%M')}")
        
        # Fetch from 1 hour before last update (overlap to avoid gaps)
        start_time = last_updated - timedelta(hours=1)
        end_time = datetime.now()
        
        new_data = fetch_func(start_time, end_time)
        
        if new_data:
            print(f"[CACHE] Adding {len(new_data)} new entries to cache")
            complete_data = self.cache.update_incremental(new_data, max_age_days=days_back)
            return complete_data
        else:
            # No new data - return cached data
            print(f"[CACHE] No new data, using existing cache")
            return cached_data
    
    def get_stats(self) -> Dict:
        """Get cache statistics"""
        return self.cache.get_stats()
    
    def clear(self):
        """Clear the cache"""
        self.cache.clear()
