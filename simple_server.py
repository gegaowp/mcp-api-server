import http.server
import socketserver
import json
import time
import jwt
import uuid
from datetime import datetime, timedelta, timezone
from email.utils import formatdate
from pysui import SuiConfig, SyncClient
from pysui.sui import sui_txresults

PORT = 8080
HOST = '0.0.0.0'
# Secret key for signing JWT tokens
SECRET_KEY = "your-secret-key-for-jwt-tokens"
# Store issued tokens (in a real application, this would be in a database)
ISSUED_TOKENS = {}
# Sui Address to monitor
SUI_ADDRESS_TO_MONITOR = "0x95831b91dc0d4761530daa520274cc7bb1256b579784d7d223814c3f05c45b26"
# Sui RPC URL (replace with your desired network: devnet, testnet, mainnet)
# For example, for devnet: "https://fullnode.devnet.sui.io:443"
# For mainnet: "https://fullnode.mainnet.sui.io:443"
SUI_RPC_URL = "https://fullnode.mainnet.sui.io:443" # Defaulting to mainnet

# Initialize Sui Client
try:
    sui_config = SuiConfig.default_config() # Or use SuiConfig.from_config_file(...)
    # Attempt to use an existing environment if available, otherwise, create a new one based on RPC URL
    if sui_config.rpc_url != SUI_RPC_URL and SUI_RPC_URL:
        sui_config.rpc_url = SUI_RPC_URL
        sui_config.active_address = None # No specific address needed for querying public data
    sui_client = SyncClient(sui_config)
    print(f"Successfully connected to Sui network: {sui_config.rpc_url}")
except Exception as e:
    print(f"Error initializing Sui client: {e}")
    sui_client = None

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
                if not sui_client:
                    response_data = {
                        'jsonrpc': '2.0',
                        'error': {'code': -32000, 'message': 'Sui client not initialized'},
                        'id': rpc_id
                    }
                    self.send_response(500)
                else:
                    payment_received = False
                    try:
                        # Query for recent transactions to the monitored address
                        # We are checking for transactions TO the address
                        query = {
                            "filter": {"ToAddress": SUI_ADDRESS_TO_MONITOR},
                            # "filter": {"ChangedObject": SUI_ADDRESS_TO_MONITOR}, # Alternative: if address is an object
                            # "filter": {"FromAddress": SUI_ADDRESS_TO_MONITOR}, # Alternative: if address is sender
                        }
                        
                        # Get current time in milliseconds UTC
                        now_utc_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
                        ten_seconds_ago_ms = now_utc_ms - 10000

                        # Fetch recent transactions, newest first
                        # We fetch a small number and check their timestamps
                        # Note: pysui SDK might have direct time filtering in future versions or specific methods.
                        # For now, we filter client-side after fetching recent txs.
                        
                        tx_query_result = sui_client.execute(
                            sui_client.SUI_RPC_VERSION_QUERY_TRANSACTION_BLOCKS(
                                query=query,
                                cursor=None, # Start from the beginning
                                limit=10,    # Fetch last 10 transactions
                                descending_order=True # Newest first
                            )
                        )

                        if tx_query_result.is_ok():
                            queried_tx_blocks: list[sui_txresults.SuiTransactionBlockResponse] = tx_query_result.result_data.data
                            for tx_block in queried_tx_blocks:
                                if tx_block.timestamp_ms and int(tx_block.timestamp_ms) >= ten_seconds_ago_ms:
                                    # Further check if this specific transaction is relevant (e.g. amount, type) if needed
                                    # For now, any recent transaction to the address is considered payment
                                    print(f"Found recent transaction: {tx_block.digest} at {tx_block.timestamp_ms}")
                                    payment_received = True
                                    break 
                        else:
                            print(f"Error querying Sui transactions: {tx_query_result.result_string}")


                    except Exception as e:
                        print(f"Error during Sui transaction check: {str(e)}")
                        # Potentially send an internal error, or proceed to "payment not received"
                        # For now, we assume payment not received if any error occurs here

                    if payment_received:
                        # Generate a new JWT token
                        token_id = str(uuid.uuid4())
                        expiration = datetime.utcnow() + timedelta(hours=1) # utcnow is deprecated, use datetime.now(timezone.utc)
                        
                        payload = {
                            'token_id': token_id,
                            'exp': expiration # JWT library handles datetime objects
                        }
                        
                        # Create the JWT token
                        new_token = jwt.encode(payload, SECRET_KEY, algorithm='HS256')
                        
                        # Store token info (in a real app, use a database)
                        ISSUED_TOKENS[token_id] = {
                            'created_at': datetime.now(timezone.utc),
                            'expires_at': expiration
                        }
                        
                        response_data = {'jsonrpc': '2.0', 'result': new_token, 'id': rpc_id}
                        self.send_response(200)
                    else:
                        response_data = {
                            'jsonrpc': '2.0',
                            'error': {'code': -32001, 'message': 'Payment not received'},
                            'id': rpc_id
                        }
                        self.send_response(402) # Payment Required
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
                        
                        # Check if token has expired based on our stored 'expires_at'
                        # Corrected to use timezone-aware datetime
                        if ISSUED_TOKENS[token_id]['expires_at'].replace(tzinfo=timezone.utc) < datetime.now(timezone.utc):
                            ISSUED_TOKENS.pop(token_id) # Clean up expired token from memory
                            raise jwt.ExpiredSignatureError("Token has expired based on server record")

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

