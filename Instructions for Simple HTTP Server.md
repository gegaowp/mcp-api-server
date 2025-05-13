# Instructions for Simple HTTP Server

This document provides instructions on how to run and test the simple Python HTTP server (`simple_server.py`).

## 1. Save the Server Code

Ensure you have the server code saved as `simple_server.py` in a directory of your choice.

```python
import http.server
import socketserver
import json
import time
from email.utils import formatdate

PORT = 8080
HOST = '0.0.0.0'

class JSONRPCRequestHandler(http.server.BaseHTTPRequestHandler):
    def do_POST(self):
        content_length = int(self.headers.get('Content-Length', 0))
        post_data = self.rfile.read(content_length)

        response_data = {}
        rpc_id = None

        try:
            json_request = json.loads(post_data.decode('utf-8'))
            method = json_request.get('method')
            params = json_request.get('params')
            rpc_id = json_request.get('id')

            if method == 'get_time':
                current_time_gmt = formatdate(timeval=None, localtime=False, usegmt=True)
                response_data = {'jsonrpc': '2.0', 'result': current_time_gmt, 'id': rpc_id}
                self.send_response(200)
            elif method == 'echo':
                response_data = {'jsonrpc': '2.0', 'result': params, 'id': rpc_id}
                self.send_response(200)
            else:
                response_data = {
                    'jsonrpc': '2.0',
                    'error': {'code': -32601, 'message': 'Method not found'},
                    'id': rpc_id
                }
                self.send_response(400)

        except json.JSONDecodeError:
            response_data = {
                'jsonrpc': '2.0',
                'error': {'code': -32700, 'message': 'Parse error'},
                'id': None
            }
            self.send_response(400)
        except Exception as e:
            response_data = {
                'jsonrpc': '2.0',
                'error': {'code': -32603, 'message': f'Internal error: {str(e)}'},
                'id': rpc_id
            }
            self.send_response(500)

        self.send_header('Content-type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps(response_data).encode('utf-8'))

    def do_GET(self):
        self.send_response(405)
        self.send_header('Allow', 'POST')
        self.end_headers()
        self.wfile.write(b'Method Not Allowed. Please use POST for JSON RPC calls.')

if __name__ == '__main__':
    with socketserver.TCPServer((HOST, PORT), JSONRPCRequestHandler) as httpd:
        print(f'Serving JSON RPC on {HOST}:{PORT}...') 
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print('\nShutting down server...')
            httpd.server_close()

```

## 2. Run the Server

Open your terminal or command prompt, navigate to the directory where you saved `simple_server.py`, and run the following command:

```bash
python3 simple_server.py
```

(If you have multiple Python versions, you might need to use `python3.11 simple_server.py` or the specific Python 3 executable in your environment).

You should see a message like:
`Serving JSON RPC on 0.0.0.0:8080...`

This means the server is running and listening for requests on port 8080.

## 3. Test the Server using `curl`

Open a new terminal window or tab to send requests to the server.

### a. Test the `get_time` function

Run the following `curl` command:

```bash
curl -X POST -H "Content-Type: application/json" -d '{"jsonrpc": "2.0", "method": "get_time", "id": 1}' http://localhost:8080
```

You should receive a JSON response similar to this (the time will be current):

```json
{"jsonrpc": "2.0", "result": "Wed, 07 May 2025 18:20:33 GMT", "id": 1}
```

### b. Test the `echo` function

Run the following `curl` command:

```bash
curl -X POST -H "Content-Type: application/json" -d '{"jsonrpc": "2.0", "method": "echo", "params": {"message": "Hello server!"}, "id": 2}' http://localhost:8080
```

You should receive a JSON response like this:

```json
{"jsonrpc": "2.0", "result": {"message": "Hello server!"}, "id": 2}
```

You can change the value of `"message"` in the `params` to test with different inputs.

## 4. Stop the Server

To stop the server, go back to the terminal window where the server is running and press `Ctrl+C`.
You should see a message like `Shutting down server...`.

