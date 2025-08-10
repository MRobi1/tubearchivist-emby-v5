#!/usr/bin/env python3
"""
Utility scripts for TubeArchivist-Emby Integration
"""

import json
import sys
import argparse
import logging
from pathlib import Path
from main import Config, TubeArchivistAPI, EmbyAPI, TubeArchivistEmbySync

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def health_check():
    """Perform health check on all components"""
    print("🏥 TubeArchivist-Emby Health Check")
    print("=" * 50)
    
    try:
        config = Config()
        print("✅ Configuration loaded successfully")
    except Exception as e:
        print(f"❌ Configuration error: {e}")
        return False
    
    # Test TubeArchivist API
    try:
        ta_api = TubeArchivistAPI(config.get('ta_url'), config.get('ta_token'))
        if ta_api.ping():
            print("✅ TubeArchivist API connection successful")
            
            # Test getting videos
            videos = ta_api.get_videos({'page_size': 1})
            video_count = videos.get('total', 0)
            print(f"   📹 Total videos in TubeArchivist: {video_count}")
        else:
            print("❌ TubeArchivist API ping failed")
            return False
    except Exception as e:
        print(f"❌ TubeArchivist API error: {e}")
        return False
    
    # Test Emby API
    try:
        emby_api = EmbyAPI(config.get('emby_url'), config.get('emby_token'))
        libraries = emby_api.get_libraries()
        print("✅ Emby API connection successful")
        
        # Find YouTube library
        youtube_lib = next((lib for lib in libraries 
                          if lib['Name'] == config.get('emby_folder')), None)
        
        if youtube_lib:
            print(f"✅ YouTube library found: {youtube_lib['Name']}")
            
            # Get library items
            items = emby_api.get_library_items(youtube_lib['ItemId'])
            item_count = items.get('TotalRecordCount', 0)
            print(f"   📺 Total items in Emby library: {item_count}")
        else:
            print(f"❌ YouTube library '{config.get('emby_folder')}' not found")
            print("   Available libraries:")
            for lib in libraries:
                print(f"   - {lib['Name']}")
            return False
    except Exception as e:
        print(f"❌ Emby API error: {e}")
        return False
    
    # Check file system access
    video_path = Path(config.get('ta_video_path'))
    if video_path.exists():
        print(f"✅ Video path accessible: {video_path}")
        
        # Count channel folders
        try:
            channel_folders = [p for p in video_path.iterdir() if p.is_dir()]
            print(f"   📁 Channel folders found: {len(channel_folders)}")
        except Exception as e:
            print(f"   ⚠️  Warning: Could not count channel folders: {e}")
    else:
        print(f"❌ Video path not accessible: {video_path}")
        return False
    
    print("\n🎉 Health check completed successfully!")
    return True


def sync_stats():
    """Display synchronization statistics"""
    print("📊 TubeArchivist-Emby Sync Statistics")
    print("=" * 50)
    
    try:
        config = Config()
        sync = TubeArchivistEmbySync(config)
        
        if not sync.verify_apis():
            print("❌ API verification failed")
            return False
        
        # Get TubeArchivist stats
        ta_videos = sync._get_all_ta_videos()
        ta_channels_response = sync.ta_api.get_channels()
        ta_channels = ta_channels_response.get('data', [])
        
        print(f"📹 TubeArchivist Videos: {len(ta_videos)}")
        print(f"📺 TubeArchivist Channels: {len(ta_channels)}")
        
        # Get Emby stats
        emby_items = sync.emby_api.get_library_items(sync.youtube_library_id)
        emby_shows = [item for item in emby_items.get('Items', []) 
                     if item.get('Type') == 'Series']
        emby_episodes = [item for item in emby_items.get('Items', []) 
                        if item.get('Type') == 'Episode']
        
        print(f"📺 Emby Shows (Channels): {len(emby_shows)}")
        print(f"📹 Emby Episodes (Videos): {len(emby_episodes)}")
        
        # Calculate sync percentage
        if len(ta_videos) > 0:
            sync_percentage = (len(emby_episodes) / len(ta_videos)) * 100
            print(f"🔄 Sync Coverage: {sync_percentage:.1f}%")
        
        # Show recent videos
        print("\n📅 Recent Videos (Last 5):")
        sorted_videos = sorted(ta_videos, 
                             key=lambda x: x.get('published', ''), 
                             reverse=True)[:5]
        
        for video in sorted_videos:
            title = video.get('title', 'Unknown')[:50] + '...' if len(video.get('title', '')) > 50 else video.get('title', 'Unknown')
            channel = video.get('channel', {}).get('channel_name', 'Unknown')
            published = video.get('published', 'Unknown')[:10]  # Just date part
            print(f"   • {title} ({channel}) - {published}")
        
        return True
        
    except Exception as e:
        print(f"❌ Error getting stats: {e}")
        return False


