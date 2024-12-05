import sys
import os
import time
import requests
import subprocess
import configparser
import re
import difflib
import json
import html
import datetime
from datetime import datetime
from dateutil import parser, tz
import xml.etree.ElementTree as ET
from PyQt5.QtGui import QFont, QIcon, QColor, QPainter
from PyQt5.QtCore import (
    Qt, QTimer, QPropertyAnimation, QAbstractAnimation, QThreadPool,
    QRunnable, pyqtSlot, QObject, pyqtSignal, QDateTime
)
from PyQt5 import QtWidgets, QtGui, QtCore
from PyQt5.QtWidgets import (
    QVBoxLayout, QLineEdit, QLabel, QPushButton, QListWidget, QWidget,
    QFileDialog, QCheckBox, QSizePolicy, QHBoxLayout, QDialog, QFormLayout,
    QDialogButtonBox, QTabWidget, QListWidgetItem, QSpinBox, QMenu, QAction
)

# Set your custom User-Agent here
CUSTOM_USER_AGENT = (
    "Connection: Keep-Alive User-Agent: okhttp/5.0.0-alpha.2 "
    "Accept-Encoding: gzip, deflate"
)

# Function to normalize channel names
def normalize_channel_name(name):
    # Lowercase and strip whitespace
    name = name.lower().strip()

    # Replace multiple spaces with one
    name = re.sub(r'\s+', ' ', name)

    # Remove special characters
    name = re.sub(r'[^\w\s]', '', name)

    # Remove common prefixes/suffixes (e.g., "HD", "SD", "Channel", "TV")
    name = re.sub(r'\b(hd|sd|channel|tv)\b', '', name)

    # Trim any remaining whitespace
    name = name.strip()

    return name

# Custom Progress Bar with text aligned to the left and percentage on the right
class CustomProgressIndicator(QtWidgets.QProgressBar):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.message = ""
        self.show_percentage = True  # Flag to control percentage display
        self.setTextVisible(False)   # Hide the default percentage text
        self.animation = None        # Initialize animation attribute

    def set_text_color(self, color):
        self.text_color = QtGui.QColor('black')  # Set custom text color

    def set_message(self, message, show_percentage=True):
        self.message = message
        self.show_percentage = show_percentage
        self.update()

    def animate_value(self, end_value):
        # Stop any existing animation
        if self.animation and self.animation.state() == QAbstractAnimation.Running:
            self.animation.stop()

        # Ensure the current value is updated before starting a new animation
        current_value = self.value()
        self.setValue(current_value)

        # Create a new animation instance for each animation
        self.animation = QPropertyAnimation(self, b"value", self)
        self.animation.setDuration(700)  # Duration in milliseconds
        self.animation.setStartValue(current_value)
        self.animation.setEndValue(end_value)
        self.animation.start()

    def start_indeterminate_animation(self):
        if self.animation and self.animation.state() == QAbstractAnimation.Running:
            return  # Animation already running

        self.animation = QPropertyAnimation(self, b"value", self)
        self.animation.setDuration(1000)  # 1 second per cycle
        self.animation.setStartValue(0)
        self.animation.setEndValue(100)
        self.animation.setEasingCurve(QEasingCurve.Linear)
        self.animation.setLoopCount(-1)  # Infinite loop
        self.animation.start()

    def stop_indeterminate_animation(self):
        if self.animation and self.animation.state() == QAbstractAnimation.Running:
            self.animation.stop()
        self.setValue(0)  # Reset progress value
        self.message = ""
        self.show_percentage = False
        self.update()

    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QtGui.QPainter(self)
        painter.setPen(QtGui.QColor('black'))
        font = painter.font()
        font.setPointSize(10)
        painter.setFont(font)
        rect = self.rect()

        # Ensure there's always some text to display or keep the bar visible
        message_text = self.message if self.message else "Processing..."
        percentage_text = f"{self.value()}%" if self.show_percentage else ""

        message_rect = painter.boundingRect(
            rect, QtCore.Qt.AlignLeft | QtCore.Qt.AlignVCenter, message_text)
        message_rect.moveLeft(5)

        percentage_rect = painter.boundingRect(
            rect, QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter, percentage_text)
        percentage_rect.moveRight(rect.width() - 5)

        painter.drawText(
            message_rect, QtCore.Qt.AlignLeft | QtCore.Qt.AlignVCenter, message_text)
        painter.drawText(
            percentage_rect, QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter, percentage_text)

# Worker Signals for EPG Loading
class EPGWorkerSignals(QObject):
    finished = pyqtSignal(dict, dict)  # epg_dict, channel_id_to_names
    error = pyqtSignal(str)


# Worker for EPG Loading
class EPGWorker(QRunnable):
    def __init__(self, server, username, password, http_method):
        super().__init__()
        self.server = server
        self.username = username
        self.password = password
        self.http_method = http_method
        self.signals = EPGWorkerSignals()

    @pyqtSlot()
    def run(self):
        try:
            cache_file = 'epg_cache.xml'
            cache_valid = False
            if os.path.exists(cache_file):
                cache_age = time.time() - os.path.getmtime(cache_file)
                if cache_age < 3600:  # 1 hour cache validity
                    cache_valid = True

            if cache_valid:
                with open(cache_file, 'rb') as f:
                    epg_xml_data = f.read()
            else:
                epg_url = f"{self.server}/xmltv.php?username={self.username}&password={self.password}"
                headers = {'User-Agent': CUSTOM_USER_AGENT}
                if self.http_method == 'POST':
                    response = requests.post(epg_url, headers=headers, timeout=10)
                else:
                    response = requests.get(epg_url, headers=headers, timeout=10)
                response.raise_for_status()
                epg_xml_data = response.content
                with open(cache_file, 'wb') as f:
                    f.write(epg_xml_data)

            epg_data, channel_id_to_names = self.parse_epg_data(epg_xml_data)
            self.signals.finished.emit(epg_data, channel_id_to_names)
        except Exception as e:
            self.signals.error.emit(str(e))

    def parse_epg_data(self, epg_xml_data):
        epg_dict = {}
        channel_id_to_names = {}
        try:
            # Parse the XML data
            epg_tree = ET.fromstring(epg_xml_data)

            # Build a mapping from channel_id to display-names (could be multiple names)
            for channel in epg_tree.findall('channel'):
                channel_id = channel.get('id')
                if channel_id:
                    channel_id = channel_id.strip().lower()
                    display_names = []
                    for display_name_elem in channel.findall('display-name'):
                        if display_name_elem.text:
                            display_name = display_name_elem.text.strip()
                            # Normalize the display name for consistent matching
                            normalized_name = normalize_channel_name(display_name)
                            display_names.append(normalized_name)
                    channel_id_to_names[channel_id] = display_names

            # Now, parse the programme elements and build the EPG data dictionary
            for programme in epg_tree.findall('programme'):
                channel_id = programme.get('channel')
                if channel_id:
                    channel_id = channel_id.strip().lower()

                start_time = programme.get('start')
                stop_time = programme.get('stop')
                title_elem = programme.find('title')
                description_elem = programme.find('desc')

                title = title_elem.text.strip() if title_elem is not None and title_elem.text else ''
                description = description_elem.text.strip() if description_elem is not None and description_elem.text else ''

                epg_entry = {
                    'start_time': start_time,
                    'stop_time': stop_time,
                    'title': title,
                    'description': description
                }

                if channel_id not in epg_dict:
                    epg_dict[channel_id] = []
                epg_dict[channel_id].append(epg_entry)

            # Return the EPG data and channel_id_to_names
            return epg_dict, channel_id_to_names

        except Exception as e:
            print(f"Error parsing EPG data: {e}")
            return {}, {}  # Return empty dictionaries on error


