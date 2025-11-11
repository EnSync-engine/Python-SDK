# EnSync SDK

Python SDK for EnSync - High-performance event streaming with end-to-end encryption. Built on gRPC for production use.

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
        engine = EnSyncEngine("node.ensync.cloud")
        client = await engine.create_client(
            os.environ.get("ENSYNC_APP_KEY"),
            {
                "app_secret_key": os.environ.get("ENSYNC_SECRET_KEY")
            }
        )
        
        # 2. Publish an event
        await client.publish(
            "orders/status/updated",
            ["appId"],  # The appId of the receiving party
            {"order_id": "order-123", "status": "completed"}
        )
        
        # 3. Subscribe to events
        subscription = await client.subscribe("orders/status/updated")
        
        # 4. Handle incoming events
        async def handle_event(event):
            print(f"Received order update: {event['payload']['order_id']}")
            # Process event...
        
        subscription.on(handle_event)
        
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

# Production - uses secure TLS on port 443 by default
engine = EnSyncEngine("node.ensync.cloud")

# Development - uses insecure connection on port 50051 by default
# engine = EnSyncEngine("localhost")

# Create authenticated client
client = await engine.create_client("your-app-key")
```

#### WebSocket Alternative

```python
# Import the WebSocket engine class
from ensync_sdk import EnSyncWebSocketEngine

# Initialize WebSocket client
engine = EnSyncWebSocketEngine("wss://node.ensync.cloud")
client = await engine.create_client("your-app-key")
```

**Connection URL Guidelines:**

- Production URLs automatically use secure TLS (port 443)
- `localhost` automatically uses insecure connection (port 50051)
- Explicit protocols: `grpcs://` (secure) or `grpc://` (insecure)
- Custom ports: `node.ensync.cloud:9090`

## API Reference

### EnSyncEngine (gRPC - Default)

```python
engine = EnSyncEngine(url, options=None)
```

#### Parameters

- **url** (`str`): Server URL for EnSync service
- **options** (`dict`, optional): Configuration options
  - `enableLogging` (`bool`, default: `False`): Enable debug logging
  - `disable_tls` (`bool`, default: `False`): Disable TLS encryption
  - `reconnect_interval` (`int`, default: `5000`): Reconnection delay in ms
  - `max_reconnect_attempts` (`int`, default: `10`): Maximum reconnection attempts

### Creating a Client

Initialize the engine with your server URL and create a client with your app key.

```python
# Initialize the engine (gRPC with TLS)
engine = EnSyncEngine("node.ensync.cloud")

# Enable logs for debugging
engine_verbose = EnSyncEngine("node.ensync.cloud", {
    "enableLogging": True
})

# Create a client
client = await engine.create_client("your-app-key")
```

#### Client Creation Parameters

- **app_key** (`str`): Your application access key
- **options** (`dict`, optional): Additional options
  - `app_secret_key` (`str`, optional): Secret key for encryption

#### Returns

`EnSyncClient`: Authenticated client instance

### Publishing Events

```python
# Basic publish
await client.publish(
    "company/service/event-type",  # Event name
    ["appId"],                      # Recipients (appIds of receiving parties)
    {"data": "your payload"}        # Event payload
)

# With optional metadata
await client.publish(
    "company/service/event-type",
    ["appId"],                      # The appId of the receiving party
    {"data": "your payload"},
    {"custom_field": "value"}       # Optional metadata
)
```

#### Publish Parameters

- **event_name** (`str`): Name/type of the event
- **recipients** (`list[str]`): List of recipient appIds
- **payload** (`dict`): Event data to send
- **metadata** (`dict`, optional): Additional metadata (not encrypted)

#### Replying to Events

Use the `sender` field from received events to reply back:

```python
async def handle_event(event):
    # Process the event
    print(f"Received: {event['payload']}")
    
    # Reply back to the sender
    sender_public_key = event.get('sender')
    if sender_public_key:
        await client.publish(
            event.get('eventName'),
            [sender_public_key],  # Send back to the original sender
            {"status": "received", "response": "Processing complete"}
        )
```

### Subscribing to Events

```python
# Subscribe to an event
subscription = await client.subscribe("orders/status/updated")

# Register event handler
async def handle_event(event):
    print(f"Order {event['payload']['order_id']} updated")
    
    # Manual acknowledgment (if auto_ack is False)
    await subscription.ack(event['idem'], event['block'])

subscription.on(handle_event)

# Subscribe with options
subscription = await client.subscribe(
    "orders/status/updated",
    auto_ack=False,              # Disable automatic acknowledgment
    app_secret_key="secret-key"  # Override default encryption key
)
```

### Event Structure

Events received by handlers have the following structure:

```python
{
    "idem": "event-unique-id",
    "eventName": "orders/status/updated",
    "block": 12345,
    "timestamp": None,
    "payload": {"order_id": "123", "status": "completed"},
    "sender": "sender-public-key",
    "metadata": {"custom_field": "value"}
}
```

### Subscription Control

```python
# Pause event processing
await subscription.pause("Maintenance in progress")

# Resume event processing
await subscription.resume()

# Defer an event (requeue for later)
await subscription.defer(
    event['idem'],
    delay_ms=5000,
    reason="Temporary unavailability"
)

# Discard an event permanently
await subscription.discard(
    event['idem'],
    reason="Invalid data"
)

# Replay a specific event
replayed_event = await subscription.replay(event['idem'])

# Unsubscribe
await subscription.unsubscribe()
```

### Closing Connections

```python
# Close the client connection
await client.close()

# Using context manager (automatic cleanup)
async with engine.create_client("your-app-key") as client:
    await client.publish("event/name", ["appId"], {"data": "value"})
    # Connection automatically closed
```

## Error Handling

```python
from ensync_sdk import EnSyncEngine
from ensync_core import EnSyncError

try:
    engine = EnSyncEngine("node.ensync.cloud")
    client = await engine.create_client("your-app-key")
    
    await client.publish(
        "orders/created",
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
engine = EnSyncEngine("node.ensync.cloud", {
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
    engine = EnSyncEngine("node.ensync.cloud")
    client = await engine.create_client(os.environ.get("ENSYNC_APP_KEY"))
    
    # Basic publish - returns event ID
    event_id = await client.publish(
        "notifications/email/sent",
        ["appId"],  # The appId of the receiving party
        {"to": "user@example.com", "subject": "Welcome!"}
    )
    print(f"Published event: {event_id}")
    
    # With metadata
    event_id = await client.publish(
        "notifications/email/sent",
        ["appId"],
        {"to": "user@example.com", "subject": "Welcome!"},
        {"source": "email-service", "priority": "high"}
    )
    print(f"Published event with metadata: {event_id}")
    
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
    engine = EnSyncEngine("node.ensync.cloud")
    client = await engine.create_client(os.environ.get("ENSYNC_APP_KEY"))
    
    # Subscribe to events
    subscription = await client.subscribe("notifications/email/sent")
    
    # Handle events
    async def handle_email_notification(event):
        email_data = event['payload']
        print(f"Email sent to: {email_data['to']}")
        print(f"Subject: {email_data['subject']}")
        
        # Event is automatically acknowledged
    
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

### Event Design

- Use hierarchical event names: `company/service/event-type`
- Keep payloads focused and minimal
- Use metadata for non-sensitive routing information

### Security Best Practices

- Store access keys in environment variables
- Use `app_secret_key` for additional encryption layer
- Never log or expose encryption keys
- Validate event payloads before processing

### Performance Optimization

- Use gRPC (default) for better performance than WebSocket
- Enable connection pooling for high-throughput scenarios
- Batch related events when possible
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
