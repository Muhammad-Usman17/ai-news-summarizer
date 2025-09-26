#!/usr/bin/env python3
"""
Celery Beat Watchdog
====================

A wrapper script that monitors for restart signals and automatically restarts
the Celery Beat scheduler when configuration changes are detected.

This solves the problem where Celery Beat needs to be restarted to pick up
new schedule configurations from the database.
"""

import os
import sys
import time
import signal
import subprocess
import logging
from pathlib import Path

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Configuration
BEAT_COMMAND = [
    sys.executable, '-m', 'celery', '-A', 'app.celery_app', 'beat', 
    '--loglevel=info',
    '--scheduler=celery.beat:PersistentScheduler'
]

RESTART_MARKER = 'celerybeat-restart.marker'
CHECK_INTERVAL = 5  # seconds
MAX_RESTART_ATTEMPTS = 3

class CeleryBeatWatchdog:
    """Watchdog that manages Celery Beat lifecycle and handles restart requests."""
    
    def __init__(self):
        self.beat_process = None
        self.restart_attempts = 0
        self.should_exit = False
        
        # Set up signal handlers
        signal.signal(signal.SIGTERM, self._signal_handler)
        signal.signal(signal.SIGINT, self._signal_handler)
    
    def _signal_handler(self, signum, frame):
        """Handle shutdown signals."""
        logger.info(f"Received signal {signum}, shutting down...")
        self.should_exit = True
        self._stop_beat()
    
    def _start_beat(self):
        """Start Celery Beat process."""
        try:
            logger.info("Starting Celery Beat process...")
            self.beat_process = subprocess.Popen(
                BEAT_COMMAND,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                universal_newlines=True
            )
            logger.info(f"Celery Beat started with PID: {self.beat_process.pid}")
            self.restart_attempts = 0
            return True
        except Exception as e:
            logger.error(f"Failed to start Celery Beat: {e}")
            return False
    
    def _stop_beat(self):
        """Stop Celery Beat process."""
        if self.beat_process:
            try:
                logger.info("Stopping Celery Beat process...")
                self.beat_process.terminate()
                
                # Wait for graceful shutdown
                try:
                    self.beat_process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    logger.warning("Celery Beat didn't stop gracefully, killing...")
                    self.beat_process.kill()
                    self.beat_process.wait()
                
                logger.info("Celery Beat stopped")
                self.beat_process = None
                
            except Exception as e:
                logger.error(f"Error stopping Celery Beat: {e}")
    
    def _check_restart_marker(self):
        """Check if restart has been requested."""
        if os.path.exists(RESTART_MARKER):
            logger.info("Restart marker found, initiating restart...")
            try:
                os.remove(RESTART_MARKER)
            except Exception as e:
                logger.warning(f"Could not remove restart marker: {e}")
            return True
        return False
    
    def _is_beat_healthy(self):
        """Check if Celery Beat process is still running."""
        if not self.beat_process:
            return False
        
        # Check if process is still alive
        poll_result = self.beat_process.poll()
        return poll_result is None
    
    def _restart_beat(self):
        """Restart Celery Beat process."""
        self.restart_attempts += 1
        
        if self.restart_attempts > MAX_RESTART_ATTEMPTS:
            logger.error(f"Max restart attempts ({MAX_RESTART_ATTEMPTS}) reached, exiting...")
            self.should_exit = True
            return False
        
        logger.info(f"Restarting Celery Beat (attempt {self.restart_attempts}/{MAX_RESTART_ATTEMPTS})...")
        
        self._stop_beat()
        time.sleep(2)  # Brief pause
        
        return self._start_beat()
    
    def run(self):
        """Main watchdog loop."""
        logger.info("Starting Celery Beat Watchdog...")
        
        # Start initial Beat process
        if not self._start_beat():
            logger.error("Failed to start initial Celery Beat process")
            return 1
        
        # Main monitoring loop
        while not self.should_exit:
            try:
                # Check if restart was requested
                if self._check_restart_marker():
                    if not self._restart_beat():
                        break
                
                # Check if process is still healthy
                elif not self._is_beat_healthy():
                    logger.warning("Celery Beat process died unexpectedly")
                    if not self._restart_beat():
                        break
                
                # Log output from beat process
                if self.beat_process and self.beat_process.stdout:
                    try:
                        line = self.beat_process.stdout.readline()
                        if line:
                            print(f"[BEAT] {line.strip()}")
                    except Exception:
                        pass  # Non-blocking read might fail
                
                time.sleep(CHECK_INTERVAL)
                
            except Exception as e:
                logger.error(f"Error in watchdog loop: {e}")
                time.sleep(CHECK_INTERVAL)
        
        # Cleanup
        self._stop_beat()
        logger.info("Celery Beat Watchdog stopped")
        return 0


def main():
    """Main entry point."""
    # Change to project directory
    project_dir = Path(__file__).parent.parent
    os.chdir(project_dir)
    
    watchdog = CeleryBeatWatchdog()
    return watchdog.run()


if __name__ == "__main__":
    sys.exit(main())