#!/usr/bin/env python3
"""
TubeArchivist-Emby Integration v5.0+ Compatible
Updated for TubeArchivist v5.0+ API compatibility

This script synchronizes metadata between TubeArchivist and Emby,
organizing YouTube channels as TV Shows with yearly seasons.
"""

import json
import os
import time
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Any
import requests
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
import threading
import signal
import sys

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class Config:
    """Configuration handler for the integration"""
    
    def __init__(self, config_file: str = "config.json"):
        self.config_file = config_file
        self.config = self.load_config()
        
    def load_config(self) -> Dict[str, Any]:
        """Load configuration from file or environment variables"""
        config = {}
        
        # Try to load from config file first
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, 'r') as f:
                    config = json.load(f)
                logger.info(f"Loaded config from {self.config_file}")
            except json.JSONDecodeError as e:
                logger.error(f"Error parsing config file: {e}")
        
        # Override with environment variables
        env_mapping = {
            'TA_URL': 'ta_url',
            'TA_TOKEN': 'ta_token', 
            'TA_VIDEO_PATH': 'ta_video_path',
            'EMBY_URL': 'emby_url',
            'EMBY_TOKEN': 'emby_token',
            'EMBY_FOLDER': 'emby_folder',
            'LISTEN_PORT': 'listen_port'
        }
        
        for env_var, config_key in env_mapping.items():
            if env_var in os.environ:
                config[config_key] = os.environ[env_var]
        
        # Set defaults
        config.setdefault('emby_folder', 'YouTube')
        config.setdefault('listen_port', 8001)
        config.setdefault('ta_video_path', '/youtube')
        
        # Validate required config
        required_keys = ['ta_url', 'ta_token', 'emby_url', 'emby_token']
        missing_keys = [key for key in required_keys if not config.get(key)]
        
        if missing_keys:
            raise ValueError(f"Missing required configuration: {', '.join(missing_keys)}")
        
        return config
    
    def get(self, key: str, default: Any = None) -> Any:
        """Get configuration value"""
        return self.config.get(key, default)


class TubeArchivistAPI:
    """TubeArchivist API client for v5.0+"""
    
    def __init__(self, base_url: str, token: str):
        self.base_url = base_url.rstrip('/')
        self.token = token
        self.session = requests.Session()
        self.session.headers.update({
            'Authorization': f'Token {token}',
            'Content-Type': 'application/json'
        })
        # Add retry strategy
        from requests.adapters import HTTPAdapter
        from urllib3.util.retry import Retry
        
        retry_strategy = Retry(
            total=3,
            status_forcelist=[429, 500, 502, 503, 504],
            method_whitelist=["HEAD", "GET", "OPTIONS"],
            backoff_factor=1
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)
    
    def _request(self, method: str, endpoint: str, **kwargs) -> requests.Response:
        """Make API request with error handling"""
        url = f"{self.base_url}/api/{endpoint.lstrip('/')}"
        
        try:
            response = self.session.request(method, url, timeout=30, **kwargs)
            response.raise_for_status()
            return response
        except requests.exceptions.RequestException as e:
            logger.error(f"API request failed: {method} {url} - {e}")
            raise
    
    def get_videos(self, params: Optional[Dict] = None) -> Dict:
        """Get videos from TubeArchivist"""
        endpoint = "video/"
        response = self._request('GET', endpoint, params=params or {})
        return response.json()
    
    def get_video(self, video_id: str) -> Dict:
        """Get specific video details"""
        endpoint = f"video/{video_id}/"
        response = self._request('GET', endpoint)
        return response.json()
    
    def get_channels(self, params: Optional[Dict] = None) -> Dict:
        """Get channels from TubeArchivist"""
        endpoint = "channel/"
        response = self._request('GET', endpoint, params=params or {})
        return response.json()
    
    def get_channel(self, channel_id: str) -> Dict:
        """Get specific channel details"""
        endpoint = f"channel/{channel_id}/"
        response = self._request('GET', endpoint)
        return response.json()
    
    def get_playlists(self, params: Optional[Dict] = None) -> Dict:
        """Get playlists from TubeArchivist"""
        endpoint = "playlist/"
        response = self._request('GET', endpoint, params=params or {})
        return response.json()
    
    def search(self, query: str, params: Optional[Dict] = None) -> Dict:
        """Search TubeArchivist content"""
        endpoint = "search/"
        search_params = {'query': query}
        if params:
            search_params.update(params)
        response = self._request('GET', endpoint, params=search_params)
        return response.json()
    
    def ping(self) -> bool:
        """Test API connectivity"""
        try:
            response = self._request('GET', "ping/")
            result = response.json()
            return result.get('response') == 'pong' or result.get('status') == 'ok'
        except Exception as e:
            logger.error(f"Ping failed: {e}")
            return False
    
    def get_stats(self) -> Dict:
        """Get TubeArchivist statistics"""
        try:
            response = self._request('GET', "stats/")
            return response.json()
        except Exception as e:
            logger.error(f"Failed to get stats: {e}")
            return {}


