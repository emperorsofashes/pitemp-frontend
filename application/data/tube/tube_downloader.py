import hashlib
import logging
import os
import subprocess
from typing import Optional


LOG = logging.getLogger(__name__)


class TubeDownloader:
    def __init__(self, output_dir="/tmp/downloads"):
        self.output_dir = output_dir
        os.makedirs(self.output_dir, exist_ok=True)

    def _get_unique_subdir(self, url):
        """
        Generate a unique subdirectory based on the hash of the YouTube URL.
        """
        hash_object = hashlib.md5(url.encode())
        unique_subdir = os.path.join(self.output_dir, hash_object.hexdigest())
        os.makedirs(unique_subdir, exist_ok=True)
        return unique_subdir

    def _clear_tmp_directory(self) -> None:
        for root, dirs, files in os.walk(self.output_dir):
            for file in files:
                if file.endswith(".mp3"):
                    file_path = os.path.join(root, file)
                    try:
                        os.remove(file_path)
                        LOG.info(f"Deleted MP3 file: {file_path}")
                    except Exception as e:
                        LOG.error(f"Error deleting file {file_path}: {e}")

    def download_mp3(self, url: str, bitrate: str, audio_format: str = "mp3") -> Optional[str]:
        unique_dir = self._get_unique_subdir(url)
        output_template = os.path.join(unique_dir, "%(title)s.%(ext)s")
        command = [
            "yt-dlp",
            "--extract-audio",
            "--audio-format", audio_format,
            "--audio-quality", f"{bitrate}K",
            "--output", output_template,
            url,
        ]

        self._clear_tmp_directory()
        LOG.info(f"Beginning download and conversion of {url}...")

        try:
            subprocess.run(command, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            LOG.info(f"Download for {url} and conversion completed successfully.")

            # Find the file in the output directory
            for file in os.listdir(unique_dir):
                if file.endswith(f".{audio_format}"):
                    return os.path.join(unique_dir, file)
        except subprocess.CalledProcessError as e:
            LOG.exception("An error occurred during download or conversion")
            raise

        return None
