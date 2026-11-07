# -*- coding: utf-8 -*-
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QFormLayout, QLineEdit, QPushButton, QMessageBox,
    QComboBox, QLabel
)
from PyQt6.QtCore import Qt

from Application.ui.Settings.Logger import log_info


class WeatherSettingsWidget(QWidget):
    """Weather location settings, shared by the Basic and Advanced menus."""

    def __init__(self, parent_launcher):
        super().__init__()
        self.launcher = parent_launcher
        theme_color = (
            self.launcher.get_theme_color()
            if hasattr(self.launcher, "get_theme_color") else "#DC143C"
        )

        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(0, 0, 0, 0)

        card = QWidget()
        card.setObjectName("settingsCard")
        card.setStyleSheet("""
            QWidget#settingsCard {
                background-color: rgba(22, 22, 22, 200);
                border: 1px solid rgba(255, 255, 255, 30);
                border-radius: 14px;
            }
        """)
        outer_layout.addWidget(card)

        layout = QVBoxLayout(card)
        layout.setContentsMargins(35, 35, 35, 35)
        layout.setSpacing(20)

        title = QLabel("Current Weather")
        title.setStyleSheet("color: #FFFFFF; font-size: 24px; font-weight: bold; border: none;")
        layout.addWidget(title)

        desc = QLabel("Choose the city and country shown above the date and time on the overview page.")
        desc.setStyleSheet("color: #888888; font-size: 14px; border: none;")
        layout.addWidget(desc)

        form = QFormLayout()
        form.setVerticalSpacing(15)
        input_style = (
            "background-color: rgba(40, 40, 40, 200); color: white; padding: 10px; "
            "border-radius: 6px; font-size: 14px; border: 1px solid rgba(255, 255, 255, 25);"
        )
        self.city_input = QLineEdit(self.launcher.config.get("_weather_city", ""))
        self.city_input.setPlaceholderText("e.g. Auckland")
        self.city_input.setStyleSheet(input_style)
        self.country_input = QLineEdit(self.launcher.config.get("_weather_country", ""))
        self.country_input.setPlaceholderText("e.g. New Zealand")
        self.country_input.setStyleSheet(input_style)
        self.unit_combo = QComboBox()
        self.unit_combo.addItems(["Celsius", "Fahrenheit"])
        self.unit_combo.setCurrentText(
            self.launcher.config.get("_weather_temperature_unit", "Celsius")
        )
        self.unit_combo.setStyleSheet(input_style)
        form.addRow(QLabel("City:"), self.city_input)
        form.addRow(QLabel("Country:"), self.country_input)
        form.addRow(QLabel("Temperature:"), self.unit_combo)
        layout.addLayout(form)

        save_btn = QPushButton("Save Weather Location")
        save_btn.setStyleSheet(
            f"background-color: {theme_color}; color: white; padding: 12px 24px; "
            "font-weight: bold; border-radius: 8px; font-size: 15px;"
        )
        save_btn.clicked.connect(self.save_weather_location)
        layout.addWidget(save_btn, alignment=Qt.AlignmentFlag.AlignLeft)
        layout.addStretch()

    def save_weather_location(self):
        city = self.city_input.text().strip()
        country = self.country_input.text().strip()
        if bool(city) != bool(country):
            QMessageBox.warning(
                self,
                "Weather Location",
                "Enter both a city and a country, or leave both blank.",
            )
            return

        self.launcher.config["_weather_city"] = city
        self.launcher.config["_weather_country"] = country
        self.launcher.config["_weather_temperature_unit"] = self.unit_combo.currentText()
        self.launcher.save_config_file()
        self.launcher.refresh_weather()
        log_info(f"Settings: Updated weather location to '{city}, {country}'")
        QMessageBox.information(
            self,
            "Weather Location",
            "Weather location saved. Current conditions will update shortly.",
        )
