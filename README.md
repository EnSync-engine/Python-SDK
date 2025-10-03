# EnSync Python SDK

A Python SDK for interacting with the EnSync messaging service. This SDK provides functionality for connecting to EnSync, publishing and subscribing to events, and handling encrypted messages.

## Installation

```bash
pip install -e .
```

## Features

- WebSocket connection management with automatic reconnection
- Event publishing with traditional and hybrid encryption
- Event subscription with customizable handlers
- Support for acknowledging, rejecting, and deferring events
- Hybrid encryption for improved performance with multiple recipients

## Usage

### Creating a Client

```python
import asyncio
from ensync import EnSyncEngine

async def main():
    # Initialize the client
    client = EnSyncEngine("ws://localhost:8082")
    
    # Connect and authenticate
    await client.create_client("your_access_key")
    
    # Close the connection when done
    await client.close()

asyncio.run(main())
```

### Publishing Events

```python
# Publish an event
response = await client.publish(
    "your/event/name",
    ["recipient_public_key"],
    {"key": "value"},  # Payload
    {"persist": True, "headers": {}}  # Metadata
)
```

### Subscribing to Events

```python
# Subscribe to an event
subscription = await client.subscribe("your/event/name", {"autoAck": False})

# Add an event handler
async def handle_event(event):
    print(f"Received event: {event}")
    
    # Acknowledge the event
    if "idem" in event:
        await subscription.acknowledge(event["idem"])

# Register the handler
remove_handler = subscription.on(handle_event)

# When done, remove the handler
remove_handler()
```

### Event Management

```python
# Acknowledge an event
await subscription.acknowledge(event_id)

# Reject an event
await subscription.reject(event_id, "Rejection reason")

# Defer an event
await subscription.defer(event_id, 5000, "Deferred for 5 seconds")

# Pause a subscription
await subscription.pause("Paused for maintenance")

# Resume a subscription
await subscription.resume()

# Replay a specific event
await subscription.replay(event_id)
```

## Environment Variables

The test scripts use the following environment variables:

- `ENSYNC_ACCESS_KEY` - Access key for the publisher
- `CLIENT_ACCESS_KEY` - Access key for the subscriber
- `APP_SECRET_KEY` - Optional secret key for decryption
- `EVENT_TO_PUBLISH` - Event name to publish
- `EVENT_TO_SUBSCRIBE` - Event name to subscribe to
- `RECEIVER_IDENTIFICATION_NUMBER` - Recipient's public key
- `REPLAY_EVENT_ID` - Optional ID of an event to replay

## Examples

See the `ensync/tests` directory for example publisher and subscriber scripts.

## License

Copyright © EnSync Team
