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
from pysui.sui.sui_builders.get_builders import QueryTransactions
from pysui.sui.sui_types.collections import SuiMap
import traceback

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
                print("[purchase_token] Entered method.")
                if not sui_client:
                    print("[purchase_token] Sui client not initialized.")
                    response_data = {
                        'jsonrpc': '2.0',
                        'error': {'code': -32000, 'message': 'Sui client not initialized'},
                        'id': rpc_id
                    }
                    self.send_response(500)
                else:
                    print("[purchase_token] Sui client initialized. Proceeding with payment check.")
                    payment_received = False
                    try:
                        print("[purchase_token] Attempting Sui transaction query.")
                        # Query for recent transactions to the monitored address
                        # We are checking for transactions TO the address
                        filter_dict = {"ToAddress": SUI_ADDRESS_TO_MONITOR}
                        # query_map_for_builder = SuiMap(key="filter", value=filter_dict)
                        # The QueryTransactions builder expects the query argument to be a SuiMap
                        # representing the entire query structure, not just the filter value.
                        # The SuiMap itself should represent the {'filter': {'ToAddress': '...'}}
                        # However, the QueryTransactions builder definition is: __init__(*, query: SuiMap, ...)
                        # This implies the `query` parameter to QueryTransactions should be the SuiMap itself.

                        # Our current `query` variable in the calling scope is `query = {"filter": {"ToAddress": SUI_ADDRESS_TO_MONITOR}}`
                        # The QueryTransactions builder seems to expect this entire structure as the `query` argument,
                        # and that argument must be of type SuiMap.
                        # Given SuiMap(key, value), it seems SuiMap is for simple key-value pairs, not complex nested dicts directly.
                        # This implies that the `pysui` library might handle the direct python dict for the `query` parameter
                        # in QueryTransactions, or there's a different way to construct complex SuiMap objects.

                        # Let's try passing the Python dictionary directly to QueryTransactions,
                        # as the builder might handle the conversion to the appropriate SuiMap structure internally if needed,
                        # or the type hint `SuiMap` for the builder is a general catch-all for map-like structures it accepts.
                        # The error was specifically about SuiMap constructor, not QueryTransactions constructor directly.

                        rpc_query_structure = {
                            "filter": {"ToAddress": SUI_ADDRESS_TO_MONITOR},
                            "options": None # Explicitly setting options to None or a valid SuiMap if needed by API
                        }

                        # Instantiate the QueryTransactions builder
                        query_builder = QueryTransactions(
                            query=rpc_query_structure, # Passing Python dict directly, builder might handle it.
                            cursor=None,    # Start from the beginning
                            limit=10,       # Fetch last 10 transactions
                            descending_order=True # Newest first
                        )
                        print(f"[purchase_token] Constructed QueryTransactions builder with params: {query_builder.params}") # DBG

                        tx_query_result = sui_client.execute(query_builder)
                        
                        print(f"[purchase_token] Sui query raw result object: {tx_query_result}") # DBG
                        if hasattr(tx_query_result, 'result_string'):
                             print(f"[purchase_token] Sui query result_string: {tx_query_result.result_string}")
                        if hasattr(tx_query_result, 'result_data'):
                             print(f"[purchase_token] Sui query result_data: {tx_query_result.result_data}")


                        if tx_query_result.is_ok():
                            print("[purchase_token] Sui query OK.")
                            queried_tx_blocks: list[sui_txresults.SuiTransactionBlockResponse] = tx_query_result.result_data.data
                            print(f"[purchase_token] Found {len(queried_tx_blocks)} transaction blocks.")
                            for i, tx_block in enumerate(queried_tx_blocks):
                                print(f"[purchase_token] Checking tx {i+1}: digest={tx_block.digest if hasattr(tx_block, 'digest') else 'N/A'}, timestamp_ms={tx_block.timestamp_ms if hasattr(tx_block, 'timestamp_ms') else 'N/A'}")
                                if hasattr(tx_block, 'timestamp_ms') and tx_block.timestamp_ms and int(tx_block.timestamp_ms) >= ten_seconds_ago_ms:
                                    # Further check if this specific transaction is relevant (e.g. amount, type) if needed
                                    # For now, any recent transaction to the address is considered payment
                                    print(f"[purchase_token] Found recent transaction: {tx_block.digest if hasattr(tx_block, 'digest') else 'N/A'}")
                                    payment_received = True
                                    break 
                        else:
                            print(f"[purchase_token] Error querying Sui transactions. Result status: {'OK' if tx_query_result.is_ok() else 'Error'}. Result string: {tx_query_result.result_string if hasattr(tx_query_result, 'result_string') else 'N/A'}")


                    except Exception as e_sui:
                        print("[purchase_token] --- Exception during Sui transaction check ---")
                        traceback.print_exc()
                        print("---------------------------------------------------------")
                        # payment_received remains False

                    print(f"[purchase_token] Payment received status: {payment_received}")
                    if payment_received:
                        print("[purchase_token] Payment received. Generating token.")
                        # Generate a new JWT token
                        token_id = str(uuid.uuid4())
                        expiration = datetime.now(timezone.utc) + timedelta(hours=1)
                        
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
                        print("[purchase_token] Payment not received. Returning 402.")
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
                        # Ensure ISSUED_TOKENS[token_id]['expires_at'] is timezone-aware if it comes from old data
                        expires_at_val = ISSUED_TOKENS[token_id]['expires_at']
                        if not expires_at_val.tzinfo:
                           expires_at_val = expires_at_val.replace(tzinfo=timezone.utc)

                        if expires_at_val < datetime.now(timezone.utc):
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
            print("---Outer Exception Caught ( منجر به 500) ---")
            traceback.print_exc()
            print("--------------------------------------------")
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