class EmbyAPI:
    """Emby API client"""
    
    def __init__(self, base_url: str, api_key: str):
        self.base_url = base_url.rstrip('/')
        self.api_key = api_key
        self.session = requests.Session()
        
    def _request(self, method: str, endpoint: str, **kwargs) -> requests.Response:
        """Make API request with error handling"""
        url = f"{self.base_url}/{endpoint.lstrip('/')}"
        
        # Add API key to params
        params = kwargs.get('params', {})
        params['api_key'] = self.api_key
        kwargs['params'] = params
        
        try:
            response = self.session.request(method, url, timeout=30, **kwargs)
            response.raise_for_status()
            return response
        except requests.exceptions.RequestException as e:
            logger.error(f"Emby API request failed: {method} {url} - {e}")
            raise
    
    def get_libraries(self) -> List[Dict]:
        """Get Emby media libraries"""
        response = self._request('GET', 'Library/VirtualFolders')
        return response.json()
    
    def get_library_items(self, library_id: str, item_type: str = None) -> Dict:
        """Get items from a specific library"""
        endpoint = f"Items"
        params = {'ParentId': library_id, 'Recursive': True}
        if item_type:
            params['IncludeItemTypes'] = item_type
        
        response = self._request('GET', endpoint, params=params)
        return response.json()
    
    def get_item(self, item_id: str) -> Dict:
        """Get specific item details"""
        response = self._request('GET', f'Items/{item_id}')
        return response.json()
    
    def update_item(self, item_id: str, data: Dict) -> bool:
        """Update item metadata"""
        try:
            response = self._request('POST', f'Items/{item_id}', json=data)
            return response.status_code in [200, 204]
        except Exception as e:
            logger.error(f"Failed to update item {item_id}: {e}")
            return False
    
    def refresh_library(self, library_id: str) -> bool:
        """Refresh a media library"""
        try:
            response = self._request('POST', f'Library/VirtualFolders/{library_id}/Refresh')
            return response.status_code in [200, 204]
        except Exception as e:
            logger.error(f"Failed to refresh library {library_id}: {e}")
            return False
    
    def create_season_folder(self, show_path: str, year: str) -> bool:
        """Create season folder for organizing videos by year"""
        season_path = Path(show_path) / f"Season {year}"
        try:
            season_path.mkdir(parents=True, exist_ok=True)
            logger.info(f"Created season folder: {season_path}")
            return True
        except Exception as e:
            logger.error(f"Failed to create season folder {season_path}: {e}")
            return False


