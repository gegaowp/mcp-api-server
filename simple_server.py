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
            original_params = json_request.get('params') # Store original params
            rpc_id = json_request.get('id')
            
            token_from_body = json_request.get('token') # Attempt to get token from body field
            effective_params = original_params # Params to be used by methods

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
                token_to_validate = token_from_body
                
                # If token not in body, try to extract from original_params[0]
                if not token_to_validate and isinstance(original_params, list) and len(original_params) > 0:
                    token_to_validate = original_params[0] # Assume this is the token
                    
                    # Adjust effective_params for the actual method logic
                    if method == 'echo':
                        effective_params = original_params[1:] if len(original_params) > 1 else []
                    else: # for get_time
                        effective_params = []

                if not token_to_validate:
                    response_data = {
                        'jsonrpc': '2.0',
                        'error': {'code': -32600, 'message': 'No access: Missing token'},
                        'id': rpc_id
                    }
                    self.send_response(401)
                else:
                    try:
                        # Decode and verify the token_to_validate
                        payload = jwt.decode(token_to_validate, SECRET_KEY, algorithms=['HS256'])
                        token_id = payload.get('token_id')
                        
                        if token_id not in ISSUED_TOKENS:
                            raise jwt.InvalidTokenError("Token not found in issued tokens")
                        
                        if method == 'get_time':
                            current_time_gmt = formatdate(timeval=None, localtime=False, usegmt=True)
                            response_data = {'jsonrpc': '2.0', 'result': current_time_gmt, 'id': rpc_id}
                            self.send_response(200)
                        elif method == 'echo':
                            # Use effective_params for echo logic
                            if isinstance(effective_params, list) and len(effective_params) > 0:
                                modified_response = f"Dear User, {effective_params[0]}"
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

