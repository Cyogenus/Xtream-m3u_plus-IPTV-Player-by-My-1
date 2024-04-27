import sys
import requests
import re
import threading
import subprocess
from PyQt5 import QtWidgets, QtGui, QtCore
from PyQt5.QtWidgets import QFileDialog
import configparser

class M3UPlayer(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("IPTV M3U Player by My-1")
        self.setMinimumSize(650, 400) 

        central_widget = QtWidgets.QWidget()
        self.setCentralWidget(central_widget)
        layout = QtWidgets.QVBoxLayout(central_widget)

        url_layout = QtWidgets.QHBoxLayout()
        layout.addLayout(url_layout)

        url_label = QtWidgets.QLabel("URL:")
        url_layout.addWidget(url_label)

        self.url_entry = QtWidgets.QLineEdit()
        url_layout.addWidget(self.url_entry)

        button_layout = QtWidgets.QHBoxLayout()
        layout.addLayout(button_layout)

        self.clear_button = QtWidgets.QPushButton("Clear")
        button_layout.addWidget(self.clear_button)

        self.load_button = QtWidgets.QPushButton("Load Playlist")
        button_layout.addWidget(self.load_button)

        self.channel_list = QtWidgets.QListWidget()
        self.channel_list.setFont(QtGui.QFont("TkDefaultFont", 12))
        layout.addWidget(self.channel_list)

        self.status_label = QtWidgets.QLabel("Status: Idle")
        self.status_label.setAlignment(QtCore.Qt.AlignCenter)
        self.status_bar = self.statusBar()
        self.status_bar.addWidget(self.status_label)

        self.entries = []
        self.groups = []
        self.current_group = ""

        self.external_player_command = ""
        self.load_external_player_command()

        self.clear_button.clicked.connect(self.clear_url)
        self.load_button.clicked.connect(self.load_playlist)
        self.channel_list.itemDoubleClicked.connect(self.load_channels)

        # Create external player button
        self.external_player_button = QtWidgets.QPushButton("Choose External Player")
        layout.addWidget(self.external_player_button)

        self.external_player_button.clicked.connect(self.choose_external_player)

        # Load external player command from INI file
        self.load_external_player_command()

    def closeEvent(self, event):
        event.accept()

    def clear_url(self):
        self.url_entry.clear()

    def load_playlist(self):
        self.status_label.setText("Status: Idle")
        url = self.url_entry.text()
        thread = threading.Thread(target=self.parse, args=(url,))
        thread.start()
        self.status_label.setText("Status: Downloading Playlist")
        self.status_label.setStyleSheet("color: purple; font-weight: bold;")

        # Clear the channel list
        self.channel_list.clear()

        # Reset the current group
        self.current_group = ""



    def load_channels(self, item):
        selected_item = self.channel_list.currentItem()
        if selected_item.text() == "Go Back" and self.current_group:
            self.current_group = ""
            self.update_channel_list()
        elif selected_item.text() in self.groups and not self.current_group:
            self.current_group = selected_item.text()
            self.channel_list.clear()
            self.channel_list.addItem("Go Back")

            for entry in self.entries:
                if entry["group_title"] == self.current_group:
                    self.channel_list.addItem(entry["tvg_name"])
        else:
            selected_entry = self.entries[self.channel_list.currentRow()]
            channel_name = selected_entry["tvg_name"]
            print("Selected Channel:", channel_name)
            self.play_selected_url()

    def parse(self, url):
        response = requests.get(url)

        if response.status_code != 200:
            print("Error: Failed to retrieve the M3U file")
            self.status_label.setText("Status: Playlist Error")# Set the status label to indicate playlist error
            self.status_label.setStyleSheet("color: red; font-weight: bold;")
            return

        lines = response.text.split("\n")
        self.entries = []
        self.groups = []

        for line in lines:
            line = line.strip()
            if line.startswith("#EXTINF:-1"):
                info = re.sub(r'^#EXTINF:-1,\s*', '', line)

                pattern = r'tvg-id="(.*?)" tvg-name="(.*?)" tvg-logo="(.*?)" group-title="(.*?)"'
                match = re.search(pattern, info)

                if match:
                    tvg_id = match.group(1)
                    tvg_name = match.group(2)
                    tvg_logo = match.group(3)
                    group_title = match.group(4)
                else:
                    group_title = info
                    tvg_id = ""
                    tvg_name = ""
                    tvg_logo = ""

                entry = {
                    "tvg_id": tvg_id,
                    "tvg_name": tvg_name,
                    "tvg_logo": tvg_logo,
                    "group_title": group_title,
                    "url": ""
                }
                self.entries.append(entry)

                if group_title not in self.groups:
                    self.groups.append(group_title)
            elif line and not line.startswith("#"):
                if self.entries:
                    self.entries[-1]["url"] = line

        QtCore.QTimer.singleShot(0, self.update_channel_list)
        self.status_label.setText("Status: Playlist Downloaded")
        self.status_label.setStyleSheet("color: green; font-weight: bold;")

    def play_selected_url(self):
        selected_item = self.channel_list.currentItem()
        if selected_item and selected_item.text() == "Go Back":
            self.go_back()
        else:
            selected_entry = self.find_entry_by_name(selected_item.text())
            if selected_entry:
                url = selected_entry["url"]
                if url:
                    self.play(url)

    def find_entry_by_name(self, name):
        for entry in self.entries:
            if entry["tvg_name"] == name:
                return entry
        return None

    def go_back(self):
        if self.current_group:
            self.current_group = ""
            self.update_channel_list()

    def update_channel_list(self):
        self.channel_list.clear()
        if self.current_group:
            self.channel_list.addItem("Go Back")
            for entry in self.entries:
                if entry["group_title"] == self.current_group:
                    self.channel_list.addItem(entry["tvg_name"])
        else:
            for group in self.groups:
                self.channel_list.addItem(group)

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

    def play(self, url):
        if self.external_player_command:
            subprocess.Popen([self.external_player_command, url])
        else:
            print("No external player command specified.")

def main():
    app = QtWidgets.QApplication(sys.argv)
    player = M3UPlayer()
    player.show()
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()
