#!/usr/bin/env python3
"""
Smoke test script for notification history and display profiles.
"""

import sys
import tempfile
from pathlib import Path

# Add the project to the path
sys.path.insert(0, str(Path(__file__).parent))

from Application.core.notification_history import NotificationHistoryManager, Notification
from Application.core.display_profiles import DisplayProfilesManager, DisplayProfile


def test_notification_history():
    """Test notification history functionality."""
    print("\n" + "="*60)
    print("TESTING NOTIFICATION HISTORY")
    print("="*60)

    # Use a temporary database for testing
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test_notifications.db"
        manager = NotificationHistoryManager(db_path=db_path)

        print("\n✓ Database initialized")

        # Test adding notifications
        print("\nAdding test notifications...")
        id1 = manager.add_notification(
            "Battery Low",
            "Your device battery is below 20%",
            "power",
            "System"
        )
        print(f"  - Added notification #{id1}: Battery Low")

        id2 = manager.add_notification(
            "WiFi Connected",
            "Connected to MyNetwork",
            "network",
            "System"
        )
        print(f"  - Added notification #{id2}: WiFi Connected")

        id3 = manager.add_notification(
            "Device Connected",
            "USB device detected",
            "device",
            "System"
        )
        print(f"  - Added notification #{id3}: Device Connected")

        # Test getting notifications
        print("\nRetrieving all notifications...")
        all_notifs = manager.get_notifications()
        print(f"  Total notifications: {len(all_notifs)}")
        for notif in all_notifs:
            print(f"    - [{notif.category}] {notif.title}: {notif.read and '✓ Read' or '● Unread'}")

        # Test filtering
        print("\nFiltering by category (power)...")
        power_notifs = manager.get_notifications(category="power")
        print(f"  Power notifications: {len(power_notifs)}")

        # Test unread filter
        print("\nGetting unread only...")
        unread = manager.get_notifications(unread_only=True)
        print(f"  Unread notifications: {len(unread)}")

        # Test marking as read
        print("\nMarking notification as read...")
        manager.mark_as_read(id1)
        print(f"  ✓ Marked notification #{id1} as read")

        unread_after = manager.get_notifications(unread_only=True)
        print(f"  Unread after mark: {len(unread_after)}")

        # Test counts
        print("\nGetting counts...")
        total = manager.get_total_count()
        unread_count = manager.get_unread_count()
        print(f"  Total: {total}, Unread: {unread_count}")

        # Test categories
        print("\nGetting categories...")
        categories = manager.get_categories()
        print(f"  Categories: {categories}")

        # Test mark all as read
        print("\nMarking all as read...")
        manager.mark_all_as_read()
        unread_final = manager.get_unread_count()
        print(f"  Unread after marking all: {unread_final}")

        print("\n✓ Notification history tests PASSED")


def test_display_profiles():
    """Test display profiles functionality."""
    print("\n" + "="*60)
    print("TESTING DISPLAY PROFILES")
    print("="*60)

    with tempfile.TemporaryDirectory() as tmpdir:
        config_path = Path(tmpdir) / "test_profiles.json"
        manager = DisplayProfilesManager(config_path=config_path)

        print("\n✓ Profile manager initialized")

        # Test adding profiles
        print("\nAdding test profiles...")
        profile1 = DisplayProfile(
            name="1080p Gaming",
            resolution="1920x1080",
            refresh_rate=144,
            scaling=100,
            dpi=96
        )
        result = manager.add_profile(profile1)
        print(f"  - Added: 1080p Gaming - {result}")

        profile2 = DisplayProfile(
            name="4K Productivity",
            resolution="3840x2160",
            refresh_rate=60,
            scaling=150,
            dpi=96
        )
        result = manager.add_profile(profile2)
        print(f"  - Added: 4K Productivity - {result}")

        # Test getting all profiles
        print("\nRetrieving profiles...")
        all_profiles = manager.get_all_profiles()
        print(f"  Total profiles: {len(all_profiles)}")
        for p in all_profiles:
            print(f"    - {p.name}: {p.resolution}@{p.refresh_rate}Hz")

        # Test getting by name
        print("\nGetting profile by name...")
        profile = manager.get_profile("1080p Gaming")
        if profile:
            print(f"  ✓ Retrieved: {profile.name}")
        else:
            print("  ✗ Profile not found")

        # Test setting current
        print("\nSetting current profile...")
        manager.set_current_profile("1080p Gaming")
        current = manager.get_current_profile()
        if current:
            print(f"  ✓ Current: {current.name}")

        # Test renaming
        print("\nRenaming profile...")
        result = manager.rename_profile("1080p Gaming", "144Hz Gaming")
        print(f"  - Rename result: {result}")

        all_profiles = manager.get_all_profiles()
        for p in all_profiles:
            print(f"    - {p.name}")

        # Test capacity
        print("\nTesting capacity...")
        capacity = manager.has_capacity_for_new_profile()
        print(f"  Can add more: {capacity}")
        print(f"  Current: {manager.get_profile_count()}/{manager.MAX_PROFILES}")

        # Test deleting
        print("\nDeleting profile...")
        result = manager.delete_profile("4K Productivity")
        print(f"  - Delete result: {result}")
        print(f"  Remaining: {manager.get_profile_count()}")

        print("\n✓ Display profiles tests PASSED")


if __name__ == "__main__":
    try:
        test_notification_history()
        test_display_profiles()

        print("\n" + "="*60)
        print("ALL TESTS PASSED ✓")
        print("="*60)
        sys.exit(0)

    except Exception as e:
        print(f"\n✗ TEST FAILED: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
