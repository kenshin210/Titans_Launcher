from pathlib import Path
from string import Template


STYLES_DIR = Path(__file__).resolve().parent.parent / "Assets" / "Styles"
DEFAULT_STYLE_VALUES = {
    "theme_color": "#DC143C",
    "border_radius": "28px",
    "bar_border_radius": "12px",
    "background_color": "#141414",
}


def load_stylesheet(name="launcher.qss", **values):
    template = Template((STYLES_DIR / name).read_text(encoding="utf-8"))
    style_values = {**DEFAULT_STYLE_VALUES, **values}
    return template.substitute(style_values)
