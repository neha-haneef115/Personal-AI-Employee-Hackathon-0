"""
BaseWatcher - Abstract base class for AI Employee watchers

This module provides the foundation for creating specialized watchers that monitor
different data sources and trigger appropriate actions based on detected events.
"""

import abc
import asyncio
import logging
from typing import Any, Dict, List, Optional, Callable
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

class EventType(Enum):
    """Types of events that can be triggered by watchers"""
    NEW_ITEM = "new_item"
    UPDATED_ITEM = "updated_item"
    DELETED_ITEM = "deleted_item"
    ERROR = "error"
    STATUS_CHANGE = "status_change"

@dataclass
class Event:
    """Represents an event triggered by a watcher"""
    event_type: EventType
    source: str
    timestamp: datetime
    data: Dict[str, Any]
    metadata: Optional[Dict[str, Any]] = None

class BaseWatcher(abc.ABC):
    """
    Abstract base class for all AI Employee watchers.
    
    This class provides the common interface and functionality that all watchers
    should implement, including event handling, logging, and lifecycle management.
    """
    
    def __init__(self, name: str, config: Optional[Dict[str, Any]] = None):
        """
        Initialize the watcher.
        
        Args:
            name: Unique identifier for this watcher
            config: Configuration dictionary for the watcher
        """
        self.name = name
        self.config = config or {}
        self.logger = self._setup_logger()
        self.is_running = False
        self._event_handlers: List[Callable[[Event], None]] = []
        self._watch_task: Optional[asyncio.Task] = None
        
        # Initialize watcher-specific configuration
        self._initialize_config()
    
    def _setup_logger(self) -> logging.Logger:
        """Set up logging for the watcher"""
        logger = logging.getLogger(f"watcher.{self.name}")
        if not logger.handlers:
            handler = logging.StreamHandler()
            formatter = logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
            )
            handler.setFormatter(formatter)
            logger.addHandler(handler)
            logger.setLevel(
                getattr(logging, self.config.get('log_level', 'INFO'))
            )
        return logger
    
    def _initialize_config(self) -> None:
        """
        Initialize watcher-specific configuration.
        Override this method in subclasses to set up default configuration.
        """
        pass
    
    @abc.abstractmethod
    async def _watch_loop(self) -> None:
        """
        Main watching loop that monitors the data source.
        Must be implemented by subclasses.
        """
        pass
    
    @abc.abstractmethod
    async def _check_for_changes(self) -> List[Event]:
        """
        Check for changes in the monitored data source.
        Must be implemented by subclasses.
        
        Returns:
            List of events detected since last check
        """
        pass
    
    def add_event_handler(self, handler: Callable[[Event], None]) -> None:
        """
        Add an event handler callback.
        
        Args:
            handler: Function to call when an event is triggered
        """
        self._event_handlers.append(handler)
        self.logger.info(f"Added event handler for watcher {self.name}")
    
    def remove_event_handler(self, handler: Callable[[Event], None]) -> None:
        """
        Remove an event handler callback.
        
        Args:
            handler: Function to remove from event handlers
        """
        if handler in self._event_handlers:
            self._event_handlers.remove(handler)
            self.logger.info(f"Removed event handler for watcher {self.name}")
    
    async def _emit_event(self, event: Event) -> None:
        """
        Emit an event to all registered handlers.
        
        Args:
            event: The event to emit
        """
        self.logger.debug(f"Emitting event: {event.event_type.value} from {event.source}")
        
        for handler in self._event_handlers:
            try:
                if asyncio.iscoroutinefunction(handler):
                    await handler(event)
                else:
                    handler(event)
            except Exception as e:
                self.logger.error(
                    f"Error in event handler for {event.event_type.value}: {e}"
                )
    
    async def start(self) -> None:
        """Start the watcher"""
        if self.is_running:
            self.logger.warning(f"Watcher {self.name} is already running")
            return
        
        self.logger.info(f"Starting watcher {self.name}")
        self.is_running = True
        
        try:
            await self._on_start()
            self._watch_task = asyncio.create_task(self._watch_loop())
            self.logger.info(f"Watcher {self.name} started successfully")
        except Exception as e:
            self.logger.error(f"Failed to start watcher {self.name}: {e}")
            self.is_running = False
            raise
    
    async def stop(self) -> None:
        """Stop the watcher"""
        if not self.is_running:
            self.logger.warning(f"Watcher {self.name} is not running")
            return
        
        self.logger.info(f"Stopping watcher {self.name}")
        self.is_running = False
        
        if self._watch_task:
            self._watch_task.cancel()
            try:
                await self._watch_task
            except asyncio.CancelledError:
                pass
        
        try:
            await self._on_stop()
            self.logger.info(f"Watcher {self.name} stopped successfully")
        except Exception as e:
            self.logger.error(f"Error stopping watcher {self.name}: {e}")
    
    async def _on_start(self) -> None:
        """
        Called when the watcher starts.
        Override this method in subclasses to perform startup tasks.
        """
        pass
    
    async def _on_stop(self) -> None:
        """
        Called when the watcher stops.
        Override this method in subclasses to perform cleanup tasks.
        """
        pass
    
    def get_status(self) -> Dict[str, Any]:
        """
        Get the current status of the watcher.
        
        Returns:
            Dictionary containing watcher status information
        """
        return {
            'name': self.name,
            'is_running': self.is_running,
            'config': self.config,
            'event_handlers_count': len(self._event_handlers),
            'timestamp': datetime.now().isoformat()
        }
    
    async def health_check(self) -> bool:
        """
        Perform a health check on the watcher.
        
        Returns:
            True if the watcher is healthy, False otherwise
        """
        try:
            # Basic health check - override in subclasses for specific checks
            return self.is_running
        except Exception as e:
            self.logger.error(f"Health check failed for {self.name}: {e}")
            return False

