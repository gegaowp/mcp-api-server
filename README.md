# Simple MCP API Server

A lightweight MCP API JSON-RPC 2.0 server implemented in Python using the standard library with JWT authentication.

## Features

- Simple HTTP server implementation
- JSON-RPC 2.0 protocol support
- JWT token-based authentication
- Supports `get_time`, `echo`, and `purchase_token` methods
- No external dependencies (except PyJWT)

## Installation

Clone this repository:

```bash
git clone https://github.com/yourusername/json-rpc-server.git
cd json-rpc-server
```

Install the required PyJWT package:

```bash
pip install pyjwt
```

## Usage

### Starting the Server

Run the server with Python 3:

```bash
python3 simple_server.py
```

The server will start listening on `0.0.0.0:8080`.

### Available RPC Methods

#### purchase_token

Generates and returns a new JWT token that expires after 1 hour.

Example request:
```bash
curl -X POST -H "Content-Type: application/json" -d '{"jsonrpc": "2.0", "method": "purchase_token", "id": 1}' http://localhost:8080
```

#### get_time

Returns the current time in GMT format. Requires a valid JWT token.

Example request:
```bash
curl -X POST -H "Content-Type: application/json" -d '{"jsonrpc": "2.0", "method": "get_time", "token": "your-jwt-token", "id": 2}' http://localhost:8080
```

Alternatively, you can provide the token as the first parameter:
```bash
curl -X POST -H "Content-Type: application/json" -d '{"jsonrpc": "2.0", "method": "get_time", "params": ["your-jwt-token"], "id": 2}' http://localhost:8080
```

#### echo

Returns a greeting with the provided message. Requires a valid JWT token.

Example request with token in body:
```bash
curl -X POST -H "Content-Type: application/json" -d '{"jsonrpc": "2.0", "method": "echo", "params": {"message": "Hello server!"}, "token": "your-jwt-token", "id": 3}' http://localhost:8080
```

Example request with token as first parameter:
```bash
curl -X POST -H "Content-Type: application/json" -d '{"jsonrpc": "2.0", "method": "echo", "params": ["your-jwt-token", "Hello server!"], "id": 3}' http://localhost:8080
```

Response will be: `"Dear User, Hello server!"`

## Authentication

The server uses JWT tokens for authentication. To use protected methods:

1. First obtain a token using the `purchase_token` method
2. Include the token either:
   - In the request body as a `token` field
   - As the first item in the `params` array

Tokens expire after 1 hour.

## File Structure

- `simple_server.py` - The main server implementation
- `Instructions for Simple HTTP Server.md` - Detailed instructions for running and testing the server

## License

[MIT](https://choosealicense.com/licenses/mit/) 