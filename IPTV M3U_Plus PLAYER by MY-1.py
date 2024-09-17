import sys
import requests
import subprocess
import configparser
import re
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QApplication, QStyleFactory
from PyQt5 import QtWidgets, QtGui, QtCore, QtNetwork
from PyQt5.QtWidgets import QVBoxLayout, QLineEdit, QLabel, QPushButton, QListWidget, QWidget, QFileDialog, QCheckBox

import qdarkstyle  # Ensure you have installed qdarkstyle via pip

# Set your custom User-Agent here
CUSTOM_USER_AGENT = ""


# Custom Progress Bar with text aligned to the left and percentage on the right
class CustomProgressIndicator(QtWidgets.QProgressBar):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.message = ""
        self.show_percentage = True  # Flag to control percentage display
        self.setTextVisible(False)   # Hide the default percentage text

    def set_text_color(self, color):
        self.text_color = QtGui.QColor(white)  # Set custom text color

    def set_message(self, message, show_percentage=True):
        self.message = message
        self.show_percentage = show_percentage
        self.update()

    def paintEvent(self, event):
        super().paintEvent(event)

        # Draw custom text inside the progress bar
        painter = QtGui.QPainter(self)
        painter.setPen(QtGui.QColor('white'))  # Set text color

        font = painter.font()
        font.setPointSize(10)
        painter.setFont(font)

        rect = self.rect()

        # Prepare the message text
        message_text = self.message
        percentage_text = f"{self.value()}%" if self.show_percentage else ""

        # Calculate positions
        message_rect = painter.boundingRect(rect, QtCore.Qt.AlignLeft | QtCore.Qt.AlignVCenter, message_text)
        message_rect.moveLeft(5)  # Padding from the left

        percentage_rect = painter.boundingRect(rect, QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter, percentage_text)
        percentage_rect.moveRight(rect.width() - 5)  # Padding from the right

        # Draw the texts
        painter.drawText(message_rect, QtCore.Qt.AlignLeft | QtCore.Qt.AlignVCenter, message_text)
        painter.drawText(percentage_rect, QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter, percentage_text)



