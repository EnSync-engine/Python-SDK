# EnSync SDK

Python SDK for EnSync - High-performance message streaming with end-to-end encryption. Built on gRPC for production use.

## Installation

```bash
pip install ensync-sdk
```

## Quick Start

```python
import asyncio
import os
from dotenv import load_dotenv
from ensync_sdk import EnSyncEngine

load_dotenv()

async def quick_start():
    try:
        # 1. Initialize engine and create client
        engine = EnSyncEngine("grpcs://node.gms.ensync.cloud")
        client = await engine.create_client(
            os.environ.get("ENSYNC_APP_KEY"),
            {
                "app_decrypt_key": os.environ.get("ENSYNC_SECRET_KEY")
            }
        )
        
        # 2. Publish a message
        await client.publish(
            "orders/status",
            ["appId"],  # The appId of the receiving party
            {"order_id": "order-123", "status": "completed"}
        )
        
        # 3. Subscribe to messages
        subscription = await client.subscribe("orders/status")
        
        # 4. Handle incoming messages
        async def handle_message(message):
            print(f"Received order update: {message['payload']['order_id']}")
            # Process message...
        
        subscription.on(handle_message)
        
        # 5. Keep the program running
        try:
            await asyncio.Future()  # Run indefinitely
        except KeyboardInterrupt:
            await subscription.unsubscribe()
            await client.close()
            
    except Exception as e:
        print(f'Error: {e}')

if __name__ == "__main__":
    asyncio.run(quick_start())
```

## Usage

### Importing

#### Default (gRPC)

```python
# Import the default engine class (gRPC)
from ensync_sdk import EnSyncEngine

# EnSync Cloud messaging (grpcs required)
engine = EnSyncEngine("grpcs://node.gms.ensync.cloud")

# Create authenticated client
client = await engine.create_client("your-app-key")
```

**Note:** EnSync Cloud messaging requires the `grpcs://` protocol for secure communication.

## API Reference

### EnSyncEngine (gRPC - Default)

```python
engine = EnSyncEngine(url, options=None)
```

#### Parameters

- **url** (`str`): Server URL for EnSync messaging service
- **options** (`dict`, optional): Configuration options
  - `enableLogging` (`bool`, default: `False`): Enable debug logging
  - `reconnect_interval` (`int`, default: `5000`): Reconnection delay in ms
  - `max_reconnect_attempts` (`int`, default: `10`): Maximum reconnection attempts

### Creating a Client

Initialize the engine with your server URL and create a client with your app key.

```python
# Initialize the engine (gRPC with TLS)
engine = EnSyncEngine("grpcs://node.gms.ensync.cloud")

# Enable logs for debugging
engine_verbose = EnSyncEngine("grpcs://node.gms.ensync.cloud", {
    "enableLogging": True
})

# Create a client
client = await engine.create_client("your-app-key")
```

#### Client Creation Parameters

- **app_key** (`str`): Your application access key
- **options** (`dict`, optional): Additional options
  - `app_decrypt_key` (`str`, optional): Secret key for decryption

#### Returns

`EnSyncClient`: Authenticated client instance

### Publishing Messages

```python
# Basic publish
await client.publish(
    "company/service/message-type",  # Message name
    ["appId"],                      # Recipients (appIds of receiving parties)
    {"data": "your payload"}        # Message payload
)

# With optional metadata
await client.publish(
    "company/service/message-type",
    ["appId"],                      # The appId of the receiving party
    {"data": "your payload"},
    {"custom_field": "value"}       # Optional metadata
)
```

#### Publish Parameters

- **message_name** (`str`): Name/type of the message
- **recipients** (`list[str]`): List of recipient appIds
- **payload** (`dict`): Message data to send
- **metadata** (`dict`, optional): Additional metadata (not encrypted)

#### Replying to Messages

Use the `sender` field from received messages to reply back:

```python
async def handle_message(message):
    # Process the message
    print(f"Received: {message['payload']}")
    
    # Reply back to the sender
    sender_app_id = message.get('sender')
    if sender_app_id:
        await client.publish(
            message.get('messageName'),
            [sender_app_id],  # Send back to the original sender
            {"status": "received", "response": "Processing complete"}
        )
```

### Subscribing to Messages

```python
# Using decorator pattern (recommended)
client = await engine.create_client("your-app-key")

# Create subscription with decorator
subscription = client.subscribe("orders/status")

@subscription.handler
async def handle_message(message):
    print(f"Order {message['payload']['order_id']} updated")

# Access subscription control methods
await subscription.pause("Maintenance")
await subscription.resume()

# With custom decryption key
subscription2 = client.subscribe("orders/status", app_decrypt_key="secret-key")

@subscription2.handler
async def handle_secure_message(message):
    print(f"Received: {message['payload']}")
```

