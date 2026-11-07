def tab_widget_stylesheet(theme_color):
    return f"""
        QTabWidget::pane {{
            border: 1px solid rgba(255, 255, 255, 25);
            background: rgba(18, 18, 18, 220);
            border-radius: 10px;
        }}
        QTabBar::tab {{
            background: rgba(35, 35, 35, 180);
            color: #bbb;
            padding: 10px 22px;
            margin-right: 4px;
            border-top-left-radius: 8px;
            border-top-right-radius: 8px;
            font-size: 14px;
            font-weight: bold;
        }}
        QTabBar::tab:selected {{
            background: {theme_color};
            color: white;
        }}
    """