# Xtream API Login window
class XtreamLoginWindow(QWidget):
    def __init__(self, player):
        super().__init__()
        self.player = player  # Reference to the main IPTVPlayerApp instance
        self.setWindowTitle("Xtream API Login")

        self.url_label = QLabel("Server URL:")
        self.username_label = QLabel("Username:")
        self.password_label = QLabel("Password:")

        # Set the size of the window
        self.resize(400, 300)

        # Set the window to stay on top of other windows
        self.setWindowFlags(self.windowFlags() | Qt.WindowStaysOnTopHint)
        

        self.url_input = QLineEdit(self)
        self.username_input = QLineEdit(self)
        self.password_input = QLineEdit(self)
        self.password_input.setEchoMode(QLineEdit.Password)  # Hide password input

        # Set default text in the input fields (you may want to remove these in production)
        self.url_input.setText("http://hostengine.live:25461")
        self.username_input.setText("CarlaLuck")
        self.password_input.setText("5467@")

        self.login_button = QPushButton("Login", self)
        self.login_button.clicked.connect(self.login)

        layout = QVBoxLayout(self)
        layout.addWidget(self.url_label)
        layout.addWidget(self.url_input)
        layout.addWidget(self.username_label)
        layout.addWidget(self.username_input)
        layout.addWidget(self.password_label)
        layout.addWidget(self.password_input)
        layout.addWidget(self.login_button)

        

    def login(self):
        # Retrieve the entered values
        server = self.url_input.text().strip()
        username = self.username_input.text().strip()
        password = self.password_input.text().strip()

        if not server or not username or not password:
            # Update progress bar with error message
            self.player.progress_bar.set_message("Please fill all fields", show_percentage=False)
            self.player.progress_bar.setValue(100)
            self.player.progress_bar.setStyleSheet("""
                QProgressBar {
                    text-align: left;
                }
                QProgressBar::chunk {
                    background-color: red;
                }
            """)
            return

        # Show progress bar message
        self.player.progress_bar.set_message("Logging in...", show_percentage=False)
        self.player.progress_bar.setValue(50)
        self.player.progress_bar.setStyleSheet("""
            QProgressBar {
                text-align: left;
            }
        """)

        self.fetch_categories_only(server, username, password)

    def fetch_categories_only(self, server, username, password):
        try:
            # Determine the HTTP method
            http_method = self.player.get_http_method()

            # Prepare parameters
            params = {
                'username': username,
                'password': password,
                'action': 'get_live_categories'
            }

            # Fetch live categories
            categories_url = f"{server}/player_api.php"
            live_response = self.player.make_request(http_method, categories_url, params)
            live_response.raise_for_status()

            # Fetch movies categories
            params['action'] = 'get_vod_categories'
            movies_response = self.player.make_request(http_method, categories_url, params)
            movies_response.raise_for_status()

            # Fetch series categories
            params['action'] = 'get_series_categories'
            series_response = self.player.make_request(http_method, categories_url, params)
            series_response.raise_for_status()

            # Store fetched categories and credentials in the main player
            self.player.groups = {
                "LIVE": live_response.json(),
                "Movies": movies_response.json(),
                "Series": series_response.json(),
            }
            self.player.server = server
            self.player.username = username
            self.player.password = password

            # Update the main player's channel lists
            self.player.login_type = 'xtream'  # Set login type to Xtream API
            self.player.update_category_lists()
            self.player.progress_bar.set_message("Login Successful", show_percentage=False)
            self.player.progress_bar.setValue(100)
            # Reset progress bar to default color
            self.player.progress_bar.setStyleSheet("""
                QProgressBar {
                    text-align: left;
                }
            """)
            self.close()
        except requests.RequestException as e:
            print(f"Network error: {e}")
            self.player.progress_bar.set_message("Network Error", show_percentage=False)
            self.player.progress_bar.setValue(100)
            # Set progress bar to red
            self.player.progress_bar.setStyleSheet("""
                QProgressBar {
                    text-align: left;
                }
                QProgressBar::chunk {
                    background-color: red;
                }
            """)
        except ValueError as e:
            print(f"JSON decode error: {e}")
            self.player.progress_bar.set_message("Invalid server response", show_percentage=False)
            self.player.progress_bar.setValue(100)
            # Set progress bar to red
            self.player.progress_bar.setStyleSheet("""
                QProgressBar {
                    text-align: left;
                }
                QProgressBar::chunk {
                    background-color: red;
                }
            """)