### Message Structure

Messages received by handlers have the following structure:

```python
{
    "idem": "message-unique-id",
    "messageName": "orders/status",
    "block": 12345,
    "timestamp": None,
    "payload": {"order_id": "123", "status": "completed"},
    "sender": "sender-public-key",
    "metadata": {"custom_field": "value"}
}
```

### Subscription Control

```python
# Pause message processing
await subscription.pause("Maintenance in progress")

# Resume message processing
await subscription.resume()

# Defer an message (requeue for later)
await subscription.defer(
    message['idem'],
    delay_ms=5000,
    reason="Temporary unavailability"
)

# Discard an message permanently
await subscription.discard(
    message['idem'],
    reason="Invalid data"
)

# Replay a specific message
replayed_message = await subscription.replay(message['idem'])

# Unsubscribe
await subscription.unsubscribe()
```

### Closing Connections

```python
# Close the client connection
await client.close()

# Using context manager (automatic cleanup)
async with engine.create_client("your-app-key") as client:
    await client.publish("message/name", ["appId"], {"data": "value"})
    # Connection automatically closed
```

## Error Handling

```python
from ensync_sdk import EnSyncEngine
from ensync_core import EnSyncError

try:
    engine = EnSyncEngine("grpcs://node.gms.ensync.cloud")
    client = await engine.create_client("your-app-key")
    
    await client.publish(
        "orders/order",
        ["appId"],
        {"order_id": "123"}
    )
except EnSyncError as e:
    print(f"EnSync error: {e}")
except Exception as e:
    print(f"Unexpected error: {e}")
```

### Debugging with Logs

Enable logging to debug connection issues:

```python
engine = EnSyncEngine("grpcs://node.gms.ensync.cloud", {
    "enableLogging": True
})
```

## Complete Examples

### Publishing Example

```python
import asyncio
import os
from dotenv import load_dotenv
from ensync_sdk import EnSyncEngine

load_dotenv()

async def publishing_example():
    # Create client
    engine = EnSyncEngine("grpcs://node.gms.ensync.cloud")
    client = await engine.create_client(os.environ.get("ENSYNC_APP_KEY"))
    
    # Basic publish - returns message ID
    message_id = await client.publish(
        "notifications/email",
        ["appId"],  # The appId of the receiving party
        {"to": "user@example.com", "subject": "Welcome!"}
    )
    print(f"Published message: {message_id}")
    
    # With metadata
    message_id = await client.publish(
        "notifications/email",
        ["appId"],
        {"to": "user@example.com", "subject": "Welcome!"},
        {"source": "email-service", "priority": "high"}
    )
    print(f"Published message with metadata: {message_id}")
    
    await client.close()

if __name__ == "__main__":
    asyncio.run(publishing_example())
```

### Subscribing Example

```python
import asyncio
import os
from dotenv import load_dotenv
from ensync_sdk import EnSyncEngine

load_dotenv()

async def subscribing_example():
    engine = EnSyncEngine("grpcs://node.gms.ensync.cloud")
    client = await engine.create_client(os.environ.get("ENSYNC_APP_KEY"))
    
    # Subscribe to messages
    subscription = await client.subscribe("notifications/email")
    
    # Handle messages
    async def handle_email_notification(message):
        email_data = message['payload']
        print(f"Email sent to: {email_data['to']}")
        print(f"Subject: {email_data['subject']}")
        
        # Message is automatically acknowledged
    
    subscription.on(handle_email_notification)
    
    # Keep running
    try:
        await asyncio.Future()
    except KeyboardInterrupt:
        await subscription.unsubscribe()
        await client.close()

if __name__ == "__main__":
    asyncio.run(subscribing_example())
```

## Best Practices

### Connection Management

- Use context managers for automatic cleanup
- Handle reconnection gracefully with appropriate intervals
- Close connections properly when shutting down

### Message Design

- Use hierarchical message names: `company/service/message-type`
- Keep payloads focused and minimal
- Use metadata for non-sensitive routing information

### Security Best Practices

- Store access keys in environment variables
- Use `app_decrypt_key` for additional decryption layer
- Never log or expose encryption keys
- Validate message payloads before processing

### Performance Optimization

- Use gRPC (default) for better performance than WebSocket
- Enable connection pooling for high-throughput scenarios
- Batch related messages when possible
- Use appropriate `reconnect_interval` based on your use case

## Documentation

For complete documentation, examples, and API reference, visit:
- [Python SDK Documentation](https://docs.ensync.cloud/sdk/python)
- [EnSync Cloud](https://ensync.cloud)

## Related Packages

- **ensync-core**: Core utilities and error handling (automatically installed)
- **ensync-websocket**: WebSocket alternative client

## License

MIT License - see LICENSE file for details
