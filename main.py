#!/usr/bin/env python3
"""
TubeArchivist Emby Integration v5.0
A modern integration to sync metadata between TubeArchivist v5.0+ and Emby
"""

import argparse
import json
import logging
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any
import schedule

# urllib3 compatibility imports
import urllib3
from urllib3.util.retry import Retry
from requests.adapters import HTTPAdapter
import requests

# Load environment variables
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# urllib3 Compatibility Fix
class CompatibleHTTPAdapter(HTTPAdapter):
    """HTTPAdapter that handles urllib3 version compatibility"""
    
    def __init__(self, *args, **kwargs):
        retry_config = kwargs.pop('retry_config', {})
        super().__init__(*args, **kwargs)
        
        if retry_config:
            self.retry_config = retry_config
            self.mount_retry_strategy()
    
    def mount_retry_strategy(self):
        """Mount retry strategy with version compatibility"""
        retry_config = getattr(self, 'retry_config', {})
        
        default_config = {
            'total': 3,
            'backoff_factor': 0.3,
            'status_forcelist': [500, 502, 503, 504],
            'method_list': ['HEAD', 'GET', 'OPTIONS', 'POST', 'PUT', 'DELETE']
        }
        default_config.update(retry_config)
        
        # Handle urllib3 version compatibility
        try:
            # Try new parameter name first (urllib3 >= 1.26.0)
            retry_strategy = Retry(
                total=default_config['total'],
                backoff_factor=default_config['backoff_factor'],
                status_forcelist=default_config['status_forcelist'],
                allowed_methods=default_config['method_list']
            )
        except TypeError:
            # Fall back to old parameter name (urllib3 < 1.26.0)
            try:
                retry_strategy = Retry(
                    total=default_config['total'],
                    backoff_factor=default_config['backoff_factor'],
                    status_forcelist=default_config['status_forcelist'],
                    method_whitelist=default_config['method_list']
                )
            except TypeError:
                # If both fail, create without method specification
                retry_strategy = Retry(
                    total=default_config['total'],
                    backoff_factor=default_config['backoff_factor'],
                    status_forcelist=default_config['status_forcelist']
                )
        
        self.max_retries = retry_strategy

def create_session_with_retry(retry_config=None):
    """Create a requests session with retry capability"""
    session = requests.Session()
    
    default_retry_config = {
        'total': 3,
        'backoff_factor': 0.3,
        'status_forcelist': [500, 502, 503, 504],
        'method_list': ['HEAD', 'GET', 'OPTIONS', 'POST', 'PUT', 'DELETE']
    }
    
    if retry_config:
        default_retry_config.update(retry_config)
    
    adapter = CompatibleHTTPAdapter(retry_config=default_retry_config)
    session.mount('http://', adapter)
    session.mount('https://', adapter)
    
    return session

