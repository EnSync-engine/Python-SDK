# EnSync WebSocket Client

WebSocket client for EnSync Engine. An alternative to the gRPC client for environments where WebSocket is preferred or required.

## Installation

```bash
pip install ensync-websocket
```

## Quick Start

```python
from ensync_websocket import EnSyncEngine

# Initialize engine
engine = EnSyncEngine("wss://node.ensync.cloud")

# Create authenticated client
client = await engine.create_client("your-app-key")

# Publish a message
await client.publish(
    "orders/status/update",
    ["appId"],
    {"order_id": "123", "status": "completed"}
)

# Subscribe to messages with decorator pattern
subscription = client.subscribe("orders/status")

@subscription.handler
async def handle_message(message):
    print(f"Received: {message['payload']}")

# Access subscription control methods
await subscription.pause("Maintenance")
await subscription.resume()
```

## Features

- **WebSocket Protocol**: Real-time bidirectional communication
- **Automatic Reconnection**: Handles connection failures gracefully
- **TLS Support**: Secure WebSocket (WSS) connections
- **Hybrid Encryption**: End-to-end encryption with Ed25519 and AES-GCM
- **Event Acknowledgment**: Manual or automatic message acknowledgment
- **Event Replay**: Request historical messages by ID
- **Pause/Resume**: Control message flow with subscription pause/continue

## Connection Options

```python
# Secure WebSocket (production)
engine = EnSyncEngine("wss://node.ensync.cloud")

# Insecure WebSocket (development)
engine = EnSyncEngine("ws://localhost:8080")

# With options
engine = EnSyncEngine("wss://node.ensync.cloud", {
    "enableLogging": True,
    "reconnect_interval": 5000,
    "max_reconnect_attempts": 10
})
```

## When to Use WebSocket vs gRPC

**Use WebSocket when:**

- You need browser compatibility
- Your infrastructure has better WebSocket support
- You're working in restricted environments where gRPC is blocked
- You prefer text-based protocols for debugging

**Use gRPC when:**

- You need maximum performance
- You're building server-to-server communication
- You want built-in load balancing and service mesh integration
- Binary protocol efficiency is important

For most production use cases, we recommend the `ensync-grpc` package for better performance.

## Documentation

For complete documentation, examples, and API reference, visit:

- [Full Documentation](https://github.com/EnSync-engine/Python-SDK)
- [EnSync Engine](https://ensync.cloud)

## Related Packages

- **ensync-core**: Core utilities (automatically installed as dependency)
- **ensync-grpc**: High-performance gRPC client (recommended for production)

## License

MIT License - see LICENSE file for details
