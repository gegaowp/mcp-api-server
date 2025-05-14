import http.server
import socketserver
import json
import time
import jwt
import uuid
from datetime import datetime, timedelta, timezone
from email.utils import formatdate
from pysui import SuiConfig, SyncClient, SuiRpcResult
from pysui.sui import sui_txresults
from pysui.sui.sui_builders.get_builders import QueryTransactions, GetMultipleTx, GetTx
from pysui.sui.sui_types.transaction_filter import ToAddressQuery
from pysui.sui.sui_types.collections import SuiArray
from pysui.sui.sui_types.scalars import SuiString
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
                        print("[purchase_token] Attempting Sui transaction query (2-phase approach).")
                        
                        # Phase 1: Get transaction digests
                        print("[purchase_token] Phase 1: Fetching transaction digests.")
                        to_address_filter = ToAddressQuery(address=SUI_ADDRESS_TO_MONITOR)
                        query_builder_digests = QueryTransactions(
                            query=to_address_filter, 
                            cursor=None,
                            limit=10, 
                            descending_order=True
                        )
                        print(f"[purchase_token] Digest query builder params: {query_builder_digests.params}")
                        result_digests: SuiRpcResult = sui_client.execute(query_builder_digests)
                        
                        transaction_digests_list = []
                        if result_digests.is_ok() and result_digests.result_data and hasattr(result_digests.result_data, 'data') and result_digests.result_data.data:
                            transaction_digests_list = [tx.digest for tx in result_digests.result_data.data if hasattr(tx, 'digest') and tx.digest]
                            print(f"[purchase_token] Found {len(transaction_digests_list)} digests: {transaction_digests_list}")
                        else:
                            print(f"[purchase_token] Phase 1 (QueryTransactions) failed or no digests found: {result_digests.result_string if hasattr(result_digests, 'result_string') else 'No error string'}")

                        if transaction_digests_list:
                            print("[purchase_token] Phase 2: Fetching transaction details for digests.")
                            tx_options_dict = GetTx.default_options()
                            # Optionally ensure critical fields for timestamp are requested if default is not enough
                            # tx_options_dict["showInput"] = True # Already default
                            print(f"[purchase_token] Using options for GetMultipleTx: {tx_options_dict}")

                            sui_digest_array = SuiArray([SuiString(d) for d in transaction_digests_list])
                            get_multiple_tx_builder = GetMultipleTx(digests=sui_digest_array, options=tx_options_dict)
                            detailed_tx_result: SuiRpcResult = sui_client.execute(get_multiple_tx_builder)

                            if detailed_tx_result.is_ok():
                                print(f"[purchase_token] GetMultipleTx successful. Result data type: {type(detailed_tx_result.result_data)}")
                                detailed_txs_data = detailed_tx_result.result_data
                                actual_tx_list = []
                                if hasattr(detailed_txs_data, 'transactions') and isinstance(detailed_txs_data.transactions, list):
                                    actual_tx_list = detailed_txs_data.transactions
                                elif hasattr(detailed_txs_data, 'data') and isinstance(detailed_txs_data.data, list):
                                    actual_tx_list = detailed_txs_data.data # Fallback, though TxResponseArray uses .transactions
                                
                                if actual_tx_list:
                                    print(f"[purchase_token] Processing {len(actual_tx_list)} detailed transactions from GetMultipleTx.")
                                    now_utc_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
                                    ten_seconds_ago_ms = now_utc_ms - 10000
                                    print(f"[purchase_token] Current time window for check: {ten_seconds_ago_ms}ms to {now_utc_ms}ms.")
                                    for tx_block in actual_tx_list:
                                        # Accessing attributes directly from the TxResponse objects within TxResponseArray
                                        tx_digest = tx_block.digest if hasattr(tx_block, 'digest') else 'N/A'
                                        tx_timestamp_ms = tx_block.timestamp_ms if hasattr(tx_block, 'timestamp_ms') else None
                                        print(f"[purchase_token] Checking detailed tx: Digest={tx_digest}, TimestampMs={tx_timestamp_ms}")
                                        if tx_timestamp_ms and int(tx_timestamp_ms) >= ten_seconds_ago_ms:
                                            print(f"[purchase_token] Found recent transaction via GetMultipleTx: {tx_digest}")
                                            payment_received = True
                                            break
                                else:
                                    print("[purchase_token] GetMultipleTx returned OK, but no transactions found in the response list.")
                            else:
                                print(f"[purchase_token] Phase 2 (GetMultipleTx) failed: {detailed_tx_result.result_string if hasattr(detailed_tx_result, 'result_string') else 'No error string'}")
                        else:
                            print("[purchase_token] No transaction digests found in Phase 1 to fetch details for.")

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

