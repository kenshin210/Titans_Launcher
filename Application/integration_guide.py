"""
Integration Guide for Phase 0, 1, and 2 Components into Titans Launcher.

This module provides helper functions and guidance for integrating the new
session management, app management, and system components into the existing
Titans Launcher application.
"""

import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class LauncherIntegration:
    """Helper class for integrating Phase 0-2 components into MainApp."""
    
    @staticmethod
    def setup_phase0_integration(main_app) -> bool:
        """Set up Phase 0 integration (session & process management).
        
        Call this in MainApp.__init__() after initUI().
        
        Args:
            main_app: Reference to MainApp instance
        
        Returns:
            bool: Success status
        
        Example:
            >>> app = MainApp()
            >>> LauncherIntegration.setup_phase0_integration(app)
        """
        try:
            from Application.core.session_manager import SessionManager
            from Application.core.process_monitor import ProcessMonitor
            from Application.core.recovery_manager import RecoveryManager
            
            # Initialize managers
            main_app.session_mgr = SessionManager()
            main_app.process_monitor = ProcessMonitor()
            main_app.recovery_mgr = RecoveryManager()
            
            # Create systemd units and desktop session file
            logger.info("Setting up Phase 0 infrastructure...")
            session_ok, session_msg = main_app.session_mgr.create_systemd_units()
            desktop_ok, desktop_msg = main_app.session_mgr.create_desktop_session_file()
            
            if session_ok:
                logger.info(session_msg)
            else:
                logger.warning(f"Systemd setup: {session_msg}")
            
            if desktop_ok:
                logger.info(desktop_msg)
            else:
                logger.warning(f"Desktop file setup: {desktop_msg}")
            
            # Start heartbeat update timer
            from PyQt6.QtCore import QTimer
            heartbeat_timer = QTimer()
            heartbeat_timer.timeout.connect(
                lambda: main_app.session_mgr.update_heartbeat()
            )
            heartbeat_timer.start(1000)  # Every 1 second
            main_app.heartbeat_timer = heartbeat_timer
            
            logger.info("Phase 0 integration complete")
            return True
        
        except Exception as e:
            logger.error(f"Phase 0 integration failed: {e}")
            return False
    
    @staticmethod
    def setup_phase1_integration(main_app) -> bool:
        """Set up Phase 1 integration (multi-app management).
        
        Call this in MainApp.initUI() to add app switcher widget.
        
        Args:
            main_app: Reference to MainApp instance
        
        Returns:
            bool: Success status
        
        Example:
            >>> app = MainApp()
            >>> LauncherIntegration.setup_phase1_integration(app)
        """
        try:
            from Application.core.application_manager import ApplicationManager
            from Application.ui.widgets.app_switcher import AppSwitcherWidget
            
            # Initialize application manager
            main_app.app_manager = ApplicationManager()
            logger.info("ApplicationManager initialized")
            
            # Create app switcher widget (add to UI at appropriate location)
            main_app.app_switcher = AppSwitcherWidget()
            
            # Connect signals
            main_app.app_switcher.app_selected.connect(
                lambda aid: main_app.on_app_selected(aid)
            )
            main_app.app_switcher.app_terminated.connect(
                lambda aid: main_app.on_app_terminated(aid)
            )
            
            # Start app monitoring timer
            from PyQt6.QtCore import QTimer
            app_monitor_timer = QTimer()
            app_monitor_timer.timeout.connect(
                lambda: main_app.app_switcher.update_app_display()
            )
            app_monitor_timer.start(2000)  # Every 2 seconds
            main_app.app_monitor_timer = app_monitor_timer
            
            logger.info("Phase 1 integration complete")
            return True
        
        except Exception as e:
            logger.error(f"Phase 1 integration failed: {e}")
            return False
    
    @staticmethod
    def setup_phase2_integration(main_app) -> bool:
        """Set up Phase 2 integration (system management).
        
        Call this to enable system management features.
        
        Args:
            main_app: Reference to MainApp instance
        
        Returns:
            bool: Success status
        
        Example:
            >>> app = MainApp()
            >>> LauncherIntegration.setup_phase2_integration(app)
        """
        try:
            from Application.core.display_settings import DisplaySettingsManager
            from Application.core.audio_manager import AudioManager
            from Application.core.network_manager import NetworkManager
            from Application.core.storage_manager import StorageManager
            from Application.core.notification_system import NotificationManager
            
            # Initialize all system managers
            main_app.display_mgr = DisplaySettingsManager()
            main_app.audio_mgr = AudioManager()
            main_app.network_mgr = NetworkManager()
            main_app.storage_mgr = StorageManager()
            main_app.notification_mgr = NotificationManager()
            
            # Detect connected displays
            success, displays = main_app.display_mgr.detect_displays()
            if success:
                logger.info(f"Detected {len(displays)} displays")
            else:
                logger.warning("Failed to detect displays")
            
            # Detect audio devices
            success, msg = main_app.audio_mgr.detect_devices()
            if success:
                logger.info(f"Audio: {len(main_app.audio_mgr.get_output_devices())} output, {len(main_app.audio_mgr.get_input_devices())} input devices")
            else:
                logger.warning(f"Audio detection: {msg}")
            
            # Check network connectivity
            is_connected, status = main_app.network_mgr.get_connectivity_status()
            logger.info(f"Network status: {status}")
            
            # Check storage
            storage_status = main_app.storage_mgr.get_storage_status()
            logger.info(f"Storage: {storage_status['disk_count']} disks, {storage_status['mount_points']} mount points")
            
            # Store references for later use
            main_app.system_managers = {
                "display": main_app.display_mgr,
                "audio": main_app.audio_mgr,
                "network": main_app.network_mgr,
                "storage": main_app.storage_mgr,
                "notifications": main_app.notification_mgr,
            }
            
            logger.info("Phase 2 integration complete (all 5 system managers)")
            return True
        
        except Exception as e:
            logger.error(f"Phase 2 integration failed: {e}")
            return False