class WatcherManager:
    """
    Manager class for handling multiple watchers.
    """
    
    def __init__(self):
        self.watchers: Dict[str, BaseWatcher] = {}
        self.logger = logging.getLogger("watcher_manager")
    
    def register_watcher(self, watcher: BaseWatcher) -> None:
        """
        Register a watcher with the manager.
        
        Args:
            watcher: The watcher to register
        """
        self.watchers[watcher.name] = watcher
        self.logger.info(f"Registered watcher: {watcher.name}")
    
    def unregister_watcher(self, name: str) -> None:
        """
        Unregister a watcher from the manager.
        
        Args:
            name: Name of the watcher to unregister
        """
        if name in self.watchers:
            del self.watchers[name]
            self.logger.info(f"Unregistered watcher: {name}")
    
    async def start_all(self) -> None:
        """Start all registered watchers"""
        for watcher in self.watchers.values():
            await watcher.start()
    
    async def stop_all(self) -> None:
        """Stop all registered watchers"""
        for watcher in self.watchers.values():
            await watcher.stop()
    
    def get_watcher(self, name: str) -> Optional[BaseWatcher]:
        """
        Get a watcher by name.
        
        Args:
            name: Name of the watcher to retrieve
            
        Returns:
            The watcher if found, None otherwise
        """
        return self.watchers.get(name)
    
    def get_all_status(self) -> Dict[str, Dict[str, Any]]:
        """
        Get status of all registered watchers.
        
        Returns:
            Dictionary mapping watcher names to their status
        """
        return {name: watcher.get_status() for name, watcher in self.watchers.items()}
    
    async def health_check_all(self) -> Dict[str, bool]:
        """
        Perform health check on all watchers.
        
        Returns:
            Dictionary mapping watcher names to their health status
        """
        results = {}
        for name, watcher in self.watchers.items():
            results[name] = await watcher.health_check()
        return results

# Utility functions
def create_event(
    event_type: EventType,
    source: str,
    data: Dict[str, Any],
    metadata: Optional[Dict[str, Any]] = None
) -> Event:
    """
    Utility function to create an event.
    
    Args:
        event_type: Type of the event
        source: Source of the event
        data: Event data
        metadata: Optional metadata
        
    Returns:
        Created event
    """
    return Event(
        event_type=event_type,
        source=source,
        timestamp=datetime.now(),
        data=data,
        metadata=metadata
    )
