import sys
from pysui import SuiConfig, SyncClient, SuiRpcResult
from pysui.sui.sui_builders.get_builders import QueryTransactions, GetMultipleTx, GetTx
from pysui.sui.sui_types.collections import SuiArray, SuiMap # Required for query structure if complex
# from pysui.sui.sui_txresults import SuiTransactionBlockResponse # For type hinting results - Removed to avoid import error if not essential for test logic
from pysui.sui import sui_txresults # Keep this for potential attribute access if needed, or if it defines response structures implicitly
from pysui.sui.sui_types.transaction_filter import ToAddressQuery, FromAddressQuery # Specific filter classes
from pysui.sui.sui_types.scalars import SuiString # For digest list
import traceback

# Address to monitor (same as in simple_server.py)
SUI_ADDRESS_TO_TEST = "0x95831b91dc0d4761530daa520274cc7bb1256b579784d7d223814c3f05c45b26"
# Mainnet RPC URL (same as in simple_server.py)
SUI_RPC_URL = "https://fullnode.mainnet.sui.io:443"

def run_sui_query_test():
    """
    Tests querying the Sui blockchain for transactions involving a specific address.
    Passes if at least one transaction is found with a non-zero timestamp.
    """
    print(f"--- Starting Sui Query Test for address: {SUI_ADDRESS_TO_TEST} ---")
    sui_client = None
    try:
        print(f"Attempting to initialize SuiConfig for RPC: {SUI_RPC_URL}")
        cfg = SuiConfig.default_config()
        if cfg.rpc_url != SUI_RPC_URL :
            print(f"Default RPC URL {cfg.rpc_url} differs, setting to {SUI_RPC_URL}")
            cfg.rpc_url = SUI_RPC_URL
            cfg.active_address = None # Not strictly needed for public queries

        print("Initializing SyncClient...")
        sui_client = SyncClient(cfg)
        print(f"Successfully connected to Sui network: {cfg.rpc_url}")

        found_transaction_with_timestamp = False
        checked_filters = []
        transaction_digests = []

        # Phase 1: Get transaction digests using QueryTransactions
        print("\n--- Phase 1: Fetching transaction digests ---")
        
        # Try ToAddress filter first
        to_address_filter = ToAddressQuery(address=SUI_ADDRESS_TO_TEST)
        checked_filters.append(f"ToAddress: {SUI_ADDRESS_TO_TEST}")
        print(f"Attempting QueryTransactions with ToAddressQuery filter: {to_address_filter.filter}")
        query_builder_digests_to = QueryTransactions(
            query=to_address_filter,
            limit=5, # Get a few recent digests
            descending_order=True
        )
        result_digests_to: SuiRpcResult = sui_client.execute(query_builder_digests_to)

        if result_digests_to.is_ok() and result_digests_to.result_data and result_digests_to.result_data.data:
            digests = [tx.digest for tx in result_digests_to.result_data.data if hasattr(tx, 'digest') and tx.digest]
            if digests:
                transaction_digests.extend(digests)
                print(f"Found {len(digests)} digests with ToAddress filter.")
        else:
            print(f"QueryTransactions (ToAddress) failed or returned no data: {result_digests_to.result_string}")

        # If no digests from ToAddress, try FromAddress
        if not transaction_digests:
            from_address_filter = FromAddressQuery(address=SUI_ADDRESS_TO_TEST)
            checked_filters.append(f"FromAddress: {SUI_ADDRESS_TO_TEST}")
            print(f"Attempting QueryTransactions with FromAddressQuery filter: {from_address_filter.filter}")
            query_builder_digests_from = QueryTransactions(
                query=from_address_filter,
                limit=5,
                descending_order=True
            )
            result_digests_from: SuiRpcResult = sui_client.execute(query_builder_digests_from)
            if result_digests_from.is_ok() and result_digests_from.result_data and result_digests_from.result_data.data:
                digests = [tx.digest for tx in result_digests_from.result_data.data if hasattr(tx, 'digest') and tx.digest]
                if digests:
                    transaction_digests.extend(digests)
                    print(f"Found {len(digests)} digests with FromAddress filter.")
            else:
                print(f"QueryTransactions (FromAddress) failed or returned no data: {result_digests_from.result_string}")
        
        if not transaction_digests:
            print("FAILURE: No transaction digests found with any filter.")
            return False
        
        print(f"Transaction digests to fetch details for: {transaction_digests}")

        # Phase 2: Get transaction details (including timestamp) using GetMultipleTx
        print("\n--- Phase 2: Fetching transaction details with GetMultipleTx ---")
        
        # Use default options from GetTx, which should be reasonably complete
        # or specify options that guarantee timestamp inclusion, e.g., showInput or showEffects.
        tx_options_dict = GetTx.default_options() # Get default options dictionary
        # Ensure at least one of these is true if default_options is too minimal
        # tx_options_dict["showInput"] = True 
        # tx_options_dict["showEffects"] = True
        print(f"Using options for GetMultipleTx: {tx_options_dict}") # Print the dict directly

        # Convert list of digest strings to SuiArray of SuiString
        sui_digest_array = SuiArray([SuiString(d) for d in transaction_digests])

        # Pass the dictionary directly; the builder should handle it or its type hint for SuiMap is broad.
        # If this fails, the next step is to see how SuiMap is made from a dict if not key,value.
        get_multiple_tx_builder = GetMultipleTx(digests=sui_digest_array, options=tx_options_dict)
        detailed_tx_result: SuiRpcResult = sui_client.execute(get_multiple_tx_builder)

        if detailed_tx_result.is_ok():
            print(f"GetMultipleTx successful. Result data type: {type(detailed_tx_result.result_data)}") # DBG
            print(f"GetMultipleTx successful. Result data content: {detailed_tx_result.result_data}") # DBG
            
            # TxResponseArray likely has a .transactions or .data attribute containing the list
            actual_tx_list = []
            if hasattr(detailed_tx_result.result_data, 'transactions') and isinstance(detailed_tx_result.result_data.transactions, list):
                actual_tx_list = detailed_tx_result.result_data.transactions
            elif hasattr(detailed_tx_result.result_data, 'data') and isinstance(detailed_tx_result.result_data.data, list):
                 actual_tx_list = detailed_tx_result.result_data.data
            else:
                print("Could not find a list of transactions in GetMultipleTx result_data.")

            if actual_tx_list:
                print(f"Processing {len(actual_tx_list)} detailed transactions.") # DBG
                for i, tx_detail in enumerate(actual_tx_list):
                    digest = tx_detail.digest if hasattr(tx_detail, 'digest') else f'unknown_digest_{i}'
                    timestamp = tx_detail.timestamp_ms if hasattr(tx_detail, 'timestamp_ms') else 'N/A'
                    print(f"  Tx {i+1}: Digest={digest}, TimestampMs={timestamp}")
                    if hasattr(tx_detail, 'timestamp_ms') and tx_detail.timestamp_ms and int(tx_detail.timestamp_ms) > 0:
                        found_transaction_with_timestamp = True
                        # We only need one for the test to pass with a real timestamp
                        # break 
            else:
                print(f"GetMultipleTx returned ok, but no transactions list found in result_data or it was empty.")

        else:
            print(f"GetMultipleTx failed: {detailed_tx_result.result_string}")

        if found_transaction_with_timestamp:
            print(f"SUCCESS: Found at least one transaction with a non-zero timestamp for address {SUI_ADDRESS_TO_TEST}.")
            return True
        else:
            print(f"FAILURE: No transactions found with a non-zero timestamp for {SUI_ADDRESS_TO_TEST} using GetMultipleTx.")
            return False

    except Exception as e:
        print(f"An error occurred during the test: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        if sui_client:
            print("Closing Sui client.")
            sui_client.close()
        print("--- Sui Query Test Finished ---")

if __name__ == "__main__":
    if run_sui_query_test():
        sys.exit(0) # Exit with success code
    else:
        sys.exit(1) # Exit with failure code 