def clean_metadata():
    """Clean up orphaned metadata in Emby"""
    print("🧹 Cleaning Orphaned Metadata")
    print("=" * 50)
    
    try:
        config = Config()
        sync = TubeArchivistEmbySync(config)
        
        if not sync.verify_apis():
            print("❌ API verification failed")
            return False
        
        # Get all videos from TubeArchivist
        ta_videos = sync._get_all_ta_videos()
        ta_video_ids = {video.get('youtube_id') for video in ta_videos}
        
        # Get all items from Emby
        emby_items = sync.emby_api.get_library_items(sync.youtube_library_id)
        
        orphaned_items = []
        for item in emby_items.get('Items', []):
            if item.get('Type') == 'Episode':
                # Check if this item has a corresponding video in TubeArchivist
                provider_ids = item.get('ProviderIds', {})
                youtube_id = provider_ids.get('Youtube')
                
                if youtube_id and youtube_id not in ta_video_ids:
                    orphaned_items.append(item)
                elif not youtube_id:
                    # Try to extract from path
                    path = item.get('Path', '')
                    # Look for YouTube ID pattern in path
                    import re
                    youtube_pattern = r'[a-zA-Z0-9_-]{11}'
                    matches = re.findall(youtube_pattern, path)
                    
                    found_match = False
                    for match in matches:
                        if match in ta_video_ids:
                            found_match = True
                            break
                    
                    if not found_match:
                        orphaned_items.append(item)
        
        if orphaned_items:
            print(f"🗑️  Found {len(orphaned_items)} orphaned items")
            
            if input("Delete orphaned items? (y/N): ").lower() == 'y':
                deleted_count = 0
                for item in orphaned_items:
                    try:
                        # Note: This would require delete permission
                        # For now, just list them
                        print(f"   Would delete: {item.get('Name', 'Unknown')}")
                        deleted_count += 1
                    except Exception as e:
                        logger.error(f"Failed to delete item {item.get('Id')}: {e}")
                
                print(f"✅ Listed {deleted_count} items for deletion")
                print("   Note: Actual deletion requires additional API permissions")
            else:
                print("   Deletion cancelled")
        else:
            print("✅ No orphaned items found")
        
        return True
        
    except Exception as e:
        print(f"❌ Error during cleanup: {e}")
        return False


def test_notification():
    """Test notification endpoint"""
    print("🔔 Testing Notification Endpoint")
    print("=" * 50)
    
    try:
        config = Config()
        port = config.get('listen_port')
        
        import requests
        
        # Test GET (health check)
        try:
            response = requests.get(f"http://localhost:{port}", timeout=5)
            if response.status_code == 200:
                print("✅ GET endpoint working")
            else:
                print(f"❌ GET endpoint returned {response.status_code}")
        except Exception as e:
            print(f"❌ GET endpoint error: {e}")
            return False
        
        # Test POST (notification)
        try:
            response = requests.post(
                f"http://localhost:{port}",
                json={"message": "test notification"},
                timeout=30
            )
            if response.status_code == 200:
                print("✅ POST endpoint working")
            else:
                print(f"❌ POST endpoint returned {response.status_code}")
        except Exception as e:
            print(f"❌ POST endpoint error: {e}")
            return False
        
        return True
        
    except Exception as e:
        print(f"❌ Error testing notification: {e}")
        return False


def main():
    """Main utility function"""
    parser = argparse.ArgumentParser(description="TubeArchivist-Emby Utilities")
    parser.add_argument('command', choices=['health', 'stats', 'clean', 'test-notification'],
                       help='Utility command to run')
    
    args = parser.parse_args()
    
    if args.command == 'health':
        success = health_check()
    elif args.command == 'stats':
        success = sync_stats()
    elif args.command == 'clean':
        success = clean_metadata()
    elif args.command == 'test-notification':
        success = test_notification()
    else:
        print(f"Unknown command: {args.command}")
        success = False
    
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
