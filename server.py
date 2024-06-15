
import webbrowser
from http.server import HTTPServer
from api import api
from auth import auth_key
from handler import MyHTTPRequestHandler

def main():
    with HTTPServer(('localhost', 8185), MyHTTPRequestHandler) as server:
        server._api = api
        print(f'URL: http://localhost:{server.server_port}/#_auth_{auth_key}')
        webbrowser.open(f'http://localhost:{server.server_port}/#_auth_{auth_key}')
        server.serve_forever()

if __name__ == '__main__':
    exit(main() or 0)
