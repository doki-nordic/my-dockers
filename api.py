
from typing import Any
from handler import MyHTTPRequestHandler
from threading import Thread

def api_get_shutdown(handler: MyHTTPRequestHandler, args: dict[str, Any]):
    thread = Thread(target=lambda s: s.shutdown(), args=(handler.server, ))
    thread.daemon = True
    thread.start()
    handler.send_json_ok()

api = [
    api_get_shutdown,
]
