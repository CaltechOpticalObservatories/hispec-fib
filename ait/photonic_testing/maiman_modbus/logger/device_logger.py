import logging
import logging.handlers
import threading
from queue import Queue
from typing import Optional
from dataclasses import dataclass
from datetime import datetime

@dataclass
class LogEvent:
    level: str
    message: str
    event_data: Optional[dict] = None

class Logger:
    def __init__(self, log_file: str, max_file_size: int = 1024*100, backup_count: int = 5, enable_logging: bool = True):
        """Initialize the Logger class."""
        self.log_file = log_file
        self.enable_logging = enable_logging
        self.max_file_size = max_file_size
        self.backup_count = backup_count
        self.log_queue = Queue()

        self.logger = logging.getLogger('DeviceLogger')

        if not self.logger.hasHandlers():
            self.logger.setLevel(logging.DEBUG)

            # Log format
            log_format = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')

            # File handler with UTF-8 encoding and append mode
            file_handler = logging.handlers.RotatingFileHandler(
                self.log_file,
                maxBytes=self.max_file_size,
                backupCount=self.backup_count,
                mode='a',
                encoding='utf-8'  # Ensure UTF-8 encoding
            )
            file_handler.setFormatter(log_format)
            self.logger.addHandler(file_handler)

        if self.enable_logging:
            self.thread = threading.Thread(target=self._process_log_queue)
            self.thread.daemon = True
            self.thread.start()

        # Add separator and timestamp at the start of each run
        self._add_log_separator()

    def _add_log_separator(self):
        """Add a separator and timestamp header between runs."""
        self.logger.info("\n" + "=" * 50)
        self.logger.info(f"New Run Started at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        self.logger.info("=" * 50)

    def _process_log_queue(self):
        """Process log events asynchronously."""
        while True:
            log_event = self.log_queue.get()
            if log_event is None:  # Stop signal
                break

            message = self._ensure_utf8(log_event.message)

            if log_event.level == 'INFO':
                self.logger.info(message, extra=log_event.event_data)
            elif log_event.level == 'ERROR':
                self.logger.error(message, extra=log_event.event_data)
            elif log_event.level == 'WARNING':
                self.logger.warning(message, extra=log_event.event_data)
            elif log_event.level == 'DEBUG':
                self.logger.debug(message, extra=log_event.event_data)

    def _ensure_utf8(self, message: str) -> str:
        """Ensure message is encoded as UTF-8."""
        try:
            return message.encode('utf-8').decode('utf-8')
        except UnicodeEncodeError:
            return message.encode('ascii', 'ignore').decode('ascii')

    def stop(self):
        """Stop the logging thread."""
        self.log_queue.put(None)
        self.thread.join()

    def start(self):
        """Restart logging if it was stopped."""
        if not self.thread.is_alive():
            self.thread = threading.Thread(target=self._process_log_queue)
            self.thread.daemon = True
            self.thread.start()

    def path(self, new_path: str):
        """Update the log file path."""
        self.log_file = new_path
        for handler in self.logger.handlers:
            if isinstance(handler, logging.FileHandler):
                handler.close()
                self.logger.removeHandler(handler)

        file_handler = logging.handlers.RotatingFileHandler(
            self.log_file,
            maxBytes=self.max_file_size,
            backupCount=self.backup_count,
            mode='a',
            encoding='utf-8'  # Ensure UTF-8 encoding
        )
        file_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
        self.logger.addHandler(file_handler)

    def eventRecording(self, event: LogEvent):
        """Record an event."""
        if self.enable_logging:
            self.log_queue.put(event)

    def errorRecording(self, message: str, error_code: Optional[int] = None):
        """Record an error event."""
        if self.enable_logging:
            self.log_queue.put(LogEvent(level='ERROR', message=message, event_data={'error_code': error_code}))


class DeviceError(Exception):
    def __init__(self, code: str, description: str):
        super().__init__(f"Error [{code}]: {description}")
        self.code = code
        self.description = description