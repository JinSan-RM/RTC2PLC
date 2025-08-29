import logging
import logging.handlers
import queue
import atexit
from functools import lru_cache

@lru_cache(maxsize=1)
def setup_logger():
    log_queue = queue.Queue()

    queue_handler = logging.handlers.QueueHandler(log_queue)
    root_logger = logging.getLogger()
    root_logger.addHandler(queue_handler)
    root_logger.setLevel(logging.INFO)

    console_handler = logging.StreamHandler()
    file_handler = logging.handlers.RotatingFileHandler("app.log", maxBytes=1024*1024, backupCount=3)
    formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
    console_handler.setFormatter(formatter)

    listener = logging.handlers.QueueListener(log_queue, console_handler, file_handler)
    listener.start()

    atexit.register(listener.stop)

    return listener