class IntegrationExamples:
    """Example code snippets for integrating components."""
    
    PHASE0_LAUNCHER_PATCH = """
# In Application/launcher.py - MainApp.__init__()

# After calling self.initUI():
from Application.integration_guide import LauncherIntegration
if not LauncherIntegration.setup_phase0_integration(self):
    log_warning("Phase 0 integration incomplete - running without session management")
"""
    
    PHASE1_LAUNCHER_PATCH = """
# In Application/launcher.py - MainApp.initUI()

# After creating main UI widgets:
from Application.integration_guide import LauncherIntegration
if not LauncherIntegration.setup_phase1_integration(self):
    log_warning("Phase 1 integration incomplete - app management unavailable")

# Add app switcher to main layout:
# self.main_layout.addWidget(self.app_switcher)
# Or add to a tabbed interface:
# self.tabs.addTab(self.app_switcher, "Apps")
"""
    
    PHASE2_LAUNCHER_PATCH = """
# In Application/launcher.py - MainApp.initUI()

# Add system management to settings:
from Application.integration_guide import LauncherIntegration
if not LauncherIntegration.setup_phase2_integration(self):
    log_warning("Phase 2 integration incomplete - system management unavailable")

# Access system managers:
# self.display_mgr   - Display/monitor management
# self.audio_mgr     - Audio device and volume control
# self.network_mgr   - WiFi/Ethernet connectivity
# self.storage_mgr   - Disk usage, mount points
# self.notification_mgr - Desktop notifications
"""
    
    CUSTOM_APP_LAUNCH = """
# Example: Launching an application from Titans UI

def launch_firefox():
    success, msg, pid = self.app_manager.launch_app(
        app_id="firefox_main",
        name="Firefox",
        command="/usr/bin/firefox",
        working_dir=str(Path.home()),
    )
    if success:
        log_info(f"Firefox launched with PID {pid}")
        self.app_switcher.update_app_display()
    else:
        show_error("Failed to launch Firefox", msg)
"""
    
    DISPLAY_SETTINGS_EXAMPLE = """
# Example: Changing display resolution

def change_display_resolution():
    displays = self.display_mgr.detect_displays()
    for display in displays:
        if display.connected:
            success, msg = self.display_mgr.set_resolution(
                display.name, 1920, 1080, 60
            )
            if success:
                log_info(msg)
            else:
                log_error(msg)
"""
    
    APP_CRASH_HANDLING = """
# Example: Handling app crashes in main loop

def check_app_health():
    from Application.ui.Settings.Logger import log_warning
    
    for app_id, app_info in self.app_manager.get_all_apps().items():
        is_healthy, status = self.app_manager.check_app_health(app_id)
        if not is_healthy and app_info.state == "running":
            self.app_manager.record_app_crash(app_id, status)
            log_warning(f"App {app_info.name} crashed: {status}")
            # Could auto-restart or show recovery UI
"""


