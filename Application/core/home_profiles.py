"""Persistence helpers for home-screen profiles and dashboard layouts."""


def application_names(config):
    return [name for name, value in config.items() if not name.startswith("_") and isinstance(value, dict)]


def normalize_home_profiles(config, names=None):
    """Keep saved profile layouts valid as applications are added or removed."""
    names = application_names(config) if names is None else list(names)
    saved = config.get("_home_profiles")
    if not isinstance(saved, dict):
        saved = {}

    profiles = {}
    for profile_name, profile in saved.items():
        if not isinstance(profile_name, str) or not profile_name.strip() or not isinstance(profile, dict):
            continue
        order = profile.get("order", [])
        hidden = profile.get("hidden", [])
        if not isinstance(order, list):
            order = []
        if not isinstance(hidden, list):
            hidden = []
        ordered_names = [name for name in order if name in names]
        ordered_names.extend(name for name in names if name not in ordered_names)
        profiles[profile_name] = {
            "order": ordered_names,
            "hidden": [name for name in hidden if name in names],
        }

    if not profiles:
        profiles["Default"] = {"order": names, "hidden": []}
    elif "Default" not in profiles:
        profiles["Default"] = {"order": names, "hidden": []}

    active = config.get("_active_home_profile")
    if active not in profiles:
        active = "Default"
    config["_home_profiles"] = profiles
    config["_active_home_profile"] = active
    return profiles


def ordered_home_applications(config, names=None):
    """Return visible application names in the active profile's order."""
    profiles = normalize_home_profiles(config, names)
    profile = profiles[config["_active_home_profile"]]
    hidden = set(profile["hidden"])
    return [name for name in profile["order"] if name not in hidden]
