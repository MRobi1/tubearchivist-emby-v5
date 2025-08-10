# monitoring.py
#!/usr/bin/env python3
"""
Monitoring and metrics for TubeArchivist-Emby Integration
"""

import time
import json
import logging
from datetime import datetime, timedelta
from pathlib import Path
from main import Config, TubeArchivistEmbySync

logger = logging.getLogger(__name__)


class SyncMonitor:
    """Monitor sync operations and collect metrics"""
    
    def __init__(self, config: Config):
        self.config = config
        self.metrics_file = Path("sync_metrics.json")
        self.sync = TubeArchivistEmbySync(config)
    
    def load_metrics(self) -> dict:
        """Load existing metrics"""
        if self.metrics_file.exists():
            try:
                with open(self.metrics_file, 'r') as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"Failed to load metrics: {e}")
        
        return {
            'sync_history': [],
            'error_history': [],
            'stats': {
                'total_syncs': 0,
                'successful_syncs': 0,
                'failed_syncs': 0,
                'last_sync': None,
                'avg_sync_time': 0
            }
        }
    
    def save_metrics(self, metrics: dict):
        """Save metrics to file"""
        try:
            with open(self.metrics_file, 'w') as f:
                json.dump(metrics, f, indent=2, default=str)
        except Exception as e:
            logger.error(f"Failed to save metrics: {e}")
    
    def record_sync(self, success: bool, duration: float, error: str = None):
        """Record sync operation"""
        metrics = self.load_metrics()
        
        sync_record = {
            'timestamp': datetime.now(),
            'success': success,
            'duration': duration,
            'error': error
        }
        
        metrics['sync_history'].append(sync_record)
        
        # Keep only last 100 records
        metrics['sync_history'] = metrics['sync_history'][-100:]
        
        # Update stats
        metrics['stats']['total_syncs'] += 1
        if success:
            metrics['stats']['successful_syncs'] += 1
        else:
            metrics['stats']['failed_syncs'] += 1
            if error:
                metrics['error_history'].append({
                    'timestamp': datetime.now(),
                    'error': error
                })
                metrics['error_history'] = metrics['error_history'][-50:]
        
        metrics['stats']['last_sync'] = datetime.now()
        
        # Calculate average sync time
        recent_syncs = [s for s in metrics['sync_history'] 
                       if s['success']][-10:]  # Last 10 successful syncs
        if recent_syncs:
            avg_time = sum(s['duration'] for s in recent_syncs) / len(recent_syncs)
            metrics['stats']['avg_sync_time'] = avg_time
        
        self.save_metrics(metrics)
    
    def get_health_status(self) -> dict:
        """Get current health status"""
        metrics = self.load_metrics()
        
        # Check recent sync success rate
        recent_syncs = [s for s in metrics['sync_history'][-10:]]
        recent_success_rate = 0
        if recent_syncs:
            successful = sum(1 for s in recent_syncs if s['success'])
            recent_success_rate = (successful / len(recent_syncs)) * 100
        
        # Check if APIs are accessible
        api_status = self.sync.verify_apis()
        
        # Check last sync time
        last_sync = metrics['stats']['last_sync']
        time_since_sync = None
        if last_sync:
            if isinstance(last_sync, str):
                last_sync = datetime.fromisoformat(last_sync)
            time_since_sync = (datetime.now() - last_sync).total_seconds() / 3600
        
        status = {
            'healthy': True,
            'api_accessible': api_status,
            'recent_success_rate': recent_success_rate,
            'time_since_last_sync_hours': time_since_sync,
            'total_syncs': metrics['stats']['total_syncs'],
            'avg_sync_time': metrics['stats']['avg_sync_time']
        }
        
        # Determine overall health
        if not api_status:
            status['healthy'] = False
            status['reason'] = 'APIs not accessible'
        elif recent_success_rate < 50:
            status['healthy'] = False
            status['reason'] = 'Low success rate'
        elif time_since_sync and time_since_sync > 24:
            status['healthy'] = False
            status['reason'] = 'No sync in 24 hours'
        
        return status
    
    def monitored_sync(self) -> bool:
        """Perform sync with monitoring"""
        start_time = time.time()
        
        try:
            logger.info("Starting monitored sync...")
            success = self.sync.sync_metadata()
            duration = time.time() - start_time
            
            self.record_sync(success, duration)
            
            if success:
                logger.info(f"Sync completed successfully in {duration:.2f}s")
            else:
                logger.error("Sync failed")
            
            return success
            
        except Exception as e:
            duration = time.time() - start_time
            error_msg = str(e)
            
            self.record_sync(False, duration, error_msg)
            logger.error(f"Sync failed with exception: {e}")
            
            return False


def main():
    """Run monitoring"""
    try:
        config = Config()
        monitor = SyncMonitor(config)
        
        # Get health status
        health = monitor.get_health_status()
        print("Health Status:", json.dumps(health, indent=2, default=str))
        
        # Run monitored sync
        if "--sync" in sys.argv:
            monitor.monitored_sync()
        
    except Exception as e:
        logger.error(f"Monitoring error: {e}")


if __name__ == "__main__":
    main()
