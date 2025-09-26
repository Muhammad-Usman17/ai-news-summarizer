"""
Celery-based scheduler for news processing.
Replaces Temporal with Celery for periodic task execution.
"""

from celery.schedules import crontab
from datetime import datetime, timedelta
import asyncio
from typing import Optional

from app.config.settings import get_settings
from app.config.logging import get_logger, setup_logging
from app.services.redis_stream import redis_stream_service
from app.services.temporal_client import temporal_client
from app.services.config_manager import config_manager

setup_logging()
logger = get_logger(__name__)
settings = get_settings()

# Import the main Celery app instead of creating a new one
from app.celery_app import celery_app


def update_schedule(restart_beat: bool = False):
    """Update the Celery beat schedule based on persistent configuration."""
    try:
        # Get configuration from persistent storage
        schedule_config = config_manager.get_schedule_config()
        enabled = schedule_config['enabled']
        schedule_type = schedule_config['schedule_type']
        hours = schedule_config['hours']
        daily_time = schedule_config['daily_time']
        custom_cron = schedule_config['custom_cron']
        
        if enabled:
            schedule = None
            
            if schedule_type == "hourly":
                schedule = crontab(minute=0, hour=f"*/{hours}")
            elif schedule_type == "daily":
                schedule = crontab(minute=0, hour=daily_time)
            elif schedule_type == "custom":
                try:
                    # Parse custom cron: "minute hour day month day_of_week"
                    cron_parts = custom_cron.split()
                    if len(cron_parts) == 5:
                        schedule = crontab(
                            minute=cron_parts[0],
                            hour=cron_parts[1], 
                            day_of_month=cron_parts[2],
                            month_of_year=cron_parts[3],
                            day_of_week=cron_parts[4]
                        )
                    else:
                        logger.error(f"Invalid cron expression: {custom_cron}")
                        return
                except Exception as e:
                    logger.error(f"Error parsing custom cron: {e}")
                    return
            
            if schedule:
                celery_app.conf.beat_schedule['process-news-periodic'] = {
                    'task': 'app.services.scheduler.process_news_scheduled',
                    'schedule': schedule,
                }
                
                # Force schedule reload by removing the beat schedule file
                try:
                    import os
                    beat_schedule_file = celery_app.conf.beat_schedule_filename
                    if os.path.exists(beat_schedule_file):
                        os.remove(beat_schedule_file)
                        logger.info("Removed old beat schedule file to force reload")
                except Exception as file_error:
                    logger.warning(f"Could not remove beat schedule file: {file_error}")
                
                # Signal beat process restart if requested
                if restart_beat:
                    _signal_beat_restart()
                
                logger.info(f"Scheduled news processing: {schedule_type} "
                           f"(hours: {hours}, daily_time: {daily_time}, custom_cron: {custom_cron}) "
                           f"enabled: {enabled}")
            
        else:
            # Remove schedule if disabled
            celery_app.conf.beat_schedule.pop('process-news-periodic', None)
            try:
                import os
                beat_schedule_file = celery_app.conf.beat_schedule_filename
                if os.path.exists(beat_schedule_file):
                    os.remove(beat_schedule_file)
                    logger.info("Removed beat schedule file - scheduling disabled")
            except Exception as file_error:
                logger.warning(f"Could not remove beat schedule file: {file_error}")
            
            # Signal beat process restart if requested
            if restart_beat:
                _signal_beat_restart()
                
            logger.info("News processing schedule disabled")
            
    except Exception as e:
        logger.error(f"Error updating schedule: {e}")
        # Fallback to default settings
        if settings.news_processing_enabled:
            schedule = crontab(minute=0, hour=f"*/{settings.news_processing_schedule_hours}")
            celery_app.conf.beat_schedule['process-news-periodic'] = {
                'task': 'app.services.scheduler.process_news_scheduled',
                'schedule': schedule,
            }
            logger.info(f"Using fallback schedule: every {settings.news_processing_schedule_hours} hours")


def _signal_beat_restart():
    """Signal the Celery Beat process to restart using process signals."""
    try:
        import os
        import signal
        import psutil
        
        # Find Celery Beat processes - updated to look for app.celery_app
        beat_processes = []
        for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
            try:
                cmdline = ' '.join(proc.info['cmdline'] or [])
                # Look for celery beat with app.celery_app (our current setup)
                if ('celery' in cmdline and 'beat' in cmdline and 
                    ('app.celery_app' in cmdline or 'news_agents' in cmdline)):
                    beat_processes.append(proc.info['pid'])
                    logger.info(f"Found Celery Beat process: PID {proc.info['pid']}, CMD: {cmdline}")
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        
        if beat_processes:
            for pid in beat_processes:
                try:
                    # Send SIGTERM for graceful shutdown
                    os.kill(pid, signal.SIGTERM)
                    logger.info(f"Sent SIGTERM to Celery Beat process {pid}")
                except OSError as e:
                    logger.warning(f"Could not signal process {pid}: {e}")
        else:
            logger.warning("No Celery Beat processes found to restart")
            
        # Create a restart marker file that the beat process can check
        restart_marker = "celerybeat-restart.marker"
        with open(restart_marker, 'w') as f:
            f.write(f"restart_requested_at={datetime.utcnow().isoformat()}")
        logger.info("Created restart marker file for Celery Beat")
        
        # Also try to start a new beat process if none are running
        if not beat_processes:
            logger.info("No beat processes found, attempting to start one...")
            try:
                import subprocess
                subprocess.Popen([
                    'python3', '-m', 'celery', '-A', 'app.celery_app', 'beat', '--loglevel=info'
                ], cwd=os.getcwd())
                logger.info("Started new Celery Beat process")
            except Exception as start_error:
                logger.error(f"Failed to start new beat process: {start_error}")
        
    except Exception as e:
        logger.error(f"Error signaling beat restart: {e}")


