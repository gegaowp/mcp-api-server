# Simple JSON-RPC Server

A lightweight JSON-RPC 2.0 server implemented in Python using the standard library.

## Features

- Simple HTTP server implementation
- JSON-RPC 2.0 protocol support
- Supports `get_time` and `echo` methods
- No external dependencies

## Installation

Clone this repository:

```bash
git clone https://github.com/yourusername/json-rpc-server.git
cd json-rpc-server
```

No additional installation is required as this server only uses Python's standard library.

## Usage

### Starting the Server

Run the server with Python 3:

```bash
python3 simple_server.py
```

The server will start listening on `0.0.0.0:8080`.

### Available RPC Methods

#### get_time

Returns the current time in GMT format.

Example request:
```bash
curl -X POST -H "Content-Type: application/json" -d '{"jsonrpc": "2.0", "method": "get_time", "id": 1}' http://localhost:8080
```

#### echo

Returns the input parameters.

Example request:
```bash
curl -X POST -H "Content-Type: application/json" -d '{"jsonrpc": "2.0", "method": "echo", "params": {"message": "Hello server!"}, "id": 2}' http://localhost:8080
```

## File Structure

- `simple_server.py` - The main server implementation
- `Instructions for Simple HTTP Server.md` - Detailed instructions for running and testing the server

## License

[MIT](https://choosealicense.com/licenses/mit/) 