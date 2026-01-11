"""
Base Provider Interface

All data providers (pricing, solar, load, state) inherit from this.
Ensures consistent API across all data sources.
"""

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Dict, List, Any, Optional


class DataProvider(ABC):
    """
    Abstract base class for all data providers.
    
    Each provider is responsible for:
    - Fetching/calculating its specific data
    - Caching results appropriately
    - Reporting confidence/health status
    - Being independently testable
    """
    
    def __init__(self, hass):
        """
        Initialize provider.
        
        Args:
            hass: Home Assistant API object
        """
        self.hass = hass
        self._last_update = None
        self._cache = {}
        self._health_status = 'unknown'
    
    def log(self, message: str, level: str = "INFO"):
        """Log a message"""
        if hasattr(self.hass, 'log'):
            self.hass.log(message, level=level)
        else:
            timestamp = datetime.now().strftime('%H:%M:%S')
            print(f"[{timestamp}] {message}")
    
    @abstractmethod
    def setup(self, config: Dict) -> bool:
        """
        Setup the provider with configuration.
        
        Args:
            config: Configuration dictionary
            
        Returns:
            True if setup successful, False otherwise
        """
        pass
    
    @abstractmethod
    def get_data(self, **kwargs) -> Any:
        """
        Get the provider's data.
        
        Returns:
            Provider-specific data structure
        """
        pass
    
    @abstractmethod
    def get_health(self) -> Dict:
        """
        Get health status of this provider.
        
        Returns:
            Dict with keys:
                - status: 'healthy', 'degraded', 'failed'
                - last_update: datetime of last successful update
                - message: human-readable status message
                - confidence: data confidence level (if applicable)
        """
        pass
    
    def clear_cache(self):
        """Clear cached data"""
        self._cache = {}
    
    def get_provider_name(self) -> str:
        """Get human-readable provider name"""
        return self.__class__.__name__