def integrate_all_phases(main_app) -> None:
    """Integrate all phases in one call.
    
    Args:
        main_app: Reference to MainApp instance
    """
    from Application.integration_guide import LauncherIntegration
    
    logger.info("Starting Phase 0-2 integration...")
    
    phase0_ok = LauncherIntegration.setup_phase0_integration(main_app)
    phase1_ok = LauncherIntegration.setup_phase1_integration(main_app)
    phase2_ok = LauncherIntegration.setup_phase2_integration(main_app)
    
    if phase0_ok:
        logger.info("✓ Phase 0 integration complete")
    else:
        logger.warning("✗ Phase 0 integration incomplete")
    
    if phase1_ok:
        logger.info("✓ Phase 1 integration complete")
    else:
        logger.warning("✗ Phase 1 integration incomplete")
    
    if phase2_ok:
        logger.info("✓ Phase 2 integration complete")
    else:
        logger.warning("✗ Phase 2 integration incomplete")
    
    if all([phase0_ok, phase1_ok, phase2_ok]):
        logger.info("✓ All phases integrated successfully")
    else:
        logger.warning("⚠ Some phases incomplete - check logs for details")


# Quick Integration Checklist
INTEGRATION_CHECKLIST = """
TITANS LAUNCHER - PHASE 0-2 INTEGRATION CHECKLIST
==================================================

PHASE 0 - Session & Process Management
--------------------------------------
[ ] Copy session_manager.py to Application/core/
[ ] Copy process_monitor.py to Application/core/
[ ] Copy recovery_manager.py to Application/core/
[ ] Call LauncherIntegration.setup_phase0_integration() in MainApp.__init__()
[ ] Test session startup/shutdown
[ ] Test process monitoring
[ ] Test crash detection
[ ] Test recovery activation

PHASE 1 - Multi-App Management
-------------------------------
[ ] Copy application_manager.py to Application/core/
[ ] Copy app_switcher.py to Application/ui/widgets/
[ ] Call LauncherIntegration.setup_phase1_integration() in MainApp.initUI()
[ ] Add AppSwitcherWidget to main UI layout
[ ] Test app launching from UI
[ ] Test app termination
[ ] Test app switching
[ ] Test app crash isolation
[ ] Test concurrent app limits

PHASE 2 - System Management
---------------------------
[ ] Copy display_settings.py to Application/core/
[ ] Copy audio_manager.py to Application/core/
[ ] Copy network_manager.py to Application/core/
[ ] Copy storage_manager.py to Application/core/
[ ] Copy notification_system.py to Application/core/
[ ] Call LauncherIntegration.setup_phase2_integration() in MainApp.initUI()
[ ] Create Display Settings UI panel
[ ] Create Audio Settings UI panel
[ ] Create Network Settings UI panel
[ ] Create Storage Settings UI panel
[ ] Test display detection and changes
[ ] Test audio management (device switching, volume control)
[ ] Test network management (scan, connect, disconnect)
[ ] Test storage management (mount, unmount, disk usage)
[ ] Test notifications (test delivery, categories, urgency)

TESTING
-------
[ ] Run existing test suite - no regressions
[ ] Test on multiple distros (Arch, Fedora, Ubuntu)
[ ] Test with multiple display configurations
[ ] Test with 5+ concurrent applications
[ ] Performance profiling (CPU, memory, startup time)
[ ] Recovery mode testing
[ ] Edge case testing (rapid crashes, service unavailability)

DOCUMENTATION
--------------
[ ] Update main documents/README.md
[ ] Create Phase 0-2 user guide
[ ] Document all new settings
[ ] Create troubleshooting guide
[ ] Document systemd integration
[ ] Document D-Bus integration

DEPLOYMENT
----------
[ ] Update installation script
[ ] Update package dependencies
[ ] Test on clean system
[ ] Create migration guide (if needed)
[ ] Tag release version
[ ] Create release notes
"""


if __name__ == "__main__":
    print(INTEGRATION_CHECKLIST)