# IPTVPlayerApp class
class IPTVPlayerApp(QtWidgets.QMainWindow):
    # ... [The rest of the IPTVPlayerApp code remains unchanged]
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Xtream & m3u_plus IPTV Player by My-1")
        self.setMinimumSize(800, 600)

        # Initialize attributes
        self.groups = {}
        self.entries = {
            'LIVE': [],
            'Movies': [],
            'Series': []
        }
        self.current_group = ""
        self.current_tab = None
        self.external_player_command = ""
        self.load_external_player_command()

        # Initialize Xtream API credentials
        self.server = ""
        self.username = ""
        self.password = ""
        self.login_type = None  # 'xtream' or 'm3u'

        # Create the central widget and main layout
        central_widget = QtWidgets.QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QtWidgets.QVBoxLayout(central_widget)

        # Create the top controls layout
        top_layout = QtWidgets.QHBoxLayout()
        self.url_entry = QtWidgets.QLineEdit()
        self.url_entry.setPlaceholderText("Enter M3U playlist URL...")
        self.load_button = QtWidgets.QPushButton("Load m3u")
        self.clear_button = QtWidgets.QPushButton("Clear")
        self.choose_player_button = QtWidgets.QPushButton("Choose Media Player")
        self.login_button = QtWidgets.QPushButton("Xtream API Login")
        self.http_method_checkbox = QCheckBox("Use POST Method")
        self.http_method_checkbox.setToolTip("Check to use POST instead of GET for server requests")

        top_layout.addWidget(QtWidgets.QLabel("M3U URL:"))
        top_layout.addWidget(self.url_entry)
        top_layout.addWidget(self.clear_button)
        top_layout.addWidget(self.load_button)
        top_layout.addWidget(self.choose_player_button)
        top_layout.addWidget(self.login_button)
        top_layout.addWidget(self.http_method_checkbox)

        main_layout.addLayout(top_layout)

        # Create and configure the custom progress bar
        self.progress_bar = CustomProgressIndicator()
        self.progress_bar.setValue(0)
        self.progress_bar.setMaximum(100)

        # Create a container widget for the main content
        content_widget = QtWidgets.QWidget()
        content_layout = QtWidgets.QVBoxLayout(content_widget)

        # Create and configure tabs
        self.tab_widget = QtWidgets.QTabWidget()
        content_layout.addWidget(self.tab_widget)

        self.live_tab = QtWidgets.QWidget()
        self.movies_tab = QtWidgets.QWidget()
        self.series_tab = QtWidgets.QWidget()

        self.tab_widget.addTab(self.live_tab, "LIVE")
        self.tab_widget.addTab(self.movies_tab, "Movies")
        self.tab_widget.addTab(self.series_tab, "Series")

        self.live_layout = QtWidgets.QVBoxLayout(self.live_tab)
        self.movies_layout = QtWidgets.QVBoxLayout(self.movies_tab)
        self.series_layout = QtWidgets.QVBoxLayout(self.series_tab)

        self.channel_list_live = QtWidgets.QListWidget()
        self.channel_list_movies = QtWidgets.QListWidget()
        self.channel_list_series = QtWidgets.QListWidget()

        self.live_layout.addWidget(self.channel_list_live)
        self.movies_layout.addWidget(self.channel_list_movies)
        self.series_layout.addWidget(self.channel_list_series)

        # Connect signals
        self.clear_button.clicked.connect(self.clear_url)
        self.load_button.clicked.connect(self.load_playlist)
        self.choose_player_button.clicked.connect(self.choose_external_player)
        self.login_button.clicked.connect(self.open_xtream_login)
        self.tab_widget.currentChanged.connect(self.on_tab_change)

        # Connect the item double-clicked signals to the unified handler
        self.channel_list_live.itemDoubleClicked.connect(self.channel_item_double_clicked)
        self.channel_list_movies.itemDoubleClicked.connect(self.channel_item_double_clicked)
        self.channel_list_series.itemDoubleClicked.connect(self.channel_item_double_clicked)

        # Initialize QNetworkAccessManager
        self.network_manager = QtNetwork.QNetworkAccessManager()

        main_layout.addWidget(content_widget)
        main_layout.addWidget(self.progress_bar)

    def get_http_method(self):
        # Returns 'POST' if checkbox is checked, else 'GET'
        return 'POST' if self.http_method_checkbox.isChecked() else 'GET'

    def make_request(self, method, url, params=None):
        headers = {'User-Agent': CUSTOM_USER_AGENT}
        if method == 'POST':
            return requests.post(url, data=params, headers=headers)
        else:
            return requests.get(url, params=params, headers=headers)

    def open_xtream_login(self):
        self.xtream_login_window = XtreamLoginWindow(self)
        self.xtream_login_window.show()

    def load_playlist(self):
        # Logic to load M3U playlist
        self.login_type = 'm3u'  # Set login type to M3U
        self.progress_bar.set_message("Idle", show_percentage=False)
        self.progress_bar.setValue(0)
        url = self.url_entry.text()

        if not url:
            self.progress_bar.set_message("Please enter a playlist URL", show_percentage=False)
            self.progress_bar.setValue(100)
            # Set progress bar to red
            self.progress_bar.setStyleSheet("""
                QProgressBar {
                    text-align: left;
                }
                QProgressBar::chunk {
                    background-color: red;
                }
            """)
            return

        request = QtNetwork.QNetworkRequest(QtCore.QUrl(url))
        # Set custom User-Agent for the M3U request
        request.setRawHeader(b'User-Agent', CUSTOM_USER_AGENT.encode('utf-8'))
        self.reply = self.network_manager.get(request)
        self.reply.downloadProgress.connect(self.update_progress_bar)
        self.reply.finished.connect(self.m3u_download_finished)
        self.progress_bar.set_message("Downloading Playlist")
        self.progress_bar.setValue(0)
        # Reset progress bar to default color
        self.progress_bar.setStyleSheet("""
            QProgressBar {
                text-align: left;
            }
        """)

    def update_progress_bar(self, bytes_received, bytes_total):
        if bytes_total > 0:
            progress = (bytes_received / bytes_total) * 100
            self.progress_bar.setValue(int(progress))

    def m3u_download_finished(self):
        if self.reply.error() != QtNetwork.QNetworkReply.NoError:
            print("Error downloading playlist")
            self.progress_bar.set_message("Error downloading playlist", show_percentage=False)
            self.progress_bar.setValue(100)
            # Set progress bar to red
            self.progress_bar.setStyleSheet("""
                QProgressBar {
                    text-align: left;
                }
                QProgressBar::chunk {
                    background-color: red;
                }
            """)
            return
        data = self.reply.readAll().data()
        text = data.decode('utf-8', errors='ignore')
        lines = text.split('\n')
        self.process_lines(lines)
        self.update_channel_list()
        self.progress_bar.set_message("Playlist Downloaded", show_percentage=False)
        self.progress_bar.setValue(100)
        # Reset progress bar to default color
        self.progress_bar.setStyleSheet("""
            QProgressBar {
                text-align: left;
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

            if self.login_type == 'xtream':
                self.handle_xtream_double_click(selected_text, category, sender)
            elif self.login_type == 'm3u':
                self.handle_m3u_double_click(selected_text, category, sender)
            else:
                print("Unknown login type")
        except Exception as e:
            print(f"Error occurred while handling double click: {e}")

    def handle_m3u_double_click(self, selected_text, category, sender):
        # Handle M3U playlist double-clicks
        try:
            # Handle "Go Back" functionality
            if selected_text == "Go Back":
                self.current_group = ""  # Reset current group
                sender.clear()  # Clear the current list
                self.update_channel_list()  # Go back to the category list
                return

            # Handle group selection (Load channels within the selected group)
            if not self.current_group and selected_text in [entry["group_title"] for entry in self.entries[category]]:
                self.current_group = selected_text
                sender.clear()  # Clear the current list
                sender.addItem("Go Back")  # Add "Go Back" option at the top

                # Load channels for the selected group
                for entry in self.entries[category]:
                    if entry["group_title"] == self.current_group:
                        sender.addItem(entry["tvg_name"])
                return

            # Handle channel selection (Play the channel)
            selected_entry = next((entry for entry in self.entries[category] if entry["tvg_name"] == selected_text), None)
            if selected_entry:
                self.play(selected_entry["url"])  # Play the selected channel
            else:
                print(f"No channel found for selected item: {selected_text}")

        except Exception as e:
            print(f"Error occurred while loading channels: {e}")

    def handle_xtream_double_click(self, selected_text, category, sender):
        # Handle Xtream API double-clicks
        try:
            # Handle "Go Back" functionality
            if selected_text == "Go Back":
                if self.current_group:
                    # Go back to category level if in a group
                    self.current_group = ""
                    self.update_category_lists()
                else:
                    # If at top level, reset the view
                    self.update_category_lists()
                return

            # Handle selecting a category and loading channels (Live or Movies)
            tab_name = category
            if selected_text in [group["category_name"] for group in self.groups[tab_name]]:
                self.current_category = selected_text
                self.fetch_channels(self.current_category, tab_name)
                return

            # Handle selecting a series (Series tab)
            if tab_name == "Series" and selected_text in [entry["name"] for entry in self.entries]:
                selected_series = next(entry for entry in self.entries if entry["name"] == selected_text)
                if "series_id" in selected_series:
                    # Fetch episodes for the selected series
                    self.fetch_episodes(selected_series["series_id"], sender)
                else:
                    # Update progress bar with error message
                    self.progress_bar.set_message("Series ID not found", show_percentage=False)
                    self.progress_bar.setValue(100)
                    # Set progress bar to red
                    self.progress_bar.setStyleSheet("""
                        QProgressBar {
                            text-align: left;
                        }
                        QProgressBar::chunk {
                            background-color: red;
                        }
                    """)
                return

            # Handle selecting a season (Don't play, just list episodes)
            if "Season" in selected_text:
                print(f"Season selected: {selected_text}")
                # Handle it by displaying episodes
                self.show_episodes_for_selected_season(selected_text, sender)
                return

            # Handle selecting an episode and playing it
            index = sender.currentRow() - 1  # Adjust for "Go Back"
            if 0 <= index < len(self.entries):
                selected_entry = self.entries[index]
                if "url" in selected_entry:
                    print(f"Playing URL: {selected_entry['url']}")  # Debugging: Print the URL to play
                    self.play_channel(selected_entry)  # Play the selected channel or episode
                else:
                    # Update progress bar with error message
                    self.progress_bar.set_message("Stream URL not found", show_percentage=False)
                    self.progress_bar.setValue(100)
                    # Set progress bar to red
                    self.progress_bar.setStyleSheet("""
                        QProgressBar {
                            text-align: left;
                        }
                        QProgressBar::chunk {
                            background-color: red;
                        }
                    """)
            else:
                # Update progress bar with error message
                self.progress_bar.set_message("Invalid selection", show_percentage=False)
                self.progress_bar.setValue(100)
                # Set progress bar to red
                self.progress_bar.setStyleSheet("""
                    QProgressBar {
                        text-align: left;
                    }
                    QProgressBar::chunk {
                        background-color: red;
                    }
                """)
        except Exception as e:
            print(f"Error loading channels: {e}")
            self.progress_bar.set_message("Error loading channels", show_percentage=False)
            self.progress_bar.setValue(100)
            # Set progress bar to red
            self.progress_bar.setStyleSheet("""
                QProgressBar {
                    text-align: left;
                }
                QProgressBar::chunk {
                    background-color: red;
                }
            """)

    def update_channel_list(self):
        # Update the channel list for M3U playlists
        for tab_name, tab_widget in {
            'LIVE': self.channel_list_live,
            'Movies': self.channel_list_movies,
            'Series': self.channel_list_series
        }.items():
            tab_widget.clear()
            if self.current_group:
                tab_widget.addItem("Go Back")
                for entry in self.entries[tab_name]:
                    if entry["group_title"] == self.current_group:
                        tab_widget.addItem(entry["tvg_name"])
            else:
                groups = set(entry["group_title"] for entry in self.entries[tab_name])
                for group in groups:
                    tab_widget.addItem(group)

    def update_category_lists(self):
        try:
            # Clear existing lists
            self.channel_list_live.clear()
            self.channel_list_movies.clear()
            self.channel_list_series.clear()

            # Populate new categories
            for group in self.groups["LIVE"]:
                self.channel_list_live.addItem(group["category_name"])

            for movie in self.groups["Movies"]:
                self.channel_list_movies.addItem(movie["category_name"])

            for serie in self.groups["Series"]:
                self.channel_list_series.addItem(serie["category_name"])
        except Exception as e:
            print(f"Error updating category lists: {e}")
            self.progress_bar.set_message("Error updating lists", show_percentage=False)
            self.progress_bar.setValue(100)
            # Set progress bar to red
            self.progress_bar.setStyleSheet("""
                QProgressBar {
                    text-align: left;
                }
                QProgressBar::chunk {
                    background-color: red;
                }
            """)

    def fetch_channels(self, category_name, tab_name):
        try:
            # Find the category ID for the selected category name
            category_id = next(g["category_id"] for g in self.groups[tab_name] if g["category_name"] == category_name)

            # Determine the HTTP method
            http_method = self.get_http_method()

            # Prepare parameters
            params = {
                'username': self.username,
                'password': self.password,
                'action': '',
                'category_id': category_id
            }

            # Build the URL based on the tab type (Live, Movies, Series)
            if tab_name == "LIVE":
                params['action'] = 'get_live_streams'
                list_widget = self.channel_list_live
                stream_type = "live"
            elif tab_name == "Movies":
                params['action'] = 'get_vod_streams'
                list_widget = self.channel_list_movies
                stream_type = "movie"
            else:
                params['action'] = 'get_series'
                list_widget = self.channel_list_series
                stream_type = "series"

            streams_url = f"{self.server}/player_api.php"

            # Fetch the channels/streams from the server
            response = self.make_request(http_method, streams_url, params)
            response.raise_for_status()

            self.entries = response.json()

            if isinstance(self.entries, dict) and "streams" in self.entries:
                self.entries = self.entries["streams"]

            # For series, fetch episodes later, so don't assign URLs yet
            if tab_name != "Series":
                for entry in self.entries:
                    stream_id = entry.get("stream_id")
                    if stream_id:
                        entry["url"] = f"{self.server}/{stream_type}/{self.username}/{self.password}/{stream_id}.m3u8"
                    else:
                        entry["url"] = None

            self.show_channels(list_widget)
        except requests.RequestException as e:
            print(f"Network error: {e}")
            self.progress_bar.set_message("Network Error", show_percentage=False)
            self.progress_bar.setValue(100)
            # Set progress bar to red
            self.progress_bar.setStyleSheet("""
                QProgressBar {
                    text-align: left;
                }
                QProgressBar::chunk {
                    background-color: red;
                }
            """)
        except ValueError as e:
            print(f"JSON decode error: {e}")
            self.progress_bar.set_message("Invalid server response", show_percentage=False)
            self.progress_bar.setValue(100)
            # Set progress bar to red
            self.progress_bar.setStyleSheet("""
                QProgressBar {
                    text-align: left;
                }
                QProgressBar::chunk {
                    background-color: red;
                }
            """)
        except Exception as e:
            print(f"Error fetching channels: {e}")
            self.progress_bar.set_message("Error fetching channels", show_percentage=False)
            self.progress_bar.setValue(100)
            # Set progress bar to red
            self.progress_bar.setStyleSheet("""
                QProgressBar {
                    text-align: left;
                }
                QProgressBar::chunk {
                    background-color: red;
                }
            """)

    def show_channels(self, list_widget):
        try:
            # Ensure that the list_widget is cleared and channels are displayed
            if isinstance(list_widget, QListWidget):
                list_widget.clear()
                list_widget.addItem("Go Back")
                for entry in self.entries:
                    list_widget.addItem(entry["name"])
            else:
                print("Expected a QListWidget, but received an invalid widget.")
                self.progress_bar.set_message("Error displaying channels", show_percentage=False)
                self.progress_bar.setValue(100)
                # Set progress bar to red
                self.progress_bar.setStyleSheet("""
                    QProgressBar {
                        text-align: left;
                    }
                    QProgressBar::chunk {
                        background-color: red;
                    }
                """)
        except Exception as e:
            print(f"Error displaying channels: {e}")
            self.progress_bar.set_message("Error displaying channels", show_percentage=False)
            self.progress_bar.setValue(100)
            # Set progress bar to red
            self.progress_bar.setStyleSheet("""
                QProgressBar {
                    text-align: left;
                }
                QProgressBar::chunk {
                    background-color: red;
                }
            """)

    def fetch_episodes(self, series_id, list_widget):
        try:
            # Determine the HTTP method
            http_method = self.get_http_method()

            # Prepare parameters
            params = {
                'username': self.username,
                'password': self.password,
                'action': 'get_series_info',
                'series_id': series_id
            }

            episodes_url = f"{self.server}/player_api.php"

            response = self.make_request(http_method, episodes_url, params)
            response.raise_for_status()

            series_info = response.json()

            # Clear previous entries and add "Go Back"
            self.entries = []
            list_widget.clear()
            list_widget.addItem("Go Back")

            # List the seasons
            for season, episodes in series_info.get("episodes", {}).items():
                # Add the season to the list
                list_widget.addItem(f"Season {season}")

                # Store the episodes in self.entries for future selection
                for episode in episodes:
                    episode_entry = {
                        "season": season,
                        "episode_num": episode['episode_num'],
                        "name": f"Episode {episode['episode_num']}: {episode['title']}",
                        "url": f"{self.server}/series/{self.username}/{self.password}/{episode['id']}.{episode['container_extension']}",
                        "title": episode['title']
                    }
                    self.entries.append(episode_entry)

        except requests.RequestException as e:
            print(f"Network error: {e}")
            self.progress_bar.set_message("Network Error", show_percentage=False)
            self.progress_bar.setValue(100)
            # Set progress bar to red
            self.progress_bar.setStyleSheet("""
                QProgressBar {
                    text-align: left;
                }
                QProgressBar::chunk {
                    background-color: red;
                }
            """)
        except ValueError as e:
            print(f"JSON decode error: {e}")
            self.progress_bar.set_message("Invalid server response", show_percentage=False)
            self.progress_bar.setValue(100)
            # Set progress bar to red
            self.progress_bar.setStyleSheet("""
                QProgressBar {
                    text-align: left;
                }
                QProgressBar::chunk {
                    background-color: red;
                }
            """)
        except Exception as e:
            print(f"Error fetching episodes: {e}")
            self.progress_bar.set_message("Error fetching episodes", show_percentage=False)
            self.progress_bar.setValue(100)
            # Set progress bar to red
            self.progress_bar.setStyleSheet("""
                QProgressBar {
                    text-align: left;
                }
                QProgressBar::chunk {
                    background-color: red;
                }
            """)

    def show_episodes_for_selected_season(self, selected_season, list_widget):
        try:
            # Clear current entries and add "Go Back"
            list_widget.clear()
            list_widget.addItem("Go Back")

            # List episodes for the selected season
            for entry in self.entries:
                # Match the season number with the selected season
                if entry["season"] == selected_season.split()[-1]:
                    list_widget.addItem(f"   {entry['name']}")  # Indent the episodes under the season

        except Exception as e:
            print(f"Error showing episodes: {e}")
            self.progress_bar.set_message("Error showing episodes", show_percentage=False)
            self.progress_bar.setValue(100)
            # Set progress bar to red
            self.progress_bar.setStyleSheet("""
                QProgressBar {
                    text-align: left;
                }
                QProgressBar::chunk {
                    background-color: red;
                }
            """)

    def play_channel(self, entry):
        try:
            # Ensure that the entry contains a "url" key with the stream URL
            stream_url = entry.get("url")
            if not stream_url:
                # Update progress bar with error message
                self.progress_bar.set_message("Stream URL not found", show_percentage=False)
                self.progress_bar.setValue(100)
                # Set progress bar to red
                self.progress_bar.setStyleSheet("""
                    QProgressBar {
                        text-align: left;
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
                self.progress_bar.setValue(100)
                # Set progress bar to red
                self.progress_bar.setStyleSheet("""
                    QProgressBar {
                        text-align: left;
                    }
                    QProgressBar::chunk {
                        background-color: red;
                    }
                """)
        except Exception as e:
            print(f"Error playing channel: {e}")
            self.progress_bar.set_message("Error playing channel", show_percentage=False)
            self.progress_bar.setValue(100)
            # Set progress bar to red
            self.progress_bar.setStyleSheet("""
                QProgressBar {
                    text-align: left;
                }
                QProgressBar::chunk {
                    background-color: red;
                }
            """)

    def process_lines(self, lines):
        self.entries = {'LIVE': [], 'Movies': [], 'Series': []}

        current_entry = None
        for line in lines:
            line = line.strip()
            if line.startswith("#EXTINF:-1"):
                info = line[len("#EXTINF:-1"):].strip()
                attributes = {}
                match = re.findall(r'([\w-]+)="([^"]*)"', info)
                for key, value in match:
                    attributes[key] = value

                tvg_id = attributes.get("tvg-id", "")
                tvg_name = attributes.get("tvg-name", "")
                tvg_logo = attributes.get("tvg-logo", "")
                group_title = attributes.get("group-title", "No Group")
                title = info.split(",")[-1].strip()

                current_entry = {
                    "tvg_id": tvg_id,
                    "tvg_name": tvg_name or title,
                    "tvg_logo": tvg_logo,
                    "group_title": group_title,
                    "url": ""
                }
            elif line and not line.startswith("#"):
                if current_entry:
                    current_entry["url"] = line
                    url = current_entry["url"]
                    if "movie" in url.lower():
                        self.entries['Movies'].append(current_entry)
                    elif "series" in url.lower():
                        self.entries['Series'].append(current_entry)
                    else:
                        self.entries['LIVE'].append(current_entry)
                    current_entry = None

    def play(self, url):
        if self.external_player_command:
            subprocess.Popen([self.external_player_command, url])
        else:
            # Update progress bar with error message
            self.progress_bar.set_message("No external player configured", show_percentage=False)
            self.progress_bar.setValue(100)
            # Set progress bar to red
            self.progress_bar.setStyleSheet("""
                QProgressBar {
                    text-align: left;
                }
                QProgressBar::chunk {
                    background-color: red;
                }
            """)

    def clear_url(self):
        self.url_entry.clear()

    def on_tab_change(self, index):
        # Reset the current group when switching tabs
        self.current_group = ""
        

    def choose_external_player(self):
        file_dialog = QFileDialog()
        file_dialog.setFileMode(QFileDialog.ExistingFile)
        file_dialog.setNameFilter("Executable files (*.exe)")
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


def main():
    app = QtWidgets.QApplication(sys.argv)

    # Apply QDarkStyleSheet for a professional dark theme
    app.setStyleSheet(qdarkstyle.load_stylesheet_pyqt5())

    player = IPTVPlayerApp()
    player.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