def _ensure_beat_process_running():
    """Ensure that a Celery Beat process is running when scheduling is enabled."""
    try:
        import psutil
        import subprocess
        import os
        
        # Check if any beat process is running
        beat_running = False
        for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
            try:
                cmdline = ' '.join(proc.info['cmdline'] or [])
                if ('celery' in cmdline and 'beat' in cmdline and 
                    ('app.celery_app' in cmdline or 'news_agents' in cmdline)):
                    beat_running = True
                    logger.info(f"Found running Celery Beat process: PID {proc.info['pid']}")
                    break
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        
        if not beat_running:
            logger.info("No Celery Beat process found, starting new one...")
            try:
                # Start as background process
                subprocess.Popen([
                    'python3', '-m', 'celery', '-A', 'app.celery_app', 'beat', '--loglevel=info'
                ], cwd=os.getcwd(), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                logger.info("Started new Celery Beat process in background")
                return True
            except Exception as start_error:
                logger.error(f"Failed to start beat process: {start_error}")
                return False
        
        return True
        
    except Exception as e:
        logger.error(f"Error checking/starting beat process: {e}")
        return False


def _check_restart_marker():
    """Check if a restart has been requested and clean up marker file."""
    try:
        import os
        restart_marker = "celerybeat-restart.marker"
        if os.path.exists(restart_marker):
            os.remove(restart_marker)
            logger.info("Restart marker found and removed - forcing schedule reload")
            return True
    except Exception as e:
        logger.warning(f"Error checking restart marker: {e}")
    return False


@celery_app.task(bind=True, name="app.services.scheduler.process_news_scheduled")
def process_news_scheduled(self):
    """
    Scheduled task to process news using Temporal workflow.
    This replaces the Temporal workflow scheduling with Celery scheduling + Temporal orchestration.
    """
    try:
        logger.info("Starting scheduled news processing via Temporal")
        
        # Generate job ID
        job_id = f"scheduled-{datetime.utcnow().strftime('%Y%m%d-%H%M%S')}"
        
        # Send real-time update via Redis pub/sub
        asyncio.run(redis_stream_service.publish_update(
            job_id=job_id,
            status="started",
            message="Starting scheduled news processing via Temporal",
            data={
                "type": "news_processing_started",
                "timestamp": datetime.utcnow().isoformat()
            }
        ))
        
        # Start Temporal workflow
        async def start_workflow():
            await temporal_client.connect()
            workflow_id = await temporal_client.start_news_workflow(job_id)
            return workflow_id
        
        workflow_id = asyncio.run(start_workflow())
        logger.info("Temporal workflow started for scheduled task", job_id=job_id, workflow_id=workflow_id)
        
        # Send workflow started update
        asyncio.run(redis_stream_service.publish_update(
            job_id=job_id,
            status="workflow_started",
            message="Scheduled Temporal workflow initiated",
            data={
                'type': 'workflow_started',
                'workflow_id': workflow_id,
                'timestamp': datetime.utcnow().isoformat()
            }
        ))
        
        return {
            'status': 'started',
            'job_id': job_id,
            'workflow_id': workflow_id,
            'message': 'Scheduled Temporal workflow started successfully'
        }
        
        logger.info("Scheduled news processing completed", job_id=job_id)
        return result
        
    except Exception as e:
        logger.error("Scheduled news processing failed", error=str(e))
        
        # Send error update
        asyncio.run(redis_stream_service.publish_update(
            job_id=job_id,
            status="failed",
            message="Scheduled news processing failed",
            data={
                'type': 'job_failed',
                'error': str(e),
                'timestamp': datetime.utcnow().isoformat()
            }
        ))
        
        raise


@celery_app.task(bind=True, name="app.services.scheduler.process_news_manual")
def process_news_manual(self, job_id: str, target_date: Optional[str] = None):
    """
    Manual task to process news for a specific date using Temporal workflow.
    This can be triggered via API call.
    """
    try:
        logger.info("Starting manual news processing via Temporal", job_id=job_id, target_date=target_date)
        
        # Send real-time update via Redis pub/sub
        asyncio.run(redis_stream_service.publish_update(
            job_id=job_id,
            status="started",
            message="Manual news processing started via Temporal",
            data={
                'type': 'job_started',
                'target_date': target_date,
                'timestamp': datetime.utcnow().isoformat()
            }
        ))
        
        # Start Temporal workflow
        async def start_workflow():
            await temporal_client.connect()
            workflow_id = await temporal_client.start_news_workflow(job_id, target_date)
            return workflow_id
        
        workflow_id = asyncio.run(start_workflow())
        logger.info("Temporal workflow started", job_id=job_id, workflow_id=workflow_id)
        
        # Send workflow started update
        asyncio.run(redis_stream_service.publish_update(
            job_id=job_id,
            status="workflow_started",
            message="Temporal workflow initiated",
            data={
                'type': 'workflow_started',
                'workflow_id': workflow_id,
                'timestamp': datetime.utcnow().isoformat()
            }
        ))
        
        return {
            'status': 'started',
            'job_id': job_id,
            'workflow_id': workflow_id,
            'message': 'Temporal workflow started successfully'
        }
        
    except Exception as e:
        logger.error("Manual news processing failed", job_id=job_id, error=str(e))
        
        # Send error update
        asyncio.run(redis_stream_service.publish_update(
            job_id=job_id,
            status="failed",
            message="Manual news processing failed",
            data={
                'type': 'job_failed',
                'error': str(e),
                'timestamp': datetime.utcnow().isoformat()
            }
        ))
        
        raise


# Alias for backward compatibility
trigger_manual_news_processing = process_news_manual


def start_scheduled_processing(schedule_type: str = "hourly", hours: int = 1, daily_time: int = 9, custom_cron: str = "0 */1 * * *"):
    """
    Start or update scheduled processing with new configuration.
    
    Args:
        schedule_type: "hourly", "daily", or "custom"
        hours: Interval hours for hourly scheduling
        daily_time: Hour (0-23) for daily scheduling  
        custom_cron: Custom cron expression for custom scheduling
    """
    try:
        # Save configuration to persistent storage
        config = {
            'enabled': True,
            'schedule_type': schedule_type,
            'hours': hours,
            'daily_time': daily_time,
            'custom_cron': custom_cron
        }
        
        success = config_manager.save_schedule_config(config)
        if not success:
            raise Exception("Failed to save schedule configuration")
        
        # Update the schedule and restart beat
        update_schedule(restart_beat=True)
        
        # Ensure beat process is running
        _ensure_beat_process_running()
        
        logger.info("Scheduled processing started", 
                   schedule_type=schedule_type, 
                   hours=hours, 
                   daily_time=daily_time,
                   custom_cron=custom_cron)
        
        return {
            "status": "started",
            "schedule_type": schedule_type,
            "configuration": {
                "hours": hours,
                "daily_time": daily_time, 
                "custom_cron": custom_cron
            },
            "message": f"Scheduled processing started with {schedule_type} schedule. Celery Beat restart initiated."
        }
        
    except Exception as e:
        logger.error("Failed to start scheduled processing", error=str(e))
        raise


def stop_scheduled_processing():
    """Stop scheduled processing."""
    try:
        # Get current config and disable it
        schedule_config = config_manager.get_schedule_config()
        schedule_config['enabled'] = False
        
        success = config_manager.save_schedule_config(schedule_config)
        if not success:
            raise Exception("Failed to save schedule configuration")
        
        # Update schedule and restart beat
        update_schedule(restart_beat=True)
        
        logger.info("Scheduled processing stopped")
        
        return {
            "status": "stopped", 
            "message": "Scheduled processing has been disabled. Celery Beat restart initiated."
        }
        
    except Exception as e:
        logger.error("Failed to stop scheduled processing", error=str(e))
        raise


def get_schedule_status():
    """Get current schedule status and configuration."""
    try:
        schedule_config = config_manager.get_schedule_config()
        current_schedule = celery_app.conf.beat_schedule.get('process-news-periodic', {})
        
        # Calculate next run time (simplified - in production you'd use celery beat scheduler)
        next_run = "calculated_based_on_schedule"  # TODO: Implement proper next run calculation
        
        return {
            "enabled": schedule_config['enabled'],
            "schedule_type": schedule_config['schedule_type'],
            "hours": schedule_config['hours'],
            "daily_time": schedule_config['daily_time'],
            "custom_cron": schedule_config['custom_cron'],
            "next_run": next_run,
            "current_schedule": current_schedule
        }
        
    except Exception as e:
        logger.error(f"Failed to get schedule status: {e}")
        # Return default/fallback status
        return {
            "enabled": False,
            "schedule_type": "hourly",
            "hours": 1,
            "daily_time": 9,
            "custom_cron": "0 */1 * * *",
            "next_run": "unknown",
            "current_schedule": {}
        }


# Initialize schedule on module import
update_schedule()