# Address Book Dialog for managing saved credentials
class AddressBookDialog(QtWidgets.QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Address Book")
        self.setMinimumSize(400, 300)
        self.parent = parent

        layout = QtWidgets.QVBoxLayout(self)

        # List widget to display saved credentials
        self.credentials_list = QtWidgets.QListWidget()
        layout.addWidget(self.credentials_list)

        # Buttons
        button_layout = QHBoxLayout()
        self.add_button = QtWidgets.QPushButton("Add")
        self.add_button.setIcon(self.style().standardIcon(QtWidgets.QStyle.SP_FileDialogNewFolder))
        self.select_button = QtWidgets.QPushButton("Select")
        self.select_button.setIcon(self.style().standardIcon(QtWidgets.QStyle.SP_DialogYesButton))
        self.delete_button = QtWidgets.QPushButton("Delete")
        self.delete_button.setIcon(self.style().standardIcon(QtWidgets.QStyle.SP_DialogCancelButton))
        button_layout.addWidget(self.add_button)
        button_layout.addWidget(self.select_button)
        button_layout.addWidget(self.delete_button)
        layout.addLayout(button_layout)

        # Load saved credentials
        self.load_saved_credentials()

        # Connect buttons
        self.add_button.clicked.connect(self.add_credentials)
        self.select_button.clicked.connect(self.select_credentials)
        self.delete_button.clicked.connect(self.delete_credentials)
        self.credentials_list.itemDoubleClicked.connect(self.double_click_credentials)

    def load_saved_credentials(self):
        self.credentials_list.clear()
        config = configparser.ConfigParser()
        config.read('credentials.ini')
        if 'Credentials' in config:
            for key in config['Credentials']:
                self.credentials_list.addItem(key)

    def add_credentials(self):
        dialog = AddCredentialsDialog(self)
        if dialog.exec_() == QtWidgets.QDialog.Accepted:
            method, name, *credentials = dialog.get_credentials()
            if name:
                config = configparser.ConfigParser()
                config.read('credentials.ini')
                if 'Credentials' not in config:
                    config['Credentials'] = {}
                if method == 'manual':
                    server, username, password = credentials
                    config['Credentials'][name] = f"manual|{server}|{username}|{password}"
                elif method == 'm3u_plus':
                    m3u_url, = credentials
                    config['Credentials'][name] = f"m3u_plus|{m3u_url}"
                else:
                    print("Unknown method")
                with open('credentials.ini', 'w') as config_file:
                    config.write(config_file)
                self.load_saved_credentials()

    def select_credentials(self):
        selected_item = self.credentials_list.currentItem()
        if selected_item:
            name = selected_item.text()
            config = configparser.ConfigParser()
            config.read('credentials.ini')
            if 'Credentials' in config and name in config['Credentials']:
                data = config['Credentials'][name]
                # Parse data to get the type and credentials
                if data.startswith('manual|'):
                    _, server, username, password = data.split('|')
                    # Update parent fields
                    self.parent.server_entry.setText(server)
                    self.parent.username_entry.setText(username)
                    self.parent.password_entry.setText(password)
                    # Proceed to login
                    self.parent.login()
                elif data.startswith('m3u_plus|'):
                    _, m3u_url = data.split('|', 1)
                    self.parent.extract_credentials_from_m3u_plus_url(m3u_url)
                    # Proceed to login
                    self.parent.login()
                else:
                    print("Unknown credential type")
                self.accept()

    def double_click_credentials(self, item):
        self.select_credentials()
        self.accept()

    def delete_credentials(self):
        selected_item = self.credentials_list.currentItem()
        if selected_item:
            name = selected_item.text()
            config = configparser.ConfigParser()
            config.read('credentials.ini')
            if 'Credentials' in config and name in config['Credentials']:
                del config['Credentials'][name]
                with open('credentials.ini', 'w') as config_file:
                    config.write(config_file)
                self.load_saved_credentials()


class AddCredentialsDialog(QtWidgets.QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Add Credentials")
        layout = QtWidgets.QVBoxLayout(self)

        # ComboBox to select the method
        self.method_selector = QtWidgets.QComboBox()
        self.method_selector.addItems(["Manual Entry", "m3u_plus URL Entry"])
        layout.addWidget(QtWidgets.QLabel("Select Method:"))
        layout.addWidget(self.method_selector)

        # Stack to hold the different forms
        self.stack = QtWidgets.QStackedWidget()
        layout.addWidget(self.stack)

        # Manual Entry Form
        self.manual_form = QtWidgets.QWidget()
        manual_layout = QtWidgets.QFormLayout(self.manual_form)
        self.name_entry_manual = QLineEdit()
        self.server_entry = QLineEdit()
        self.username_entry = QLineEdit()
        self.password_entry = QLineEdit()
        self.password_entry.setEchoMode(QLineEdit.Password)

        manual_layout.addRow("Name:", self.name_entry_manual)
        manual_layout.addRow("Server URL:", self.server_entry)
        manual_layout.addRow("Username:", self.username_entry)
        manual_layout.addRow("Password:", self.password_entry)

        # m3u_plus URL Entry Form
        self.m3u_form = QtWidgets.QWidget()
        m3u_layout = QtWidgets.QFormLayout(self.m3u_form)
        self.name_entry_m3u = QLineEdit()
        self.m3u_url_entry = QLineEdit()

        m3u_layout.addRow("Name:", self.name_entry_m3u)
        m3u_layout.addRow("m3u_plus URL:", self.m3u_url_entry)

        self.stack.addWidget(self.manual_form)
        self.stack.addWidget(self.m3u_form)

        # Connect method_selector to change the stack
        self.method_selector.currentIndexChanged.connect(self.stack.setCurrentIndex)

        # Dialog buttons
        buttons = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel,
            Qt.Horizontal, self)
        layout.addWidget(buttons)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

    def get_credentials(self):
        method = self.method_selector.currentText()
        if method == "Manual Entry":
            name = self.name_entry_manual.text().strip()
            server = self.server_entry.text().strip()
            username = self.username_entry.text().strip()
            password = self.password_entry.text().strip()
            return ('manual', name, server, username, password)
        else:
            name = self.name_entry_m3u.text().strip()
            m3u_url = self.m3u_url_entry.text().strip()
            return ('m3u_plus', name, m3u_url)


class IPTVPlayerApp(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Xtream IPTV Player by MY-1 V3.0")
        self.setMinimumSize(500, 500)

        # Initialize attributes
        self.groups = {}
        self.entries_per_tab = {
            'LIVE': [],
            'Movies': [],
            'Series': []
        }
        self.navigation_stacks = {
            'LIVE': [],
            'Movies': [],
            'Series': []
        }
        self.external_player_command = ""
        self.load_external_player_command()

        # Initialize top-level scroll positions for each tab
        self.top_level_scroll_positions = {
            'LIVE': 0,
            'Movies': 0,
            'Series': 0
        }

        # Initialize Xtream API credentials
        self.server = ""
        self.username = ""
        self.password = ""
        self.login_type = None  # 'xtream' or 'm3u'

        self.epg_data = {}  # Store EPG data
        self.channel_id_to_names = {}  # Store channel_id_to_names mapping
        self.epg_last_updated = None  # Timestamp for EPG data

        self.threadpool = QThreadPool()
        self.threadpool.setMaxThreadCount(10)  # Default thread count

        # Mapping dictionaries for EPG channel IDs
        self.epg_id_mapping = {
            # 'epg_channel_id_in_entry': 'channel_id_in_epg',
            # Populate this dictionary with your specific mappings
            # Example:
            # 'cnn': 'cnn.us',
            # 'fox': 'fox.us',
            # 'nbc': 'nbc.us',
        }

        # Create the central widget and main layout
        central_widget = QtWidgets.QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QtWidgets.QVBoxLayout(central_widget)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(5)  # Reduced spacing for a compact layout

        # Create the top controls layout
        # Adjust the controls layout
        controls_layout = QtWidgets.QVBoxLayout()
        controls_layout.setSpacing(5)  # Compact spacing between rows

        # Row 1: Server URL, Username, Password
        row1_layout = QHBoxLayout()
        row1_layout.setSpacing(10)

        self.server_label = QLabel("Server URL:")
        self.server_label.setFixedWidth(80)
        self.server_entry = QLineEdit()
        self.server_entry.setPlaceholderText("Enter Server URL...")
        self.server_entry.setClearButtonEnabled(True)

        self.username_label = QLabel("Username:")
        self.username_label.setFixedWidth(80)
        self.username_entry = QLineEdit()
        self.username_entry.setPlaceholderText("Enter Username...")
        self.username_entry.setClearButtonEnabled(True)

        self.password_label = QLabel("Password:")
        self.password_label.setFixedWidth(80)
        self.password_entry = QLineEdit()
        self.password_entry.setPlaceholderText("Enter Password...")
        self.password_entry.setEchoMode(QLineEdit.Password)
        self.password_entry.setClearButtonEnabled(True)

        row1_layout.addWidget(self.server_label)
        row1_layout.addWidget(self.server_entry)
        row1_layout.addWidget(self.username_label)
        row1_layout.addWidget(self.username_entry)
        row1_layout.addWidget(self.password_label)
        row1_layout.addWidget(self.password_entry)

        # Row 2: Buttons
        buttons_layout = QHBoxLayout()
        buttons_layout.setSpacing(10)

        self.login_button = QPushButton("Login")
        self.login_button.setIcon(self.style().standardIcon(QtWidgets.QStyle.SP_DialogApplyButton))
        self.login_button.clicked.connect(self.login)

        self.m3u_plus_button = QPushButton("M3u_plus")
        self.m3u_plus_button.setIcon(self.style().standardIcon(QtWidgets.QStyle.SP_FileDialogContentsView))
        self.m3u_plus_button.clicked.connect(self.open_m3u_plus_dialog)

        self.address_book_button = QPushButton("Address Book")
        self.address_book_button.setIcon(self.style().standardIcon(QtWidgets.QStyle.SP_DirIcon))
        self.address_book_button.setToolTip("Manage Saved Credentials")
        self.address_book_button.clicked.connect(self.open_address_book)

        self.choose_player_button = QPushButton("Choose Media Player")
        self.choose_player_button.setIcon(self.style().standardIcon(QtWidgets.QStyle.SP_MediaPlay))
        self.choose_player_button.clicked.connect(self.choose_external_player)

        buttons_layout.addWidget(self.login_button)
        buttons_layout.addWidget(self.m3u_plus_button)
        buttons_layout.addWidget(self.address_book_button)
        buttons_layout.addWidget(self.choose_player_button)

        # Checkbox layout (aligned to the right)
        checkbox_layout = QHBoxLayout()
        checkbox_layout.setAlignment(Qt.AlignRight)  # Align to the right

        # HTTP Method Checkbox
        self.http_method_checkbox = QCheckBox("Use POST Method")
        self.http_method_checkbox.setToolTip("Check to use POST instead of GET for server requests")
        checkbox_layout.addWidget(self.http_method_checkbox)

        # Keep on Top Checkbox
        self.keep_on_top_checkbox = QCheckBox("Keep on top")
        self.keep_on_top_checkbox.setToolTip("Keep the application on top of all windows")
        self.keep_on_top_checkbox.stateChanged.connect(self.toggle_keep_on_top)
        checkbox_layout.addWidget(self.keep_on_top_checkbox)

        # EPG Download Checkbox
        self.epg_checkbox = QCheckBox("Download EPG")
        self.epg_checkbox.setToolTip("Check to download EPG data for channels")
        checkbox_layout.addWidget(self.epg_checkbox)

        # Font Size Control
        self.font_size_label = QLabel("Font Size:")
        self.font_size_spinbox = QSpinBox()
        self.font_size_spinbox.setRange(8, 24)  # Set reasonable range for font sizes
        self.font_size_spinbox.setValue(10)  # Default font size
        self.font_size_spinbox.setToolTip("Set the font size for playlist items")
        self.font_size_spinbox.valueChanged.connect(self.update_font_size)
        self.font_size_spinbox.setFixedWidth(50)  # Adjust the width as needed

        self.default_font_size = 10  # Set the initial default font size


        # Add Font Size Control to Layout
        checkbox_layout.addWidget(self.font_size_label)
        checkbox_layout.addWidget(self.font_size_spinbox)



        # Add layouts to controls layout
        controls_layout.addLayout(row1_layout)
        controls_layout.addLayout(buttons_layout)
        controls_layout.addLayout(checkbox_layout)

        # Add controls layout to the main layout
        main_layout.addLayout(controls_layout)

        


        # Create and configure the custom progress bar
        self.progress_bar = CustomProgressIndicator()
        self.progress_bar.setValue(0)
        self.progress_bar.setMaximum(100)
        self.progress_bar.setFixedHeight(25)

        # Create a container widget for the main content
        content_widget = QtWidgets.QWidget()
        content_layout = QtWidgets.QVBoxLayout(content_widget)
        content_layout.setSpacing(10)

        # Create and configure tabs
        self.tab_widget = QTabWidget()
        content_layout.addWidget(self.tab_widget)

        live_icon = self.style().standardIcon(QtWidgets.QStyle.SP_MediaVolume)
        movies_icon = self.style().standardIcon(QtWidgets.QStyle.SP_MediaPlay)
        series_icon = self.style().standardIcon(QtWidgets.QStyle.SP_DialogYesButton)

        self.live_tab = QtWidgets.QWidget()
        self.movies_tab = QtWidgets.QWidget()
        self.series_tab = QtWidgets.QWidget()

        self.tab_widget.addTab(self.live_tab, live_icon, "LIVE")
        self.tab_widget.addTab(self.movies_tab, movies_icon, "Movies")
        self.tab_widget.addTab(self.series_tab, series_icon, "Series")

        self.live_layout = QtWidgets.QVBoxLayout(self.live_tab)
        self.movies_layout = QtWidgets.QVBoxLayout(self.movies_tab)
        self.series_layout = QtWidgets.QVBoxLayout(self.series_tab)

        self.search_bar_live = QLineEdit()
        self.search_bar_live.setPlaceholderText("Search Live Channels...")
        self.search_bar_live.setClearButtonEnabled(True)
        self.search_bar_live.addAction(QIcon.fromTheme("edit-find"), QLineEdit.LeadingPosition)
        self.search_bar_live.textChanged.connect(lambda text: self.search_in_list('LIVE', text))

        self.search_bar_movies = QLineEdit()
        self.search_bar_movies.setPlaceholderText("Search Movies...")
        self.search_bar_movies.setClearButtonEnabled(True)
        self.search_bar_movies.addAction(QIcon.fromTheme("edit-find"), QLineEdit.LeadingPosition)
        self.search_bar_movies.textChanged.connect(lambda text: self.search_in_list('Movies', text))

        self.search_bar_series = QLineEdit()
        self.search_bar_series.setPlaceholderText("Search Series...")
        self.search_bar_series.setClearButtonEnabled(True)
        self.search_bar_series.addAction(QIcon.fromTheme("edit-find"), QLineEdit.LeadingPosition)
        self.search_bar_series.textChanged.connect(lambda text: self.search_in_list('Series', text))

        self.add_search_bar(self.live_layout, self.search_bar_live)
        self.add_search_bar(self.movies_layout, self.search_bar_movies)
        self.add_search_bar(self.series_layout, self.search_bar_series)

        self.channel_list_live = QListWidget()
        self.channel_list_movies = QListWidget()
        self.channel_list_series = QListWidget()

        for list_widget in [self.channel_list_live, self.channel_list_movies, self.channel_list_series]:
            list_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        self.live_layout.addWidget(self.channel_list_live)
        self.movies_layout.addWidget(self.channel_list_movies)
        self.series_layout.addWidget(self.channel_list_series)

        self.list_widgets = {
            'LIVE': self.channel_list_live,
            'Movies': self.channel_list_movies,
            'Series': self.channel_list_series
        }

        self.tab_widget.currentChanged.connect(self.on_tab_change)
        self.channel_list_live.itemDoubleClicked.connect(self.channel_item_double_clicked)
        self.channel_list_movies.itemDoubleClicked.connect(self.channel_item_double_clicked)
        self.channel_list_series.itemDoubleClicked.connect(self.channel_item_double_clicked)

        main_layout.addWidget(content_widget)
        main_layout.addWidget(self.progress_bar)

        # Connect context menu
        for list_widget in self.list_widgets.values():
            list_widget.setContextMenuPolicy(Qt.CustomContextMenu)
            list_widget.customContextMenuRequested.connect(self.show_context_menu)

    # Helper methods
    def toggle_keep_on_top(self, state):
        if state == Qt.Checked:
            self.setWindowFlags(self.windowFlags() | Qt.WindowStaysOnTopHint)
        else:
            self.setWindowFlags(self.windowFlags() & ~Qt.WindowStaysOnTopHint)
        self.show()

    def add_search_bar(self, layout, search_bar):
        # The search icon is already added via addAction
        layout.addWidget(search_bar)

    def get_http_method(self):
        # Returns 'POST' if checkbox is checked, else 'GET'
        return 'POST' if self.http_method_checkbox.isChecked() else 'GET'

    def make_request(self, method, url, params=None, timeout=10):
        headers = {'User-Agent': CUSTOM_USER_AGENT}
        try:
            if method == 'POST':
                return requests.post(url, data=params, headers=headers, timeout=timeout)
            else:
                return requests.get(url, params=params, headers=headers, timeout=timeout)
        except requests.exceptions.Timeout:
            raise requests.exceptions.Timeout("Request timed out")

    def open_m3u_plus_dialog(self):
        # Open a dialog to paste the m3u_plus URL
        text, ok = QtWidgets.QInputDialog.getText(self, 'M3u_plus Login', 'Enter m3u_plus URL:')
        if ok and text:
            # Extract host, username, and password from the URL
            m3u_plus_url = text.strip()
            self.extract_credentials_from_m3u_plus_url(m3u_plus_url)
            # Proceed to login
            self.login()

    def set_item_font(self, item):
        """
        Sets the font for a QListWidgetItem based on the default font size.
        """
        font = QFont("Calibri", self.default_font_size)
        font.setBold(False)
        item.setFont(font)


    def update_font_size(self, value):
        # Store the updated font size
        self.default_font_size = value

        # Update font size for all current items in all tabs
        for tab_name, list_widget in self.list_widgets.items():
            for i in range(list_widget.count()):
                item = list_widget.item(i)
                font = item.font()
                font.setPointSize(value)  # Apply updated font size
                item.setFont(font)



    def extract_credentials_from_m3u_plus_url(self, url):
        try:
            # Updated pattern to support both "type=m3u_plus" and "type=m3u"
            pattern = r'(http[s]?://[^/]+)/get\.php\?username=([^&]*)&password=([^&]*)&type=(m3u_plus|m3u|&output=m3u8)'
            match = re.match(pattern, url)
            if match:
                self.server = match.group(1)
                self.username = match.group(2)
                self.password = match.group(3)

                # Update the GUI fields
                self.server_entry.setText(self.server)
                self.username_entry.setText(self.username)
                self.password_entry.setText(self.password)

                # Update progress bar for success
                self.progress_bar.set_message("Credentials extracted from URL", show_percentage=False)
                self.progress_bar.animate_value(100)
                # Reset progress bar to default color
                self.progress_bar.setStyleSheet("""
                    QProgressBar {
                        text-align: left;
                        background-color: #f0f0f0;
                    }
                """)
            else:
                # If URL doesn't match the expected format
                self.progress_bar.set_message("Invalid m3u_plus or m3u URL", show_percentage=False)
                self.progress_bar.animate_value(100)
                # Set progress bar to red
                self.progress_bar.setStyleSheet("""
                    QProgressBar {
                        text-align: left;
                        background-color: #f0f0f0;
                    }
                    QProgressBar::chunk {
                        background-color: red;
                    }
                """)
        except Exception as e:
            print(f"Error extracting credentials: {e}")
            self.progress_bar.set_message("Error extracting credentials", show_percentage=False)
            self.progress_bar.animate_value(100)
            # Set progress bar to red
            self.progress_bar.setStyleSheet("""
                QProgressBar {
                    text-align: left;
                    background-color: #f0f0f0;
                }
                QProgressBar::chunk {
                    background-color: red;
                }
            """)

    def get_list_widget(self, tab_name):
        return self.list_widgets.get(tab_name)

    def update_epg_thread_count(self, value):
        self.threadpool.setMaxThreadCount(value)
        print(f"EPG thread count set to: {value}")

    def load_external_player_command(self):
        config = configparser.ConfigParser()
        config.read('config.ini')
        if 'ExternalPlayer' in config:
            self.external_player_command = config['ExternalPlayer'].get('Command', '')

    def save_external_player_command(self):
        config = configparser.ConfigParser()
        config['ExternalPlayer'] = {'Command': self.external_player_command}
        with open('config.ini', 'w') as config_file:
            config.write(config_file)

    def login(self):
        # Clear EPG data from memory
        self.epg_data = {}
        self.channel_id_to_names = {}
        self.epg_last_updated = None

        # Clear UI elements that might display old EPG data
        for tab_name, list_widget in self.list_widgets.items():
            list_widget.clear()
        self.progress_bar.set_message("EPG data cleared from memory", show_percentage=False)

        # Delete the EPG cache file if it exists
        cache_file = 'epg_cache.xml'
        if os.path.exists(cache_file):
            try:
                os.remove(cache_file)
            except Exception as e:
                print(f"Error deleting cache file: {e}")
                self.progress_bar.set_message("Error deleting EPG cache", show_percentage=False)
                self.progress_bar.animate_value(100)
                # Set progress bar to red to indicate an error
                self.progress_bar.setStyleSheet("""
                    QProgressBar {
                        text-align: left;
                        background-color: #f0f0f0;
                    }
                    QProgressBar::chunk {
                        background-color: red;
                    }
                """)
                return  # Exit the login process if cache deletion fails

        # Retrieve the entered values
        server = self.server_entry.text().strip()
        username = self.username_entry.text().strip()
        password = self.password_entry.text().strip()

        # Reset progress bar before starting
        self.progress_bar.setValue(0)  # Reset progress to 0
        self.progress_bar.setStyleSheet("""  # Reset style to default
            QProgressBar {
                text-align: left;
                background-color: #f0f0f0;
            }
            QProgressBar::chunk {
                background-color: #00cc00;  # Default green
            }
        """)
        self.progress_bar.set_message("Logging in...", show_percentage=False)

        if not server or not username or not password:
            # Update progress bar with error message
            self.progress_bar.set_message("Please fill all fields", show_percentage=False)
            self.progress_bar.animate_value(100)
            self.progress_bar.setStyleSheet("""  # Set red background for error
                QProgressBar {
                    text-align: left;
                    background-color: #f0f0f0;
                }
                QProgressBar::chunk {
                    background-color: red;
                }
            """)
            return

        # Show progress bar message
        self.progress_bar.set_message("Logging in...", show_percentage=False)
        self.progress_bar.animate_value(100)  # Animate to 50% for initial login step

        # Perform the actual login task
        self.fetch_categories_only(server, username, password)



    def fetch_categories_only(self, server, username, password):
        try:
            # Determine the HTTP method
            http_method = self.get_http_method()

            # Prepare parameters
            params = {
                'username': username,
                'password': password,
                'action': 'get_live_categories'
            }

            # Fetch live categories with a timeout
            categories_url = f"{server}/player_api.php"
            live_response = self.make_request(http_method, categories_url, params, timeout=10)
            live_response.raise_for_status()

            # Fetch movies categories
            params['action'] = 'get_vod_categories'
            movies_response = self.make_request(http_method, categories_url, params, timeout=10)
            movies_response.raise_for_status()

            # Fetch series categories
            params['action'] = 'get_series_categories'
            series_response = self.make_request(http_method, categories_url, params, timeout=10)
            series_response.raise_for_status()

            # Store fetched categories and credentials
            self.groups = {
                "LIVE": live_response.json(),
                "Movies": movies_response.json(),
                "Series": series_response.json(),
            }
            self.server = server
            self.username = username
            self.password = password

            # Clear navigation stacks
            self.navigation_stacks = {
                'LIVE': [],
                'Movies': [],
                'Series': []
            }

            # Reset top-level scroll positions
            self.top_level_scroll_positions = {
                'LIVE': 0,
                'Movies': 0,
                'Series': 0
            }

            # Update the main player's channel lists
            self.login_type = 'xtream'  # Set login type to Xtream API
            self.update_category_lists('LIVE')
            self.update_category_lists('Movies')
            self.update_category_lists('Series')
            self.progress_bar.set_message("Login Successful", show_percentage=False)
            self.progress_bar.animate_value(100)
            # Reset progress bar to default color
            self.progress_bar.setStyleSheet("""
                QProgressBar {
                    text-align: left;
                    background-color: #f0f0f0;
                }
            """)

            # Load EPG data if checkbox is checked
            if self.epg_checkbox.isChecked():
                self.load_epg_data_async()

        except requests.exceptions.Timeout:
            print("Request timed out")
            self.progress_bar.set_message("Login timed out", show_percentage=False)
            self.progress_bar.animate_value(100)
            # Set progress bar to red
            self.progress_bar.setStyleSheet("""
                QProgressBar {
                    text-align: left;
                    background-color: #f0f0f0;
                }
                QProgressBar::chunk {
                    background-color: red;
                }
            """)
        except requests.RequestException as e:
            print(f"Network error: {e}")
            self.progress_bar.set_message("Network Error", show_percentage=False)
            self.progress_bar.animate_value(100)
            # Set progress bar to red
            self.progress_bar.setStyleSheet("""
                QProgressBar {
                    text-align: left;
                    background-color: #f0f0f0;
                }
                QProgressBar::chunk {
                    background-color: red;
                }
            """)
        except ValueError as e:
            print(f"JSON decode error: {e}")
            self.progress_bar.set_message("Invalid server response", show_percentage=False)
            self.progress_bar.animate_value(100)
            # Set progress bar to red
            self.progress_bar.setStyleSheet("""
                QProgressBar {
                    text-align: left;
                    background-color: #f0f0f0;
                }
                QProgressBar::chunk {
                    background-color: red;
                }
            """)
        except Exception as e:
            print(f"Error fetching categories: {e}")
            self.progress_bar.set_message("Error fetching categories", show_percentage=False)
            self.progress_bar.animate_value(100)
            # Set progress bar to red
            self.progress_bar.setStyleSheet("""
                QProgressBar {
                    text-align: left;
                    background-color: #f0f0f0;
                }
                QProgressBar::chunk {
                    background-color: red;
                }
            """)

    def load_epg_data_async(self):
        self.progress_bar.set_message("Playlist Done. EPG downloading", show_percentage=True)
        self.progress_bar.start_indeterminate_animation()  # Start indeterminate animation

        http_method = self.get_http_method()
        epg_worker = EPGWorker(self.server, self.username, self.password, http_method)
        epg_worker.signals.finished.connect(self.on_epg_loaded)
        epg_worker.signals.error.connect(self.on_epg_error)
        self.threadpool.start(epg_worker)

    def on_epg_loaded(self, epg_data):
        self.epg_data = epg_data
        self.progress_bar.stop_indeterminate_animation()  # Stop animation
        self.progress_bar.set_message("EPG data loaded", show_percentage=True)
        self.progress_bar.animate_value(100)
        
        # Update progress bar to white and blue gradient
        self.progress_bar.setStyleSheet("""
            QProgressBar {
                text-align: center;
                background-color: #f0f0f0;
                border: 1px solid #000000;
                border-radius: 5px;
            }
            QProgressBar::chunk {
                background: qlineargradient(
                    x1:0, y1:0, x2:1, y2:0,
                    stop:0 white, stop:1 #007bff
                );
                border-radius: 5px;
            }
        """)
        
        # Optionally, trigger UI updates if needed
        self.progress_bar.repaint()


    def on_epg_error(self, error_message):
        print(f"Error fetching EPG data: {error_message}")
        self.progress_bar.stop_indeterminate_animation()  # Stop animation
        self.progress_bar.set_message("Error fetching EPG data", show_percentage=False)
        self.progress_bar.animate_value(100)
        # Set progress bar to red to indicate an error
        self.progress_bar.setStyleSheet("""
            QProgressBar {
                text-align: left;
                background-color: #f0f0f0;
            }
            QProgressBar::chunk {
                background-color: red;
            }
        """)



    def channel_item_double_clicked(self, item):
        try:
            sender = self.sender()

            # Determine the category based on the sender
            category = {
                self.channel_list_live: 'LIVE',
                self.channel_list_movies: 'Movies',
                self.channel_list_series: 'Series'
            }.get(sender)

            if not category:
                print("Unknown sender")
                return

            selected_item = sender.currentItem()
            if not selected_item:
                print("No item selected")
                return

            selected_text = selected_item.text()

            # Save current scroll position before navigating
            list_widget = self.get_list_widget(category)
            current_scroll_position = list_widget.verticalScrollBar().value()
            stack = self.navigation_stacks[category]

            if stack:
                # Update the last level's scroll position
                stack[-1]['scroll_position'] = current_scroll_position
            else:
                # If stack is empty, we're at the top level; save the scroll position
                self.top_level_scroll_positions[category] = current_scroll_position

            # Handle Xtream API double-clicks
            self.handle_xtream_double_click(selected_item, selected_text, category, sender)

        except Exception as e:
            print(f"Error occurred while handling double click: {e}")

    def update_category_lists(self, tab_name):
        # Clear search bar
        if tab_name == 'LIVE':
            self.search_bar_live.clear()
        elif tab_name == 'Movies':
            self.search_bar_movies.clear()
        elif tab_name == 'Series':
            self.search_bar_series.clear()

        try:
            list_widget = self.get_list_widget(tab_name)
            list_widget.clear()

            # Populate new categories with sorted names
            group_list = self.groups[tab_name]
            category_names = sorted(group["category_name"] for group in group_list)
            for category_name in category_names:
                item = QListWidgetItem(category_name)
                # Set the same font as in show_channels
                font = QFont("Calibri", 10)
                font.setBold(False)
                item.setFont(font)
                self.set_item_font(item)
                list_widget.addItem(item)

            # Restore the scroll position
            scroll_position = self.top_level_scroll_positions.get(tab_name, 0)
            list_widget.verticalScrollBar().setValue(scroll_position)
        except Exception as e:
            print(f"Error updating category lists: {e}")
            self.progress_bar.set_message("Error updating lists", show_percentage=False)
            self.progress_bar.animate_value(100)
            # Set progress bar to red
            self.progress_bar.setStyleSheet("""
                QProgressBar {
                    text-align: left;
                    background-color: #f0f0f0;
                }
                QProgressBar::chunk {
                    background-color: red;
                }
            """)

    def fetch_channels(self, category_name, tab_name):
        try:
            # Find the category ID for the selected category name
            category_id = next(g["category_id"] for g in self.groups[tab_name] if g["category_name"] == category_name)

            # Save current scroll position
            list_widget = self.get_list_widget(tab_name)
            current_scroll_position = list_widget.verticalScrollBar().value()
            stack = self.navigation_stacks[tab_name]
            if stack:
                stack[-1]['scroll_position'] = current_scroll_position
            else:
                self.top_level_scroll_positions[tab_name] = current_scroll_position

            # Determine the HTTP method
            http_method = self.get_http_method()

            # Prepare parameters
            params = {
                'username': self.username,
                'password': self.password,
                'action': '',
                'category_id': category_id
            }

            # Build the URL based on the tab type (Live, Movies)
            if tab_name == "LIVE":
                params['action'] = 'get_live_streams'
                list_widget = self.channel_list_live
                stream_type = "live"
            elif tab_name == "Movies":
                params['action'] = 'get_vod_streams'
                list_widget = self.channel_list_movies
                stream_type = "movie"

            streams_url = f"{self.server}/player_api.php"

            # Fetch the channels/streams from the server
            response = self.make_request(http_method, streams_url, params)
            response.raise_for_status()

            data = response.json()
            if not isinstance(data, list):
                raise ValueError("Expected a list of channels")
            self.entries_per_tab[tab_name] = data

            entries = self.entries_per_tab[tab_name]

            if isinstance(entries, dict) and "streams" in entries:
                entries = entries["streams"]

            for entry in entries:
                stream_id = entry.get("stream_id")
                epg_channel_id = entry.get("epg_channel_id")  # Get the EPG channel ID

                # Normalize epg_channel_id
                if epg_channel_id:
                    epg_channel_id = epg_channel_id.strip().lower()
                else:
                    epg_channel_id = None

                container_extension = entry.get("container_extension", "m3u8")  # Default to "m3u8" if not found
                if stream_id:
                    entry["url"] = f"{self.server}/{stream_type}/{self.username}/{self.password}/{stream_id}.{container_extension}"
                else:
                    entry["url"] = None
                entry["epg_channel_id"] = epg_channel_id  # Ensure epg_channel_id is stored in the entry

            # Update the navigation stack
            self.navigation_stacks[tab_name].append({'level': 'channels', 'data': {'tab_name': tab_name, 'entries': entries}, 'scroll_position': 0})
            self.show_channels(list_widget, tab_name)
            # Reset progress bar
            

        except requests.RequestException as e:
            print(f"Network error: {e}")
            self.progress_bar.set_message("Network Error", show_percentage=False)
            self.progress_bar.animate_value(100)
            # Set progress bar to red
            self.progress_bar.setStyleSheet("""
                QProgressBar {
                    text-align: left;
                    background-color: #f0f0f0;
                }
                QProgressBar::chunk {
                    background-color: red;
                }
            """)
        except ValueError as e:
            print(f"Data validation error: {e}")
            self.progress_bar.set_message("Invalid channel data received", show_percentage=False)
            self.progress_bar.animate_value(100)
            # Set progress bar to red
            self.progress_bar.setStyleSheet("""
                QProgressBar {
                    text-align: left;
                    background-color: #f0f0f0;
                }
                QProgressBar::chunk {
                    background-color: red;
                }
            """)
        except Exception as e:
            print(f"Error fetching channels: {e}")
            self.progress_bar.set_message("Error fetching channels", show_percentage=False)
            self.progress_bar.animate_value(100)
            # Set progress bar to red
            self.progress_bar.setStyleSheet("""
                QProgressBar {
                    text-align: left;
                    background-color: #f0f0f0;
                }
                QProgressBar::chunk {
                    background-color: red;
                }
            """)

    def handle_xtream_double_click(self, selected_item, selected_text, tab_name, sender):
        # Handle Xtream API double-clicks
        try:
            list_widget = self.get_list_widget(tab_name)
            stack = self.navigation_stacks[tab_name]

            if selected_text == "Go Back":
                # Handle "Go Back" functionality
                if stack:
                    # Pop the last level from the stack
                    stack.pop()
                    if stack:
                        last_level = stack[-1]
                        level = last_level['level']
                        data = last_level['data']
                        scroll_position = last_level.get('scroll_position', 0)
                        if level == 'categories':
                            self.update_category_lists(tab_name)
                            list_widget.verticalScrollBar().setValue(scroll_position)
                        elif level == 'channels':
                            self.entries_per_tab[tab_name] = data['entries']
                            self.show_channels(list_widget, tab_name)
                            list_widget.verticalScrollBar().setValue(scroll_position)
                        elif level == 'series_categories':
                            self.show_series_in_category(data['series_list'], restore_scroll_position=True, scroll_position=scroll_position)
                        elif level == 'series':
                            self.show_seasons(data['seasons'], restore_scroll_position=True, scroll_position=scroll_position)
                        elif level == 'season':
                            self.show_episodes(data['episodes'], restore_scroll_position=True, scroll_position=scroll_position)
                        else:
                            # Other levels...
                            pass
                    else:
                        # Stack is now empty, show categories and restore top-level scroll position
                        self.update_category_lists(tab_name)
                        list_widget.verticalScrollBar().setValue(self.top_level_scroll_positions.get(tab_name, 0))
                else:
                    # Stack is empty, we're at the top level
                    # Restore scroll position
                    self.update_category_lists(tab_name)
                    list_widget.verticalScrollBar().setValue(self.top_level_scroll_positions.get(tab_name, 0))
                return

            # Handle selecting a category and loading channels (Live, Movies, or Series)
            if tab_name != "Series":
                if selected_text in [group["category_name"] for group in self.groups[tab_name]]:
                    self.fetch_channels(selected_text, tab_name)
                else:
                    selected_entry = selected_item.data(Qt.UserRole)
                    if selected_entry and "url" in selected_entry:
                        self.play_channel(selected_entry)
                    else:
                        self.progress_bar.set_message("Invalid selection or URL not found", show_percentage=False)
                        self.progress_bar.animate_value(100)
                        # Set progress bar to red
                        self.progress_bar.setStyleSheet("""
                            QProgressBar {
                                text-align: left;
                                background-color: #f0f0f0;
                            }
                            QProgressBar::chunk {
                                background-color: red;
                            }
                        """)
                return

            # For Series Tab
            if tab_name == "Series":
                if not stack:
                    if selected_text in [group["category_name"] for group in self.groups["Series"]]:
                        self.fetch_series_in_category(selected_text)
                        return

                # If at series list level
                elif stack[-1]['level'] == 'series_categories':
                    series_entry = selected_item.data(Qt.UserRole)
                    if series_entry and "series_id" in series_entry:
                        self.fetch_seasons(series_entry)
                        return
                    else:
                        self.progress_bar.set_message("Series ID not found", show_percentage=False)
                        self.progress_bar.animate_value(100)
                        # Set progress bar to red
                        self.progress_bar.setStyleSheet("""
                            QProgressBar {
                                text-align: left;
                                background-color: #f0f0f0;
                            }
                            QProgressBar::chunk {
                                background-color: red;
                            }
                        """)
                        return

                # If at seasons level
                elif stack[-1]['level'] == 'series':
                    season_number = selected_item.data(Qt.UserRole)
                    series_entry = stack[-1]['data']['series_entry']
                    self.fetch_episodes(series_entry, season_number)
                    return

                # If at episodes level
                elif stack[-1]['level'] == 'season':
                    selected_entry = selected_item.data(Qt.UserRole)
                    if selected_entry and "url" in selected_entry:
                        self.play_channel(selected_entry)
                    else:
                        self.progress_bar.set_message("Invalid selection or URL not found", show_percentage=False)
                        self.progress_bar.animate_value(100)
                        # Set progress bar to red
                        self.progress_bar.setStyleSheet("""
                            QProgressBar {
                                text-align: left;
                                background-color: #f0f0f0;
                            }
                            QProgressBar::chunk {
                                background-color: red;
                            }
                        """)
                    return

        except Exception as e:
            print(f"Error loading channels: {e}")
            self.progress_bar.set_message("Error loading channels", show_percentage=False)
            self.progress_bar.animate_value(100)
            # Set progress bar to red
            self.progress_bar.setStyleSheet("""
                QProgressBar {
                    text-align: left;
                    background-color: #f0f0f0;
                }
                QProgressBar::chunk {
                    background-color: red;
                }
            """)

    def show_channels(self, list_widget, tab_name):
        try:
            list_widget.clear()
            list_widget.addItem("Go Back")

            items = []

            for idx, entry in enumerate(self.entries_per_tab[tab_name]):
                if "name" not in entry:
                    print(f"Warning: Channel entry at index {idx} is missing 'name'.")
                display_text = entry.get("name", "Unnamed Channel")
                tooltip_text = ""  # Initialize tooltip text

                if tab_name == "LIVE" and self.epg_data:
                    epg_channel_id = entry.get('epg_channel_id')
                    if epg_channel_id:
                        epg_channel_id = epg_channel_id.strip().lower()
                    else:
                        epg_channel_id = None

                    epg_info_list = None
                    if epg_channel_id and epg_channel_id in self.epg_data:
                        # Use EPG data matched by epg_channel_id
                        epg_info_list = self.epg_data[epg_channel_id]
                    else:
                        # Fallback to matching by name
                        channel_name = normalize_channel_name(entry.get('name', ''))
                        best_match_channel_id = self.find_best_epg_match(channel_name)
                        epg_info_list = self.epg_data.get(best_match_channel_id, [])

                    if epg_info_list:
                        # Get current datetime with local timezone
                        now = datetime.now(tz=tz.tzlocal())
                        current_epg = None
                        for epg in epg_info_list:
                            # Parse the start and stop times with timezone awareness
                            start_time = parser.parse(epg['start_time'])
                            stop_time = parser.parse(epg['stop_time'])

                            if start_time <= now <= stop_time:
                                current_epg = epg
                                break
                            elif start_time > now:
                                current_epg = epg
                                break

                        if current_epg:
                            # Convert times to local timezone
                            start_time = start_time.astimezone(tz.tzlocal())
                            stop_time = stop_time.astimezone(tz.tzlocal())

                            # Format times
                            start_time_formatted = start_time.strftime("%I:%M %p")
                            stop_time_formatted = stop_time.strftime("%I:%M %p")
                            title = current_epg['title']

                            display_text += f" - {title} ({start_time_formatted} - {stop_time_formatted})"
                            tooltip_text = current_epg['description']
                        else:
                            display_text += " - No Current EPG Data Available"
                            tooltip_text = "No current EPG information found for this channel."
                    

                # Create the QListWidgetItem with the display text
                item = QListWidgetItem(display_text)
                item.setData(Qt.UserRole, entry)

                # Apply a readable font without bold
                font = QFont("Calibri", 10)  # Choose a preferred font family and size
                font.setBold(False)            # Set font weight to normal
                item.setFont(font)
                self.set_item_font(item)
                self.set_item_font(item)
                
                # Set the tooltip if available
                if tooltip_text:
                    # Escape HTML special characters in the description using html.escape
                    description_html = html.escape(tooltip_text)
                    # Format the tooltip using HTML to limit the width and enable text wrapping
                    tooltip_text_formatted = f"""
                    <div style="max-width: 300px; white-space: normal;">
                        {description_html}
                    </div>
                    """
                    item.setToolTip(tooltip_text_formatted)

                items.append(item)

            # Sort items alphabetically by their text
            items.sort(key=lambda x: x.text())

            # Add all items to the list widget in a batch
            for item in items:
                list_widget.addItem(item)

            # Scroll to top when entering a new list
            list_widget.verticalScrollBar().setValue(0)
        except Exception as e:
            print(f"Error displaying channels: {e}")
            self.progress_bar.set_message("Error displaying channels", show_percentage=False)
            self.progress_bar.animate_value(100)
            # Set progress bar to red
            self.progress_bar.setStyleSheet("""
                QProgressBar {
                    text-align: left;
                    background-color: #f0f0f0;
                }
                QProgressBar::chunk {
                    background-color: red;
                }
            """)
    def fetch_series_in_category(self, category_name):
        try:
            # Save current scroll position
            list_widget = self.get_list_widget('Series')
            current_scroll_position = list_widget.verticalScrollBar().value()
            stack = self.navigation_stacks['Series']
            if stack:
                stack[-1]['scroll_position'] = current_scroll_position
            else:
                self.top_level_scroll_positions['Series'] = current_scroll_position

            # Find the category ID for the selected category name
            category_id = next(g["category_id"] for g in self.groups["Series"] if g["category_name"] == category_name)

            # Determine the HTTP method
            http_method = self.get_http_method()

            # Prepare parameters
            params = {
                'username': self.username,
                'password': self.password,
                'action': 'get_series',
                'category_id': category_id
            }

            streams_url = f"{self.server}/player_api.php"

            # Fetch the series from the server
            response = self.make_request(http_method, streams_url, params)
            response.raise_for_status()

            series_list = response.json()

            # Update the navigation stack
            self.navigation_stacks['Series'].append({'level': 'series_categories', 'data': {'series_list': series_list}, 'scroll_position': 0})

            self.show_series_in_category(series_list)

        except Exception as e:
            print(f"Error fetching series: {e}")
            self.progress_bar.set_message("Error fetching series", show_percentage=False)
            self.progress_bar.animate_value(100)
            self.progress_bar.setStyleSheet("""
                QProgressBar {
                    text-align: left;
                    background-color: #f0f0f0;
                }
                QProgressBar::chunk {
                    background-color: red;
                }
            """)

    def show_series_in_category(self, series_list, restore_scroll_position=False, scroll_position=0):
        try:
            list_widget = self.channel_list_series

            list_widget.clear()
            list_widget.addItem("Go Back")

            items = []
            for entry in series_list:
                item = QListWidgetItem(entry["name"])
                item.setData(Qt.UserRole, entry)
                self.set_item_font(item)
                items.append(item)

            items.sort(key=lambda x: x.text())
            for item in items:
                list_widget.addItem(item)

            # Restore the scroll position
            if restore_scroll_position:
                QTimer.singleShot(0, lambda: list_widget.verticalScrollBar().setValue(scroll_position))
            else:
                list_widget.verticalScrollBar().setValue(0)

            # Store the current series list
            self.current_series_list = series_list

        except Exception as e:
            print(f"Error displaying series: {e}")
            self.progress_bar.set_message("Error displaying series", show_percentage=False)
            self.progress_bar.animate_value(100)
            self.progress_bar.setStyleSheet("""
                QProgressBar {
                    text-align: left;
                    background-color: #f0f0f0;
                }
                QProgressBar::chunk {
                    background-color: red;
                }
            """)

    def fetch_seasons(self, series_entry):
        try:
            # Save current scroll position
            list_widget = self.get_list_widget('Series')
            current_scroll_position = list_widget.verticalScrollBar().value()
            stack = self.navigation_stacks['Series']
            if stack:
                stack[-1]['scroll_position'] = current_scroll_position

            # Determine the HTTP method
            http_method = self.get_http_method()

            # Prepare parameters
            params = {
                'username': self.username,
                'password': self.password,
                'action': 'get_series_info',
                'series_id': series_entry["series_id"]
            }

            episodes_url = f"{self.server}/player_api.php"

            response = self.make_request(http_method, episodes_url, params)
            response.raise_for_status()

            series_info = response.json()

            self.series_info = series_info  # Store for later use

            seasons = list(series_info.get("episodes", {}).keys())

            # Update the navigation stack
            self.navigation_stacks['Series'].append({'level': 'series', 'data': {'series_entry': series_entry, 'seasons': seasons}, 'scroll_position': 0})

            self.show_seasons(seasons)

        except Exception as e:
            print(f"Error fetching seasons: {e}")
            self.progress_bar.set_message("Error fetching seasons", show_percentage=False)
            self.progress_bar.animate_value(100)
            self.progress_bar.setStyleSheet("""
                QProgressBar {
                    text-align: left;
                    background-color: #f0f0f0;
                }
                QProgressBar::chunk {
                    background-color: red;
                }
            """)

    def show_seasons(self, seasons, restore_scroll_position=False, scroll_position=0):
        try:
            list_widget = self.channel_list_series

            list_widget.clear()
            list_widget.addItem("Go Back")

            # Convert and sort seasons numerically
            seasons_int = sorted([int(season) for season in seasons])

            items = []
            for season in seasons_int:
                season_str = str(season)  # Convert back to string
                item = QListWidgetItem(f"Season {season}")
                item.setData(Qt.UserRole, season_str)
                self.set_item_font(item)
                items.append(item)

            for item in items:
                list_widget.addItem(item)

            # Restore the scroll position
            if restore_scroll_position:
                QTimer.singleShot(0, lambda: list_widget.verticalScrollBar().setValue(scroll_position))
            else:
                list_widget.verticalScrollBar().setValue(0)

            # Update current seasons
            self.current_seasons = [str(season) for season in seasons_int]

        except Exception as e:
            print(f"Error displaying seasons: {e}")
            self.progress_bar.set_message("Error displaying seasons", show_percentage=False)
            self.progress_bar.animate_value(100)
            self.progress_bar.setStyleSheet("""
                QProgressBar {
                    text-align: left;
                    background-color: #f0f0f0;
                }
                QProgressBar::chunk {
                    background-color: red;
                }
            """)

    def fetch_episodes(self, series_entry, season_number):
        try:
            # Save current scroll position
            list_widget = self.get_list_widget('Series')
            current_scroll_position = list_widget.verticalScrollBar().value()
            stack = self.navigation_stacks['Series']
            if stack:
                stack[-1]['scroll_position'] = current_scroll_position

            episodes = self.series_info.get("episodes", {}).get(str(season_number), [])

            # Update the current stack
            self.navigation_stacks['Series'].append({'level': 'season', 'data': {'season_number': season_number, 'episodes': episodes}, 'scroll_position': 0})

            self.show_episodes(episodes)

        except Exception as e:
            print(f"Error fetching episodes: {e}")
            self.progress_bar.set_message("Error fetching episodes", show_percentage=False)
            self.progress_bar.animate_value(100)
            self.progress_bar.setStyleSheet("""
                QProgressBar {
                    text-align: left;
                    background-color: #f0f0f0;
                }
                QProgressBar::chunk {
                    background-color: red;
                }
            """)

    def show_episodes(self, episodes, restore_scroll_position=False, scroll_position=0):
        try:
            list_widget = self.channel_list_series

            # Clear the existing items and add the "Go Back" option
            list_widget.clear()
            list_widget.addItem("Go Back")

            # Sort episodes numerically by episode number to ensure proper order
            episodes_sorted = sorted(episodes, key=lambda x: int(x.get('episode_num', 0)))

            # Retrieve the series title from the current stack
            stack = self.navigation_stacks['Series']
            if stack and len(stack) >= 2 and 'series_entry' in stack[-2]['data']:
                series_title = stack[-2]['data']['series_entry'].get('name', '').strip()
            else:
                series_title = "Unknown Series"  # Fallback if series title is not found

            items = []
            for episode in episodes_sorted:
                # Extract fields and ensure proper types
                raw_episode_title = str(episode.get('title', 'Untitled Episode')).strip()
                season = str(episode.get('season', '1'))  # Convert to string if it's not already
                episode_num = str(episode.get('episode_num', '1'))  # Convert to string if it's not already

                # Format season and episode numbers with leading zeros
                try:
                    season_int = int(season)
                    episode_num_int = int(episode_num)
                    episode_code = f"S{season_int:02d}E{episode_num_int:02d}"
                except ValueError:
                    # Handle cases where season or episode numbers are not integers
                    episode_code = f"S{season}E{episode_num}"

                # Clean up the episode title to avoid redundancy
                if series_title in raw_episode_title:
                    episode_title = raw_episode_title.replace(series_title, '').strip(" -")
                else:
                    episode_title = raw_episode_title

                # Ensure episode_code is not mistakenly added to the title
                if episode_code in episode_title:
                    episode_title = episode_title.replace(episode_code, '').strip(" -")

                # Construct the display text
                display_text = f"{series_title} - {episode_code} - {episode_title}"

                # Prepare the entry dictionary with necessary information for playback
                episode_entry = {
                    "season": season,
                    "episode_num": episode_num,
                    "name": display_text,
                    "url": f"{self.server}/series/{self.username}/{self.password}/{episode['id']}.{episode['container_extension']}",
                    "title": episode_title
                }

                # Create a QListWidgetItem with the display text
                item = QListWidgetItem(display_text)
                item.setData(Qt.UserRole, episode_entry)
                items.append(item)
                self.set_item_font(item)

            # Add all episode items to the list widget
            for item in items:
                list_widget.addItem(item)

            # Restore the scroll position
            if restore_scroll_position:
                QTimer.singleShot(0, lambda: list_widget.verticalScrollBar().setValue(scroll_position))
            else:
                list_widget.verticalScrollBar().setValue(0)

            # Store the current episodes for potential future use
            self.current_episodes = episodes_sorted

        except Exception as e:
            print(f"Error displaying episodes: {e}")
            self.progress_bar.set_message("Error displaying episodes", show_percentage=False)
            self.progress_bar.animate_value(100)
            self.progress_bar.setStyleSheet("""
                QProgressBar {
                    text-align: left;
                    background-color: #f0f0f0;
                }
                QProgressBar::chunk {
                    background-color: red;
                }
            """)



    def find_best_epg_match(self, channel_name):
        # Prepare a list of all EPG channel names with their corresponding channel_id
        epg_channel_names = []
        for channel_id, names in self.channel_id_to_names.items():
            for name in names:
                epg_channel_names.append((name, channel_id))

        # Find the best match using difflib
        best_match = None
        highest_ratio = 0
        for epg_name, channel_id in epg_channel_names:
            ratio = difflib.SequenceMatcher(None, channel_name, epg_name).ratio()
            # Print the ratio for debugging
            
            if ratio > highest_ratio:
                highest_ratio = ratio
                best_match = channel_id

        # Adjust the threshold as needed
        if highest_ratio > 0.6:
            
            return best_match
        else:
            
            return None

    def normalize_channel_name(self, name):
        # Lowercase, strip whitespace, remove special characters
        name = name.lower()
        name = name.strip()
        name = re.sub(r'\s+', ' ', name)  # Replace multiple spaces with one
        name = re.sub(r'[^\w\s]', '', name)  # Remove non-alphanumeric characters
        return name


    def play_channel(self, entry):
        try:
            # Ensure that the entry contains a "url" key with the stream URL
            stream_url = entry.get("url")
            if not stream_url:
                # Update progress bar with error message
                self.progress_bar.set_message("Stream URL not found", show_percentage=False)
                self.progress_bar.animate_value(100)
                # Set progress bar to red
                self.progress_bar.setStyleSheet("""
                    QProgressBar {
                        text-align: left;
                        background-color: #f0f0f0;
                    }
                    QProgressBar::chunk {
                        background-color: red;
                    }
                """)
                return

            # Debug: Print the URL to verify it's being handled correctly
            print(f"Playing stream URL: {stream_url}")

            # Check if an external player is set (e.g., VLC)
            if self.external_player_command:
                # Play the stream using the external player
                subprocess.Popen([self.external_player_command, stream_url])
            else:
                # Update progress bar with error message
                self.progress_bar.set_message("No external player configured", show_percentage=False)
                self.progress_bar.animate_value(100)
                # Set progress bar to red
                self.progress_bar.setStyleSheet("""
                    QProgressBar {
                        text-align: left;
                        background-color: #f0f0f0;
                    }
                    QProgressBar::chunk {
                        background-color: red;
                    }
                """)
        except Exception as e:
            print(f"Error playing channel: {e}")
            self.progress_bar.set_message("Error playing channel", show_percentage=False)
            self.progress_bar.animate_value(100)
            # Set progress bar to red
            self.progress_bar.setStyleSheet("""
                QProgressBar {
                    text-align: left;
                    background-color: #f0f0f0;
                }
                QProgressBar::chunk {
                    background-color: red;
                }
            """)

    def on_tab_change(self, index):
        tab_name = self.tab_widget.tabText(index)
        if self.login_type == 'xtream':
            # Get the navigation stack for the current tab
            stack = self.navigation_stacks[tab_name]
            list_widget = self.get_list_widget(tab_name)
            if not stack:
                # At top level, show categories and restore top-level scroll position
                self.update_category_lists(tab_name)
                list_widget.verticalScrollBar().setValue(self.top_level_scroll_positions.get(tab_name, 0))
            else:
                # Get the last level
                last_level = stack[-1]
                level = last_level['level']
                data = last_level['data']
                scroll_position = last_level.get('scroll_position', 0)
                if level == 'categories':
                    self.update_category_lists(tab_name)
                    list_widget.verticalScrollBar().setValue(scroll_position)
                elif level == 'channels':
                    self.entries_per_tab[tab_name] = data['entries']
                    self.show_channels(list_widget, tab_name)
                    list_widget.verticalScrollBar().setValue(scroll_position)
                elif level == 'series_categories':
                    self.show_series_in_category(data['series_list'], restore_scroll_position=True, scroll_position=scroll_position)
                elif level == 'series':
                    self.show_seasons(data['seasons'], restore_scroll_position=True, scroll_position=scroll_position)
                elif level == 'season':
                    self.show_episodes(data['episodes'], restore_scroll_position=True, scroll_position=scroll_position)
                else:
                    # Other levels...
                    pass

    def choose_external_player(self):
        file_dialog = QFileDialog()
        file_dialog.setFileMode(QFileDialog.ExistingFile)
        # Adjust name filter based on OS
        if sys.platform.startswith('win'):
            file_dialog.setNameFilter("Executable files (*.exe *.bat)")
        else:
            file_dialog.setNameFilter("Executable files (*)")
        file_dialog.setWindowTitle("Select External Media Player")
        if file_dialog.exec_():
            file_paths = file_dialog.selectedFiles()
            if len(file_paths) > 0:
                self.external_player_command = file_paths[0]
                self.save_external_player_command()
                print("External Player selected:", self.external_player_command)

    def load_external_player_command(self):
        config = configparser.ConfigParser()
        config.read('config.ini')
        if 'ExternalPlayer' in config:
            self.external_player_command = config['ExternalPlayer'].get('Command', '')

    def save_external_player_command(self):
        config = configparser.ConfigParser()
        config['ExternalPlayer'] = {'Command': self.external_player_command}
        with open('config.ini', 'w') as config_file:
            config.write(config_file)

    def show_context_menu(self, position):
        sender = self.sender()
        menu = QMenu()
        sort_action = QAction("Sort Alphabetically", self)
        sort_action.setIcon(self.style().standardIcon(QtWidgets.QStyle.SP_ArrowUp))
        sort_action.triggered.connect(lambda: self.sort_channel_list(sender))
        menu.addAction(sort_action)
        menu.exec_(sender.viewport().mapToGlobal(position))

    def sort_channel_list(self, list_widget):
        try:
            items = []
            for i in range(list_widget.count()):
                item = list_widget.item(i)
                if item.text() != "Go Back":
                    items.append(item)

            items.sort(key=lambda x: x.text())
            list_widget.clear()

            if self.navigation_stacks[self.tab_widget.tabText(self.tab_widget.currentIndex())]:
                list_widget.addItem("Go Back")

            for item in items:
                list_widget.addItem(item)
        except Exception as e:
            print(f"Error sorting channel list: {e}")

    def search_in_list(self, tab_name, text):
        list_widget = self.get_list_widget(tab_name)

        if not list_widget:
            return

        list_widget.clear()

        if self.navigation_stacks[tab_name]:
            list_widget.addItem("Go Back")

        filtered_items = []
        if self.login_type == 'xtream':
            if tab_name != "Series":
                for entry in self.entries_per_tab[tab_name]:
                    if text.lower() in entry['name'].lower():
                        item = QListWidgetItem(entry['name'])
                        item.setData(Qt.UserRole, entry)
                        # Apply the same font as in show_channels
                        font = QFont("Calibri", 10)
                        font.setBold(False)
                        item.setFont(font)
                        filtered_items.append(item)
            else:
                # Handle search in Series tab based on current level
                stack = self.navigation_stacks['Series']
                if not stack or stack[-1]['level'] == 'series_categories':
                    for group in self.groups["Series"]:
                        if text.lower() in group["category_name"].lower():
                            item = QListWidgetItem(group["category_name"])
                            # Apply the same font as in show_channels
                            font = QFont("Calibri", 10)
                            font.setBold(False)
                            item.setFont(font)
                            filtered_items.append(item)
                elif stack[-1]['level'] == 'series_categories':
                    for entry in self.current_series_list:
                        if text.lower() in entry['name'].lower():
                            item = QListWidgetItem(entry['name'])
                            item.setData(Qt.UserRole, entry)
                            # Apply the same font as in show_channels
                            font = QFont("Calibri", 10)
                            font.setBold(False)
                            item.setFont(font)
                            filtered_items.append(item)
                elif stack[-1]['level'] == 'series':
                    for season in self.current_seasons:
                        if text.lower() in f"Season {season}".lower():
                            item = QListWidgetItem(f"Season {season}")
                            item.setData(Qt.UserRole, season)
                            # Apply the same font as in show_channels
                            font = QFont("Calibri", 10)
                            font.setBold(False)
                            item.setFont(font)
                            filtered_items.append(item)
                elif stack[-1]['level'] == 'season':
                    for episode in self.current_episodes:
                        if text.lower() in episode['title'].lower():
                            episode_entry = {
                                "season": episode.get('season'),
                                "episode_num": episode['episode_num'],
                                "name": f"{episode['title']}",
                                "url": f"{self.server}/series/{self.username}/{self.password}/{episode['id']}.{episode['container_extension']}",
                                "title": episode['title']
                            }
                            item = QListWidgetItem(f"Episode {episode['episode_num']}: {episode['title']}")
                            item.setData(Qt.UserRole, episode_entry)
                            # Apply the same font as in show_channels
                            font = QFont("Calibri", 10)
                            font.setBold(False)
                            item.setFont(font)
                            filtered_items.append(item)

        for item in filtered_items:
            list_widget.addItem(item)

    def open_address_book(self):
        dialog = AddressBookDialog(self)
        dialog.exec_()

    def update_epg_thread_count(self, value):
        self.threadpool.setMaxThreadCount(value)
        print(f"EPG thread count set to: {value}")


def main():
    app = QtWidgets.QApplication(sys.argv)

    # Set the application style to Fusion
    app.setStyle('Fusion')

    player = IPTVPlayerApp()
    player.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