# Configuration Management
class Config:
    def __init__(self):
        self.config = self._load_config()
        self._validate_config()
    
    def _load_config(self) -> Dict[str, Any]:
        """Load configuration from environment variables and config file"""
        config = {}
        
        # Try to load from config file first
        config_file = Path("config.json")
        if config_file.exists():
            try:
                with open(config_file, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                logging.info("Configuration loaded from config.json")
            except Exception as e:
                logging.warning(f"Failed to load config.json: {e}")
        
        # Override with environment variables
        env_mapping = {
            'TA_URL': 'tubearchivist_url',
            'TA_TOKEN': 'tubearchivist_token', 
            'EMBY_URL': 'emby_url',
            'EMBY_TOKEN': 'emby_token',
            'EMBY_FOLDER': 'emby_folder',
            'TA_VIDEO_PATH': 'tubearchivist_video_path',
            'LISTEN_PORT': 'listen_port',
            'LOG_LEVEL': 'log_level'
        }
        
        for env_key, config_key in env_mapping.items():
            env_value = os.getenv(env_key)
            if env_value:
                config[config_key] = env_value
        
        # Set defaults
        defaults = {
            'emby_folder': 'YouTube',
            'listen_port': 8001,
            'log_level': 'INFO',
            'sync_interval_hours': 24
        }
        
        for key, default_value in defaults.items():
            if key not in config:
                config[key] = default_value
        
        return config
    
    def _validate_config(self):
        """Validate required configuration"""
        required = ['tubearchivist_url', 'tubearchivist_token', 'emby_url', 'emby_token']
        missing = [key for key in required if not self.config.get(key)]
        
        if missing:
            raise ValueError(f"Missing required configuration: {', '.join(missing)}")
    
    def get(self, key: str, default=None):
        """Get configuration value"""
        return self.config.get(key, default)

# API Clients
class TubeArchivistClient:
    def __init__(self, base_url: str, token: str):
        self.base_url = base_url.rstrip('/')
        self.token = token
        self.session = create_session_with_retry()
        self.session.headers.update({
            'Authorization': f'Token {token}',
            'Content-Type': 'application/json'
        })
    
    def ping(self) -> bool:
        """Test connection to TubeArchivist"""
        try:
            response = self.session.get(f"{self.base_url}/api/ping/", timeout=10)
            return response.status_code == 200
        except Exception as e:
            logging.error(f"Failed to ping TubeArchivist: {e}")
            return False
    
    def get_videos(self, page: int = 1, limit: int = 50) -> Dict[str, Any]:
        """Get videos from TubeArchivist with pagination"""
        try:
            params = {'page': page, 'limit': limit}
            response = self.session.get(f"{self.base_url}/api/video/", params=params, timeout=30)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logging.error(f"Failed to get videos from TubeArchivist: {e}")
            return {}
    
    def get_all_videos(self) -> List[Dict[str, Any]]:
        """Get all videos from TubeArchivist"""
        all_videos = []
        page = 1
        
        while True:
            data = self.get_videos(page=page, limit=100)
            videos = data.get('data', [])
            
            if not videos:
                break
                
            all_videos.extend(videos)
            logging.info(f"Retrieved {len(videos)} videos from page {page}")
            
            # Check if there are more pages
            if len(videos) < 100:
                break
                
            page += 1
        
        logging.info(f"Total videos retrieved: {len(all_videos)}")
        return all_videos
    
    def get_channels(self) -> List[Dict[str, Any]]:
        """Get all channels from TubeArchivist"""
        try:
            response = self.session.get(f"{self.base_url}/api/channel/", timeout=30)
            response.raise_for_status()
            return response.json().get('data', [])
        except Exception as e:
            logging.error(f"Failed to get channels from TubeArchivist: {e}")
            return []

class EmbyClient:
    def __init__(self, base_url: str, api_key: str, library_name: str):
        self.base_url = base_url.rstrip('/')
        self.api_key = api_key
        self.library_name = library_name
        self.session = create_session_with_retry()
        self.library_id = None
    
    def ping(self) -> bool:
        """Test connection to Emby"""
        try:
            response = self.session.get(
                f"{self.base_url}/System/Info",
                params={'api_key': self.api_key},
                timeout=10
            )
            return response.status_code == 200
        except Exception as e:
            logging.error(f"Failed to ping Emby: {e}")
            return False
    
    def get_library_id(self) -> Optional[str]:
        """Get the library ID for the YouTube folder"""
        if self.library_id:
            return self.library_id
            
        try:
            response = self.session.get(
                f"{self.base_url}/Library/VirtualFolders",
                params={'api_key': self.api_key},
                timeout=10
            )
            response.raise_for_status()
            
            for library in response.json():
                if library.get('Name') == self.library_name:
                    # Get the actual library ID
                    locations = library.get('Locations', [])
                    if locations:
                        # Use the first collection type ID
                        self.library_id = library.get('ItemId')
                        return self.library_id
                        
        except Exception as e:
            logging.error(f"Failed to get library ID: {e}")
        
        return None
    
    def get_library_items(self) -> List[Dict[str, Any]]:
        """Get all items from the YouTube library"""
        library_id = self.get_library_id()
        if not library_id:
            # Try alternative approach
            return self._get_library_items_alternative()
        
        try:
            response = self.session.get(
                f"{self.base_url}/Items",
                params={
                    'api_key': self.api_key,
                    'ParentId': library_id,
                    'Recursive': 'true',
                    'IncludeItemTypes': 'Episode'
                },
                timeout=30
            )
            response.raise_for_status()
            return response.json().get('Items', [])
        except Exception as e:
            logging.error(f"Failed to get library items: {e}")
            return []
    
    def _get_library_items_alternative(self) -> List[Dict[str, Any]]:
        """Alternative method to get library items"""
        try:
            response = self.session.get(
                f"{self.base_url}/Items",
                params={
                    'api_key': self.api_key,
                    'Recursive': 'true',
                    'IncludeItemTypes': 'Episode',
                    'SearchTerm': ''
                },
                timeout=30
            )
            response.raise_for_status()
            
            # Filter items that belong to our library
            all_items = response.json().get('Items', [])
            library_items = []
            
            for item in all_items:
                # Check if item path contains our expected path patterns
                path = item.get('Path', '')
                if any(keyword in path.lower() for keyword in ['youtube', 'tubearchivist']):
                    library_items.append(item)
            
            return library_items
        except Exception as e:
            logging.error(f"Failed to get library items (alternative): {e}")
            return []
    
    def update_item_metadata(self, item_id: str, metadata: Dict[str, Any]) -> bool:
        """Update metadata for an Emby item"""
        try:
            response = self.session.post(
                f"{self.base_url}/Items/{item_id}",
                params={'api_key': self.api_key},
                json=metadata,
                timeout=10
            )
            return response.status_code in [200, 204]
        except Exception as e:
            logging.error(f"Failed to update item {item_id}: {e}")
            return False
    
    def refresh_library(self) -> bool:
        """Refresh the YouTube library"""
        library_id = self.get_library_id()
        if not library_id:
            logging.warning("Cannot refresh library: Library ID not found")
            return False
        
        try:
            response = self.session.post(
                f"{self.base_url}/Library/VirtualFolders/{library_id}/Refresh",
                params={'api_key': self.api_key},
                timeout=10
            )
            return response.status_code in [200, 204]
        except Exception as e:
            logging.error(f"Failed to refresh library: {e}")
            return False

# Main Integration Class
class TubeArchivistEmbyIntegration:
    def __init__(self, config: Config):
        self.config = config
        self.ta_client = TubeArchivistClient(
            config.get('tubearchivist_url'),
            config.get('tubearchivist_token')
        )
        self.emby_client = EmbyClient(
            config.get('emby_url'),
            config.get('emby_token'),
            config.get('emby_folder')
        )
    
    def test_connections(self) -> bool:
        """Test connections to both services"""
        logging.info("Testing connections...")
        
        ta_ok = self.ta_client.ping()
        emby_ok = self.emby_client.ping()
        
        if ta_ok:
            logging.info("✓ TubeArchivist connection successful")
        else:
            logging.error("✗ TubeArchivist connection failed")
        
        if emby_ok:
            logging.info("✓ Emby connection successful")
        else:
            logging.error("✗ Emby connection failed")
        
        return ta_ok and emby_ok
    
    def sync_metadata(self) -> bool:
        """Perform full metadata sync"""
        if not self.test_connections():
            return False
        
        logging.info("Starting metadata sync...")
        start_time = time.time()
        
        # Get all videos from TubeArchivist
        ta_videos = self.ta_client.get_all_videos()
        if not ta_videos:
            logging.warning("No videos found in TubeArchivist")
            return False
        
        # Get all items from Emby library
        emby_items = self.emby_client.get_library_items()
        if not emby_items:
            logging.warning("No items found in Emby library")
            return False
        
        # Create mapping of YouTube IDs to Emby items
        emby_by_youtube_id = {}
        for item in emby_items:
            # Look for YouTube ID in various places
            youtube_id = self._extract_youtube_id(item)
            if youtube_id:
                emby_by_youtube_id[youtube_id] = item
        
        logging.info(f"Found {len(emby_by_youtube_id)} Emby items with YouTube IDs")
        
        # Process each TubeArchivist video
        updated_count = 0
        for video in ta_videos:
            youtube_id = video.get('youtube_id')
            if not youtube_id:
                continue
            
            emby_item = emby_by_youtube_id.get(youtube_id)
            if not emby_item:
                continue
            
            # Update metadata
            if self._update_emby_item_metadata(emby_item, video):
                updated_count += 1
        
        end_time = time.time()
        duration = end_time - start_time
        
        logging.info(f"Sync completed: {updated_count} items updated in {duration:.2f} seconds")
        return True
    
    def _extract_youtube_id(self, emby_item: Dict[str, Any]) -> Optional[str]:
        """Extract YouTube ID from Emby item"""
        # Check various metadata fields where YouTube ID might be stored
        youtube_id = None
        
        # Check custom metadata
        provider_ids = emby_item.get('ProviderIds', {})
        if 'YouTube' in provider_ids:
            youtube_id = provider_ids['YouTube']
        
        # Check filename
        if not youtube_id:
            path = emby_item.get('Path', '')
            filename = Path(path).stem if path else ''
            # Extract 11-character YouTube ID from filename
            import re
            match = re.search(r'[a-zA-Z0-9_-]{11}', filename)
            if match:
                youtube_id = match.group(0)
        
        return youtube_id
    
    def _update_emby_item_metadata(self, emby_item: Dict[str, Any], ta_video: Dict[str, Any]) -> bool:
        """Update a single Emby item with TubeArchivist metadata"""
        item_id = emby_item.get('Id')
        if not item_id:
            return False
        
        # Prepare metadata update
        metadata = {
            'Name': ta_video.get('title', ''),
            'Overview': ta_video.get('description', ''),
            'Studios': [{'Name': ta_video.get('channel', {}).get('channel_name', '')}] if ta_video.get('channel') else [],
            'Tags': ta_video.get('tags', []),
            'PremiereDate': ta_video.get('published'),
            'ProductionYear': self._extract_year(ta_video.get('published')),
            'ProviderIds': {
                'YouTube': ta_video.get('youtube_id', '')
            }
        }
        
        # Remove empty fields
        metadata = {k: v for k, v in metadata.items() if v}
        
        success = self.emby_client.update_item_metadata(item_id, metadata)
        if success:
            logging.debug(f"Updated metadata for: {ta_video.get('title', 'Unknown')}")
        
        return success
    
    def _extract_year(self, date_string: Optional[str]) -> Optional[int]:
        """Extract year from date string"""
        if not date_string:
            return None
        
        try:
            # Handle various date formats
            from dateutil.parser import parse
            date_obj = parse(date_string)
            return date_obj.year
        except Exception:
            return None

def setup_logging(level: str = 'INFO'):
    """Setup logging configuration"""
    numeric_level = getattr(logging, level.upper(), logging.INFO)
    
    logging.basicConfig(
        level=numeric_level,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler(sys.stdout),
        ]
    )

