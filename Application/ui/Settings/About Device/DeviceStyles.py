from PyQt6.QtWidgets import QFormLayout, QLabel, QVBoxLayout, QWidget


PAGE_STYLE = """
    QWidget#aboutDevicePage {
        background-color: rgba(22, 22, 22, 200);
        border: 1px solid rgba(255, 255, 255, 30);
        border-radius: 14px;
    }
    QWidget#aboutDevicePage QLabel {
        color: #BBBBBB;
        font-size: 15px;
    }
    QWidget#aboutDevicePage QLabel#aboutDeviceTitle {
        color: #FFFFFF;
        font-size: 24px;
        font-weight: bold;
    }
"""


def style_device_page(widget: QWidget, layout: QVBoxLayout):
    widget.setObjectName("aboutDevicePage")
    widget.setStyleSheet(PAGE_STYLE)
    layout.setContentsMargins(30, 30, 30, 30)
    layout.setSpacing(20)


def create_device_page_title(text: str):
    title = QLabel(text)
    title.setObjectName("aboutDeviceTitle")
    return title


def style_device_form(form: QFormLayout):
    form.setContentsMargins(0, 0, 0, 0)
    form.setVerticalSpacing(15)
    form.setHorizontalSpacing(20)
