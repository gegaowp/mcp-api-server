import http.server
import socketserver
import json
import time
import jwt
import uuid
from datetime import datetime, timedelta
from email.utils import formatdate

PORT = 8080
HOST = '0.0.0.0'
# Secret key for signing JWT tokens
SECRET_KEY = "your-secret-key-for-jwt-tokens"
# Store issued tokens (in a real application, this would be in a database)
ISSUED_TOKENS = {}

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
            token = json_request.get('token')

            if method == 'purchase_token':
                # Generate a new JWT token
                token_id = str(uuid.uuid4())
                expiration = datetime.utcnow() + timedelta(hours=1)
                
                payload = {
                    'token_id': token_id,
                    'exp': expiration
                }
                
                # Create the JWT token
                new_token = jwt.encode(payload, SECRET_KEY, algorithm='HS256')
                
                # Store token info (in a real app, use a database)
                ISSUED_TOKENS[token_id] = {
                    'created_at': datetime.utcnow(),
                    'expires_at': expiration
                }
                
                response_data = {'jsonrpc': '2.0', 'result': new_token, 'id': rpc_id}
                self.send_response(200)
            elif method in ['get_time', 'echo']:
                # Verify token for protected methods
                if not token:
                    response_data = {
                        'jsonrpc': '2.0',
                        'error': {'code': -32600, 'message': 'No access: Missing token'},
                        'id': rpc_id
                    }
                    self.send_response(401)
                else:
                    try:
                        # Decode and verify the token
                        payload = jwt.decode(token, SECRET_KEY, algorithms=['HS256'])
                        token_id = payload.get('token_id')
                        
                        # Check if token is in our store
                        if token_id not in ISSUED_TOKENS:
                            raise jwt.InvalidTokenError("Token not found in issued tokens")
                        
                        # Process the method now that token is verified
                        if method == 'get_time':
                            current_time_gmt = formatdate(timeval=None, localtime=False, usegmt=True)
                            response_data = {'jsonrpc': '2.0', 'result': current_time_gmt, 'id': rpc_id}
                            self.send_response(200)
                        elif method == 'echo':
                            # Add "Dear User" before the message
                            if isinstance(params, list) and len(params) > 0:
                                modified_response = f"Dear User, {params[0]}"
                            else:
                                modified_response = "Dear User"
                            response_data = {'jsonrpc': '2.0', 'result': modified_response, 'id': rpc_id}
                            self.send_response(200)
                            
                    except jwt.ExpiredSignatureError:
                        response_data = {
                            'jsonrpc': '2.0',
                            'error': {'code': -32600, 'message': 'No access: Token expired'},
                            'id': rpc_id
                        }
                        self.send_response(401)
                    except jwt.InvalidTokenError:
                        response_data = {
                            'jsonrpc': '2.0', 
                            'error': {'code': -32600, 'message': 'No access: Invalid token'},
                            'id': rpc_id
                        }
                        self.send_response(401)
            else:
                response_data = {
                    'jsonrpc': '2.0',
                    'error': {'code': -32601, 'message': 'Method not found'},
                    'id': rpc_id
                }
                self.send_response(400) # Bad Request or 501 Not Implemented for method not found

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