def main():
    parser = argparse.ArgumentParser(description='TubeArchivist Emby Integration v5.0')
    parser.add_argument('--server', action='store_true', help='Run as server for notifications')
    parser.add_argument('--sync', action='store_true', help='Perform one-time sync')
    parser.add_argument('--test', action='store_true', help='Test connections only')
    args = parser.parse_args()
    
    try:
        # Load configuration
        config = Config()
        setup_logging(config.get('log_level', 'INFO'))
        logging.info("Configuration loaded successfully")
        
        # Create integration instance
        integration = TubeArchivistEmbyIntegration(config)
        
        if args.test:
            # Test connections only
            success = integration.test_connections()
            sys.exit(0 if success else 1)
        
        elif args.server:
            # Run as server
            logging.info("Starting server mode...")
            # Here you would implement your notification server
            # For now, we'll run scheduled sync
            schedule.every(config.get('sync_interval_hours', 24)).hours.do(integration.sync_metadata)
            
            while True:
                schedule.run_pending()
                time.sleep(60)
        
        else:
            # Default: one-time sync
            success = integration.sync_metadata()
            sys.exit(0 if success else 1)
    
    except Exception as e:
        logging.error(f"Application error: {e}")
        sys.exit(1)

if __name__ == '__main__':
    main()
