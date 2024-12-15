import hashlib
import logging
import os
import shutil
import subprocess
from typing import Optional

LOG = logging.getLogger(__name__)
AUDIO_FORMAT = "mp3"


class TubeDownloader:
    def __init__(self, output_dir="/tmp/downloads"):
        self.output_dir = output_dir
        os.makedirs(self.output_dir, exist_ok=True)
        self.completed = set()
        self.started = set()

    def get_unique_subdir(self, url) -> str:
        """
        Generate a unique subdirectory based on the hash of the YouTube URL.
        """
        hash_object = hashlib.md5(url.encode())
        unique_subdir = os.path.join(self.output_dir, hash_object.hexdigest())
        os.makedirs(unique_subdir, exist_ok=True)
        return unique_subdir

    def _clear_tmp_directory(self) -> None:
        self.completed.clear()
        for item in os.listdir(self.output_dir):
            item_path = os.path.join(self.output_dir, item)
            if os.path.isdir(item_path):  # Check if it's a directory
                shutil.rmtree(item_path)  # Recursively delete the directory

    def download_mp3(self, url: str, bitrate: str):
        unique_dir = self.get_unique_subdir(url)
        output_template = os.path.join(unique_dir, "%(title)s.%(ext)s")
        command = [
            "yt-dlp",
            "--extract-audio",
            "--audio-format", AUDIO_FORMAT,
            "--audio-quality", f"{bitrate}K",
            "--output", output_template,
            url,
        ]

        self._clear_tmp_directory()
        LOG.info(f"Beginning download and conversion of {url}...")

        try:
            subprocess.run(command, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            self.completed.add(unique_dir)
            LOG.info(f"Download for {url} and conversion completed successfully.")
        except subprocess.CalledProcessError as e:
            LOG.error(f"yt-dlp command failed with exit code {e.returncode}")
            LOG.error(f"Error output: {e.stderr.decode('utf-8')}")
            raise

    def get_mp3_if_ready(self, unique_dir: str) -> Optional[str]:
        if unique_dir not in self.started:
            raise ValueError("ID not found")

        if unique_dir not in self.completed:
            return None

        for file in os.listdir(unique_dir):
            if file.endswith(f".{AUDIO_FORMAT}"):
                return os.path.join(unique_dir, file)
        return None
