"""
Database Adapter for GirlsManager

Provides database integration for the existing GirlsManager class without 
breaking existing functionality. Implements Strangler Fig pattern to gradually
transition from JSON to PostgreSQL storage.
"""

import asyncio
import json
import logging
from typing import Dict, Any, Optional, List
from datetime import datetime, timezone
from pathlib import Path

from src.database.integration import get_database_integration, DatabaseIntegrationManager
from src.core.girls_manager import GirlProfile
from src.utils.logger import setup_logger
from src.utils.exceptions import DataStorageError


class DatabaseGirlsAdapter:
    """
    Database adapter for GirlsManager that provides seamless integration
    between existing JSON-based storage and new PostgreSQL database.
    """
    
    def __init__(self, girls_manager=None):
        self.girls_manager = girls_manager
        self.logger = setup_logger(__name__)
        self._db_integration: Optional[DatabaseIntegrationManager] = None
        
    async def initialize(self) -> bool:
        """Initialize database adapter"""
        try:
            self._db_integration = get_database_integration()
            if not self._db_integration:
                self.logger.warning("Database integration not available, using JSON fallback")
                return False
            
            self.logger.info("Database adapter initialized successfully")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to initialize database adapter: {e}")
            return False
    
    def is_database_available(self) -> bool:
        """Check if database integration is available and healthy"""
        return (self._db_integration is not None and 
                self._db_integration._is_initialized and
                self._db_integration._components_migrated.get('users', False))
    
    async def load_profile(self, chat_id: int) -> Optional[GirlProfile]:
        """
        Load profile with database integration support
        Falls back to original JSON method if database unavailable
        """
        try:
            if self.is_database_available():
                # Try database first
                profile_data = await self._db_integration.get_user_profile(chat_id)
                
                if profile_data:
                    # Convert database format to GirlProfile
                    return self._convert_db_to_profile(profile_data)
            
            # Fallback to original JSON method
            if self.girls_manager:
                return await self.girls_manager.load_profile(chat_id)
            
            return None
            
        except Exception as e:
            self.logger.error(f"Error loading profile {chat_id}: {e}")
            
            # Emergency fallback to JSON
            if self.girls_manager:
                try:
                    return await self.girls_manager.load_profile(chat_id)
                except Exception as fallback_error:
                    self.logger.error(f"JSON fallback also failed: {fallback_error}")
            
            return None
    
    async def save_profile(self, profile: GirlProfile) -> bool:
        """
        Save profile with database integration support
        Dual-write during migration phase for safety
        """
        success = False
        
        try:
            if self.is_database_available():
                # Convert profile to database format
                profile_data = self._convert_profile_to_db(profile)
                
                # Save to database
                db_success = await self._db_integration.save_user_profile(
                    profile.chat_id, profile_data
                )
                
                if db_success:
                    success = True
                    self.logger.debug(f"Profile {profile.chat_id} saved to database")
            
            # During migration: also save to JSON for safety
            # In pure database mode: fallback to JSON on database failure
            if (self.girls_manager and 
                (not self.is_database_available() or 
                 not success or 
                 self._is_dual_write_enabled())):
                
                json_success = await self.girls_manager.save_profile(profile)
                if not success:  # Database failed, JSON is primary
                    success = json_success
                    
        except Exception as e:
            self.logger.error(f"Error saving profile {profile.chat_id}: {e}")
            
            # Emergency fallback to JSON
            if self.girls_manager:
                try:
                    success = await self.girls_manager.save_profile(profile)
                except Exception as fallback_error:
                    self.logger.error(f"JSON fallback save failed: {fallback_error}")
        
        return success
    
    async def update_last_activity(self, chat_id: int) -> bool:
        """Update user's last activity timestamp"""
        try:
            if self.is_database_available():
                success = await self._db_integration.update_user_activity(chat_id)
                if success:
                    return True
            
            # Fallback to original method
            if self.girls_manager:
                return await self.girls_manager.update_last_activity(chat_id)
            
            return False
            
        except Exception as e:
            self.logger.error(f"Error updating last activity {chat_id}: {e}")
            return False
    
    async def ensure_girl(self, chat_id: int, name: str) -> GirlProfile:
        """
        Ensure girl profile exists, create if needed
        Uses database if available, falls back to JSON
        """
        try:
            # Try to load existing profile
            profile = await self.load_profile(chat_id)
            
            if profile:
                # Update name if different
                if profile.name != name:
                    profile.name = name
                    await self.save_profile(profile)
                return profile
            
            # Create new profile
            new_profile = GirlProfile(
                chat_id=chat_id,
                name=name,
                last_activity=datetime.now(timezone.utc).isoformat(),
                message_count=0
            )
            
            await self.save_profile(new_profile)
            return new_profile
            
        except Exception as e:
            self.logger.error(f"Error ensuring girl {chat_id}: {e}")
            raise DataStorageError(f"Failed to ensure girl profile: {e}")
    
    async def list_girls(self) -> List[GirlProfile]:
        """
        List all girl profiles
        Combines database and JSON sources during migration
        """
        profiles = []
        
        try:
            if self.is_database_available():
                # Get profiles from database
                # This would need to be implemented in the data store
                # For now, fall through to JSON method
                pass
            
            # Get profiles from JSON
            if self.girls_manager:
                json_profiles = await self.girls_manager.list_girls()
                profiles.extend(json_profiles)
            
            # Remove duplicates (prefer database version)
            seen_chat_ids = set()
            unique_profiles = []
            
            for profile in profiles:
                if profile.chat_id not in seen_chat_ids:
                    unique_profiles.append(profile)
                    seen_chat_ids.add(profile.chat_id)
            
            return unique_profiles
            
        except Exception as e:
            self.logger.error(f"Error listing girls: {e}")
            return []
    
    async def update_profile(self, chat_id: int, message_text: str) -> bool:
        """
        Update profile with new message
        Integrates with analytics logging
        """
        try:
            # Load current profile
            profile = await self.load_profile(chat_id)
            if not profile:
                self.logger.warning(f"Profile not found for chat_id {chat_id}")
                return False
            
            # Update message count and activity
            profile.message_count += 1
            profile.last_activity = datetime.now(timezone.utc).isoformat()
            
            # Save updated profile
            success = await self.save_profile(profile)
            
            # Log analytics event if database available
            if self.is_database_available():
                await self._db_integration.log_analytics_event(
                    event_type="message_received",
                    event_data={
                        "chat_id": chat_id,
                        "message_length": len(message_text),
                        "message_count": profile.message_count
                    },
                    dimensions={
                        "user_name": profile.name,
                        "timestamp": profile.last_activity
                    }
                )
            
            return success
            
        except Exception as e:
            self.logger.error(f"Error updating profile {chat_id}: {e}")
            return False
    
    # Migration and compatibility methods
    
    def _is_dual_write_enabled(self) -> bool:
        """Check if dual-write mode is enabled during migration"""
        if not self._db_integration:
            return False
        
        migration_status = self._db_integration.get_migration_status()
        return (migration_status.get('enabled', False) and 
                not migration_status.get('store_status', {}).get('complete', False))
    
    def _convert_profile_to_db(self, profile: GirlProfile) -> Dict[str, Any]:
        """
        Convert GirlProfile to database format
        
        Args:
            profile: GirlProfile instance
            
        Returns:
            Dictionary suitable for database storage
        """
        return {
            'telegram_id': profile.chat_id,
            'name': profile.name,
            'profile': {
                'message_count': profile.message_count,
                'profile_data': profile.profile,
                'summary': profile.summary,
                'previous_response_id': profile.previous_response_id
            },
            'preferences': {},  # Can be expanded later
            'last_activity': profile.last_activity,
            'created_at': datetime.now(timezone.utc).isoformat(),
            'updated_at': datetime.now(timezone.utc).isoformat()
        }
    
    def _convert_db_to_profile(self, db_data: Dict[str, Any]) -> GirlProfile:
        """
        Convert database format to GirlProfile
        
        Args:
            db_data: Database record dictionary
            
        Returns:
            GirlProfile instance
        """
        profile_data = db_data.get('profile', {})
        
        return GirlProfile(
            chat_id=db_data.get('telegram_id', 0),
            name=db_data.get('name', ''),
            last_activity=db_data.get('last_activity'),
            message_count=profile_data.get('message_count', 0),
            summary=profile_data.get('summary', {}),
            profile=profile_data.get('profile_data', {}),
            previous_response_id=profile_data.get('previous_response_id')
        )
    
    # Analytics and monitoring methods
    
    async def get_adapter_metrics(self) -> Dict[str, Any]:
        """Get adapter-specific performance metrics"""
        metrics = {
            'database_available': self.is_database_available(),
            'dual_write_enabled': self._is_dual_write_enabled(),
            'fallback_to_json': 0,  # Would track this in real usage
            'database_operations': 0,  # Would track this in real usage
        }
        
        if self._db_integration:
            db_metrics = await self._db_integration.get_performance_metrics()
            metrics['database_metrics'] = db_metrics
        
        return metrics
    
    async def health_check(self) -> Dict[str, Any]:
        """Perform health check on adapter components"""
        health = {
            'adapter_status': 'healthy',
            'database_integration': 'unknown',
            'json_fallback': 'unknown',
            'timestamp': datetime.now(timezone.utc).isoformat()
        }
        
        try:
            # Check database integration
            if self._db_integration:
                db_health = await self._db_integration.health_check()
                health['database_integration'] = db_health.get('overall', 'unknown')
            else:
                health['database_integration'] = 'not_available'
            
            # Check JSON fallback
            if self.girls_manager:
                try:
                    # Test JSON operations
                    test_profiles = await self.girls_manager.list_girls()
                    health['json_fallback'] = 'healthy'
                except:
                    health['json_fallback'] = 'unhealthy'
            else:
                health['json_fallback'] = 'not_available'
            
            # Overall status
            if (health['database_integration'] in ['healthy', 'degraded'] or 
                health['json_fallback'] == 'healthy'):
                health['adapter_status'] = 'healthy'
            else:
                health['adapter_status'] = 'unhealthy'
            
        except Exception as e:
            health['adapter_status'] = 'error'
            health['error'] = str(e)
        
        return health


# Factory function for easy integration
async def create_database_adapter(girls_manager=None) -> DatabaseGirlsAdapter:
    """
    Create and initialize database adapter for GirlsManager
    
    Args:
        girls_manager: Existing GirlsManager instance for fallback
        
    Returns:
        Initialized DatabaseGirlsAdapter
    """
    adapter = DatabaseGirlsAdapter(girls_manager)
    await adapter.initialize()
    return adapter