class TubeArchivistEmbySync:
    """Main synchronization class"""
    
    def __init__(self, config: Config):
        self.config = config
        self.ta_api = TubeArchivistAPI(config.get('ta_url'), config.get('ta_token'))
        self.emby_api = EmbyAPI(config.get('emby_url'), config.get('emby_token'))
        self.youtube_library_id = None
        
    def verify_apis(self) -> bool:
        """Verify both APIs are accessible"""
        logger.info("Verifying API connections...")
        
        # Test TubeArchivist
        if not self.ta_api.ping():
            logger.error("TubeArchivist API connection failed")
            return False
        logger.info("TubeArchivist API connection successful")
        
        # Test Emby and find YouTube library
        try:
            libraries = self.emby_api.get_libraries()
            youtube_lib = next((lib for lib in libraries 
                              if lib['Name'] == self.config.get('emby_folder')), None)
            
            if not youtube_lib:
                logger.error(f"YouTube library '{self.config.get('emby_folder')}' not found in Emby")
                return False
            
            self.youtube_library_id = youtube_lib['ItemId']
            logger.info(f"Found YouTube library: {youtube_lib['Name']} (ID: {self.youtube_library_id})")
            return True
            
        except Exception as e:
            logger.error(f"Emby API connection failed: {e}")
            return False
    
    def sync_metadata(self) -> bool:
        """Main synchronization method"""
        logger.info("Starting metadata synchronization...")
        
        if not self.verify_apis():
            return False
        
        try:
            # Get all videos from TubeArchivist
            logger.info("Fetching videos from TubeArchivist...")
            ta_videos = self._get_all_ta_videos()
            logger.info(f"Found {len(ta_videos)} videos in TubeArchivist")
            
            # Get all items from Emby YouTube library
            logger.info("Fetching items from Emby...")
            emby_items = self.emby_api.get_library_items(self.youtube_library_id)
            
            # Process each video
            synced_count = 0
            for ta_video in ta_videos:
                if self._sync_video(ta_video, emby_items):
                    synced_count += 1
            
            logger.info(f"Synchronized {synced_count} videos")
            
            # Refresh library to pick up changes
            logger.info("Refreshing Emby library...")
            self.emby_api.refresh_library(self.youtube_library_id)
            
            return True
            
        except Exception as e:
            logger.error(f"Sync failed: {e}")
            return False
    
    def _get_all_ta_videos(self) -> List[Dict]:
        """Get all videos from TubeArchivist with pagination"""
        all_videos = []
        page = 1
        page_size = 50
        
        while True:
            params = {'page': page, 'page_size': page_size}
            response = self.ta_api.get_videos(params)
            
            videos = response.get('data', [])
            if not videos:
                break
                
            all_videos.extend(videos)
            
            if len(videos) < page_size:
                break
                
            page += 1
        
        return all_videos
    
    def _sync_video(self, ta_video: Dict, emby_items: Dict) -> bool:
        """Sync individual video metadata"""
        try:
            video_id = ta_video.get('youtube_id')
            if not video_id:
                logger.warning("Video missing YouTube ID, skipping")
                return False
            
            # Find corresponding Emby item
            emby_item = self._find_emby_item(video_id, emby_items)
            if not emby_item:
                logger.debug(f"Video {video_id} not found in Emby, skipping")
                return False
            
            # Prepare metadata update
            metadata = self._prepare_metadata(ta_video)
            
            # Update Emby item
            if self.emby_api.update_item(emby_item['Id'], metadata):
                logger.debug(f"Updated metadata for video: {ta_video.get('title', video_id)}")
                return True
            else:
                logger.warning(f"Failed to update video: {video_id}")
                return False
                
        except Exception as e:
            logger.error(f"Error syncing video {ta_video.get('youtube_id', 'unknown')}: {e}")
            return False
    
    def _find_emby_item(self, video_id: str, emby_items: Dict) -> Optional[Dict]:
        """Find Emby item by YouTube video ID"""
        for item in emby_items.get('Items', []):
            # Check if filename contains video ID
            if video_id in item.get('Path', ''):
                return item
            # Also check ProviderIds if available
            provider_ids = item.get('ProviderIds', {})
            if provider_ids.get('Youtube') == video_id:
                return item
        return None
    
    def _prepare_metadata(self, ta_video: Dict) -> Dict:
        """Prepare metadata for Emby update"""
        metadata = {
            'Name': ta_video.get('title', ''),
            'Overview': ta_video.get('description', ''),
            'PremiereDate': self._format_date(ta_video.get('published')),
            'ProductionYear': self._extract_year(ta_video.get('published')),
            'ProviderIds': {
                'Youtube': ta_video.get('youtube_id')
            }
        }
        
        # Add channel information
        channel = ta_video.get('channel', {})
        if channel:
            metadata['Studios'] = [{'Name': channel.get('channel_name', '')}]
            metadata['People'] = [{
                'Name': channel.get('channel_name', ''),
                'Type': 'Director',
                'Role': 'Channel'
            }]
        
        # Add tags from v5.0+ structure
        tags = []
        
        # Tags from video tags field
        video_tags = ta_video.get('tags', [])
        if video_tags:
            tags.extend(video_tags)
        
        # Add category as tag if available
        category = ta_video.get('category')
        if category:
            tags.append(f"Category: {category}")
        
        # Add duration info
        duration = ta_video.get('duration')
        if duration:
            # Convert duration to readable format
            if isinstance(duration, (int, float)):
                hours = int(duration // 3600)
                minutes = int((duration % 3600) // 60)
                if hours > 0:
                    tags.append(f"Duration: {hours}h {minutes}m")
                else:
                    tags.append(f"Duration: {minutes}m")
        
        # Add view count if available
        view_count = ta_video.get('stats', {}).get('view_count')
        if view_count:
            tags.append(f"Views: {view_count:,}")
        
        # Add upload status
        if ta_video.get('active', True):
            tags.append("Status: Active")
        else:
            tags.append("Status: Inactive")
        
        if tags:
            metadata['Tags'] = list(set(tags))  # Remove duplicates
        
        # Add additional metadata for v5.0+
        metadata.update({
            'CommunityRating': self._calculate_rating(ta_video),
            'OfficialRating': 'NR',  # Not Rated
            'CustomRating': 'YouTube Video',
        })
        
        # Add subtitle information if available
        subtitles = ta_video.get('subtitles', [])
        if subtitles:
            subtitle_langs = [sub.get('lang', 'Unknown') for sub in subtitles]
            metadata['Tags'] = metadata.get('Tags', []) + [f"Subtitles: {', '.join(subtitle_langs)}"]
        
        return metadata
    
    def _calculate_rating(self, ta_video: Dict) -> Optional[float]:
        """Calculate a rating based on video metrics"""
        try:
            stats = ta_video.get('stats', {})
            like_count = stats.get('like_count', 0)
            view_count = stats.get('view_count', 0)
            
            if view_count > 0 and like_count > 0:
                # Simple rating calculation: like ratio * view popularity factor
                like_ratio = like_count / view_count
                popularity_factor = min(view_count / 1000000, 1.0)  # Cap at 1M views
                rating = (like_ratio * 10 * (1 + popularity_factor)) / 2
                return min(max(rating, 1.0), 10.0)  # Clamp between 1-10
        except (TypeError, ZeroDivisionError):
            pass
        
        return None
    
    def _format_date(self, date_str: str) -> Optional[str]:
        """Format date for Emby"""
        if not date_str:
            return None
        
        try:
            # TubeArchivist typically stores dates in ISO format
            dt = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
            return dt.strftime('%Y-%m-%dT%H:%M:%S.%fZ')
        except Exception as e:
            logger.warning(f"Failed to parse date {date_str}: {e}")
            return None
    
    def _extract_year(self, date_str: str) -> Optional[int]:
        """Extract year from date string"""
        if not date_str:
            return None
        
        try:
            dt = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
            return dt.year
        except Exception as e:
            logger.warning(f"Failed to extract year from {date_str}: {e}")
            return None
    
    def organize_by_year(self) -> bool:
        """Organize videos into yearly seasons"""
        logger.info("Organizing videos by year...")
        
        try:
            # Get channel structure from TubeArchivist
            channels_response = self.ta_api.get_channels()
            channels = channels_response.get('data', [])
            
            base_path = Path(self.config.get('ta_video_path'))
            
            for channel in channels:
                channel_id = channel.get('channel_id')
                channel_name = channel.get('channel_name')
                
                if not channel_id or not channel_name:
                    continue
                
                logger.info(f"Processing channel: {channel_name}")
                
                # Get videos for this channel
                videos_response = self.ta_api.get_videos({
                    'channel': channel_id,
                    'page_size': 1000
                })
                
                videos = videos_response.get('data', [])
                
                # Group videos by year
                years = {}
                for video in videos:
                    year = self._extract_year(video.get('published'))
                    if year:
                        if year not in years:
                            years[year] = []
                        years[year].append(video)
                
                # Create season folders
                channel_path = base_path / channel_name
                if channel_path.exists():
                    for year in years:
                        season_path = channel_path / f"Season {year}"
                        season_path.mkdir(exist_ok=True)
                        logger.debug(f"Created season folder: {season_path}")
            
            logger.info("Video organization by year complete")
            return True
            
        except Exception as e:
            logger.error(f"Failed to organize videos by year: {e}")
            return False


class NotificationHandler(BaseHTTPRequestHandler):
    """HTTP handler for TubeArchivist notifications"""
    
    def __init__(self, sync_instance: TubeArchivistEmbySync):
        self.sync_instance = sync_instance
    
    def __call__(self, *args, **kwargs):
        # Store sync_instance in class for use in handler methods
        NotificationHandler.sync_instance = self.sync_instance
        return super().__init__(*args, **kwargs)
    
    def do_POST(self):
        """Handle POST notifications from TubeArchivist"""
        try:
            content_length = int(self.headers.get('Content-Length', 0))
            if content_length > 0:
                post_data = self.rfile.read(content_length)
                logger.info(f"Received notification: {post_data.decode()}")
            
            # Trigger sync
            logger.info("Triggering metadata sync...")
            success = self.sync_instance.sync_metadata()
            
            if success:
                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(b'{"status": "success"}')
            else:
                self.send_response(500)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(b'{"status": "error"}')
                
        except Exception as e:
            logger.error(f"Error handling notification: {e}")
            self.send_response(500)
            self.end_headers()
    
    def do_GET(self):
        """Handle GET requests (health check)"""
        self.send_response(200)
        self.send_header('Content-type', 'application/json')
        self.end_headers()
        self.wfile.write(b'{"status": "running"}')
    
    def log_message(self, format, *args):
        """Override to use our logger"""
        logger.info(f"HTTP: {format % args}")


def signal_handler(signum, frame):
    """Handle shutdown signals"""
    logger.info("Received shutdown signal, exiting...")
    sys.exit(0)


def main():
    """Main function"""
    # Set up signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    try:
        # Load configuration
        config = Config()
        logger.info("Configuration loaded successfully")
        
        # Create sync instance
        sync = TubeArchivistEmbySync(config)
        
        # Check if running as one-time sync or server
        if len(sys.argv) > 1 and sys.argv[1] == '--server':
            # Run as HTTP server for notifications
            port = int(config.get('listen_port'))
            server = HTTPServer(('0.0.0.0', port), NotificationHandler(sync))
            
            logger.info(f"Starting notification server on port {port}")
            logger.info("Send notifications to trigger sync, or Ctrl+C to exit")
            
            server.serve_forever()
        else:
            # Run one-time sync
            logger.info("Running one-time synchronization")
            success = sync.sync_metadata()
            
            if success:
                logger.info("Synchronization completed successfully")
                sys.exit(0)
            else:
                logger.error("Synchronization failed")
                sys.exit(1)
                
    except Exception as e:
        logger.error(f"Application error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
