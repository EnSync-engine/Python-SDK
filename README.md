# Python SDK

---

## Full Documentation

This is the client [SDK](https://pypi.org/project/ensync-sdk/) for [EnSync engine](https://ensync.cloud) (message delivery engine) that enables you to build an ecosystem of connected devices and services.

---

## Installation

```bash
pip install ensync-sdk
```

---

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

Both clients provide the same API for publishing and subscribing to events.

**gRPC Connection Options:**
- Production URLs automatically use secure TLS (port 443)
- `localhost` automatically uses insecure connection (port 50051)
- Explicit protocols: `grpcs://` (secure) or `grpc://` (insecure)
- Custom ports: `node.ensync.cloud:9090`

---

## API Reference

### EnSyncEngine (gRPC - Default)

The main class that manages gRPC connections and client creation for the EnSync system. This is the default and recommended client for production use.

### EnSyncWebSocketEngine (WebSocket - Alternative)

An alternative class that manages WebSocket connections and client creation for the EnSync system.

```python
engine = EnSyncEngine(url, options=None)
```

#### Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `url` | `str` | Yes | The URL of the EnSync server |
| `options` | `dict` | No | Configuration options |

**Options Dictionary:**

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `disable_tls` | `bool` | `False` | Set to true to disable TLS |
| `reconnect_interval` | `int` | `5000` | Reconnection interval in ms |
| `max_reconnect_attempts` | `int` | `10` | Maximum reconnection attempts |

---

### Creating a Client

- Initialize the engine with your server URL
- Create a client with your app key

```python
# Initialize the engine (gRPC with TLS)
engine = EnSyncEngine("grpcs://node.gms.ensync.cloud")

# Create a client
client = await engine.create_client("your-app-key")
```

#### Client Creation Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `app_key` | `str` | Yes | Your EnSync application key |
| `options` | `dict` | No | Client configuration options |

**Options Dictionary:**

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `app_secret_key` | `str` | `None` | Default key used to decrypt incoming messages |

#### Client Returns

Returns a new `EnSyncClient` instance.

---

### Publishing Events

```python
# Basic publish
await client.publish(
    "company/service/event-type",  # Event name
    ["appId"],                     # Recipients (appIds of receiving parties)
    {"data": "your payload"}       # Event payload
)

# With optional parameters
await client.publish(
    "company/service/event-type",
    ["appId"],                     # The appId of the receiving party
    {"data": "your payload"},
    {"persist": True, "headers": {"source": "order-system"}}
)
```

#### Publish Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `event_name` | `str` | Yes | Name of the event (e.g., "company/service/event-type") |
| `recipients` | `list[str]` | Yes | Array of appIds (the appIds of receiving parties) |
| `payload` | `dict` | Yes | Your event data (any JSON-serializable object) |
| `metadata` | `dict` | No | Control event persistence and add custom headers |

**Metadata Dictionary:**

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `persist` | `bool` | `False` | Whether to persist the event on the server |
| `headers` | `dict` | `{}` | Custom headers to include with the event |

#### Payload Metadata (Automatic)

When you publish an event, the SDK automatically calculates and sends payload metadata alongside your event. This metadata is available to recipients **without decrypting the payload**, making it useful for routing, filtering, and monitoring.

**Automatically Generated Fields:**

| Field | Type | Description |
|-------|------|-------------|
| `byte_size` | `int` | Total byte size of the JSON-serialized payload |
| `skeleton` | `dict` | Top-level structure showing property names and their datatypes |

**Example:**

For a payload like:
```python
{
    "message": "hello",
    "data": {"content": "random"},
    "count": 42,
    "active": True
}
```

The automatically generated `payload_metadata` will be:
```python
{
    "byte_size": 67,
    "skeleton": {
        "message": "string",
        "data": "object",
        "count": "integer",
        "active": "boolean"
    }
}
```

**Supported Datatypes:**
- `string` - String values
- `integer` - Integer numbers
- `number` - Float/decimal numbers
- `boolean` - True/False values
- `object` - Nested dictionaries
- `array` - Lists/arrays
- `null` - None/null values

---

### Subscribing to Events

```python
# Basic subscription
subscription = await client.subscribe("company/service/event-type")

# Set up event handler
async def handle_event(event):
    print(f"Received event: {event.payload}")
    # Process the event

subscription.on(handle_event)

# With options
subscription = await client.subscribe(
    "company/service/event-type",
    {
        "auto_ack": False,  # Manual acknowledgment
        "app_secret_key": os.environ.get("CUSTOM_DECRYPT_KEY")  # Custom decryption key
    }
)
```

#### Subscribe Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `event_name` | `str` | Yes | Name of the event to subscribe to |
| `options` | `dict` | No | Subscription options |

**Options Dictionary:**

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `auto_ack` | `bool` | `True` | Set to false for manual acknowledgment |
| `app_secret_key` | `str` | `None` | Custom decryption key for this subscription |

#### Subscription Methods

```python
# Handle incoming events
async def handle_event(event):
    # process event
    pass

subscription.on(handle_event)

# Manually acknowledge an event
await subscription.ack(event.idem, event.block)

# Request a specific event to be replayed
event_data = await subscription.replay("event-idem-123")

# Stop receiving events
await subscription.unsubscribe()
```

---

### Event Structure

When you receive an event through a subscription handler, it contains:

```python
{
    "idem": "abc123",                # Unique event ID (use with ack/discard/replay)
    "block": "456",                  # Block ID (use with ack)
    "event_name": "company/service/event-type",  # Event name
    "payload": { /* your data */ },  # Your decrypted data
    "timestamp": 1634567890123,      # Event timestamp (milliseconds)
    "metadata": {                    # Optional metadata
        "headers": { /* custom headers */ }
    },
    "recipient": "appId"            # The appId of the receiving party
}
```

---

### Closing Connections

```python
# Close just this client
await client.close()

# Close client and engine (if you have no other clients)
await client.close(close_engine=True)
```

---

## Error Handling

The SDK raises `EnSyncError` for various error conditions. Always wrap your code in try-except blocks to handle potential errors gracefully.

```python
try:
    # Your EnSync code
except EnSyncError as e:
    print(f"EnSync Error: {e}")
    # Handle specific error types
    if isinstance(e, EnSyncConnectionError):
        # Handle connection errors
        pass
    elif isinstance(e, EnSyncPublishError):
        # Handle publishing errors
        pass
    elif isinstance(e, EnSyncSubscriptionError):
        # Handle subscription errors
        pass
except Exception as e:
    print(f"Unexpected error: {e}")
```

Common error types:

| Error Type | Description |
|------------|-------------|
| `EnSyncConnectionError` | Connection or authentication issues |
| `EnSyncPublishError` | Problems publishing events |
| `EnSyncSubscriptionError` | Subscription-related errors |
| `EnSyncGenericError` | Other errors |

---

## Complete Examples

### Quick Start

```python
import os
import asyncio
from dotenv import load_dotenv
from ensync import EnSyncEngine

# Load environment variables from .env file
load_dotenv()

async def quick_start():
    try:
        # 1. Initialize engine and create client
        engine = EnSyncEngine("wss://node.ensync.cloud")
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
            print(f"Received order update: {event.payload['order_id']} is {event.payload['status']}")
            # Process event...
        
        subscription.on(handle_event)

        # 5. Keep the program running
        try:
            # Run indefinitely until interrupted
            await asyncio.Future()
        except KeyboardInterrupt:
            # Clean up when done
            await subscription.unsubscribe()
            await client.close()
            
    except Exception as e:
        print(f'Error: {e}')

# Run the async function
if __name__ == "__main__":
    asyncio.run(quick_start())
```

> **Note:** This example uses environment variables for security. Create a `.env` file with:
> ```
> ENSYNC_APP_KEY=your_app_key_here
> ENSYNC_SECRET_KEY=your_secret_key_here
> ```

### Publishing Example

```python
import asyncio
import os
from dotenv import load_dotenv
from ensync import EnSyncEngine

load_dotenv()

async def publishing_example():
    # Create client
    engine = EnSyncEngine("wss://node.ensync.cloud")
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
        ["appId"],  # The appId of the receiving party
        {"to": "user@example.com", "subject": "Welcome!"},
        {"persist": True, "headers": {"source": "email-service"}}
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
from ensync import EnSyncEngine

load_dotenv()

async def update_order_status(order_id, status):
    # Simulated function to update order status
    print(f"Updating order {order_id} to status: {status}")
    return True

def needs_history(order_id):
    # Simulated function to check if we need history
    return order_id.startswith("special-")

def is_temporary_error(error):
    # Simulated function to determine if an error is temporary
    return "timeout" in str(error).lower() or "retry" in str(error).lower()

async def subscribing_example():
    # Create client with decryption key
    engine = EnSyncEngine("grpcs://node.gms.ensync.cloud")
    client = await engine.create_client(
        os.environ.get("ENSYNC_APP_KEY"),
        {"app_secret_key": os.environ.get("ENSYNC_SECRET_KEY")}
    )

    # Subscribe with manual acknowledgment
    subscription = await client.subscribe("payments/completed", {"auto_ack": False})

    # Handle events
    async def handle_payment(event):
        try:
            # Process the payment
            await update_order_status(event.payload["order_id"], "paid")
            
            # Get historical data if needed
            if needs_history(event.payload["order_id"]):
                history = await subscription.replay(event.payload["previous_event_id"])
                print(f"Previous payment: {history}")
            
            # Acknowledge successful processing
            await subscription.ack(event.idem, event.block)
        except Exception as error:
            # Defer processing if temporary error
            if is_temporary_error(error):
                await subscription.defer(event.idem, 60000, "Temporary processing error")
            else:
                # Discard if permanent error
                await subscription.discard(event.idem, "Invalid payment data")
    
    subscription.on(handle_payment)
    
    # Keep the program running
    try:
        await asyncio.Future()
    except KeyboardInterrupt:
        await subscription.unsubscribe()
        await client.close()

if __name__ == "__main__":
    asyncio.run(subscribing_example())
```

---

## Best Practices

### Connection Management

- Store connection credentials securely using environment variables
- Implement proper reconnection logic for production environments
- Always close connections when they're no longer needed

```python
import os
import asyncio
import signal
from dotenv import load_dotenv
from ensync import EnSyncEngine

load_dotenv()

async def main():
    # Using environment variables for sensitive keys
    engine = EnSyncEngine(os.environ.get("ENSYNC_URL"))
    client = await engine.create_client(os.environ.get("ENSYNC_APP_KEY"))
    
    # gRPC client handles reconnection automatically
    
    # Set up signal handlers for graceful shutdown
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, lambda: asyncio.create_task(shutdown(client)))
    
    # Your application code here
    try:
        await asyncio.Future()  # Run indefinitely
    finally:
        await client.close()

async def shutdown(client):
    print("Shutting down...")
    await client.close(close_engine=True)
    asyncio.get_event_loop().stop()

if __name__ == "__main__":
    asyncio.run(main())
```

### Event Design

- Use hierarchical event names (e.g., `domain/entity/action`)
- Keep payloads concise and well-structured
- Consider versioning your event schemas

```python
# Good event naming pattern
await client.publish(
    "inventory/product/created",
    ["warehouse-service"],
    {
        "product_id": "prod-123",
        "name": "Ergonomic Chair",
        "sku": "ERG-CH-BLK",
        "price": 299.99,
        "created_at": int(time.time() * 1000)  # milliseconds timestamp
    }
)
```

### Security Best Practices

- Never hardcode app keys or secret keys
- Use environment variables or secure key management solutions
- Implement proper authentication and authorization
- Consider encrypting sensitive payloads

### Performance Optimization

- Batch events when possible instead of sending many small messages
- Consider message size and frequency in high-volume scenarios
- Use appropriate TTL values for your use case
- Implement proper error handling and retry logic

### Subscription Control

The SDK provides methods to pause, continue, and replay events, which is useful for managing event processing flow.

#### What Pause and Continue Do

When you create a client using `engine.create_client()`, that client receives a unique `client_id`. This `client_id` (not the `app_key`) identifies your specific client instance on the EnSync server.

- **Pause**: Temporarily stops the client from receiving new events from the server. The subscription remains active on the server, but events are not delivered to this specific client instance. Other clients with the same `app_key` but different `client_id` will continue receiving events normally.

- **Continue**: Resumes event delivery to the paused client. Any events that occurred during the pause (depending on server settings and TTL) may be delivered once the subscription is continued.

#### Replaying Events

The replay command allows you to request a specific event to be sent again, even if it has already been processed. Unlike regular event handling which delivers events through the event handler, the replay function returns the event data directly to your code. This is useful for:

- Retrieving specific events for analysis or debugging
- Accessing historical event data without setting up a handler
- Examining event content without processing it
- Getting event data synchronously in your code flow

```python
# Request a specific event to be replayed - returns data directly
event_data = await subscription.replay("event-idem-123")
print(f"Event data: {event_data}")

# You can immediately work with the event data
process_event_data(event_data)
```

The replay command returns the complete event object with its payload:

```python
{
    "event_name": "gms/ensync/third_party/payments/complete",
    "idem": "event-idem-123",
    "block": "81404",
    "metadata": {
        "persist": {"is_string": False, "content": "true"},
        "headers": {},
        "$internal": {
            "replay_info": {
                "is_replayed": {"is_string": False, "content": "true"},
                "replay_timestamp": {"is_string": False, "content": "1758410511179"},
                "was_acknowledged": {"is_string": False, "content": "false"}
            }
        }
    },
    "payload": {/* payload data */},
    "logged_at": 1757778462158,
    "recipient": "RECIPIENT_PUBLIC_KEY_BASE64",
    "is_group": False
}
```

**Direct Access vs Handler Processing:**

Regular event subscription:

```python
# Events come through the handler asynchronously
async def handle_event(event):
    # Process event here
    print(f"Received event: {event}")

subscription.on(handle_event)
```

Replay function:

```python
# Get event data directly and synchronously
event = await subscription.replay("event-idem-123")
print(f"Retrieved event: {event}")
```

#### Deferring Events

The defer method allows you to postpone processing of an event for a specified period. This is useful when:

- You need more time to prepare resources for processing
- You want to implement a retry mechanism with increasing delays
- You need to wait for another system to be ready
- You want to implement rate limiting for event processing

```python
# Defer an event for 5 seconds (5000ms)
defer_result = await subscription.defer(
    "event-idem-123",  # Event ID
    5000,              # Delay in milliseconds
    "Waiting for resources to be available"  # Optional reason
)
print(f"Defer result: {defer_result}")

# Defer with minimum delay (immediate redelivery)
immediate_redelivery = await subscription.defer("event-idem-123", 0)
```

The defer method returns an object with status information:

```python
{
    "status": "success",
    "action": "deferred",
    "event_idem": "event-idem-123",
    "delay_ms": 5000,
    "scheduled_delivery": 1757778467158,  # timestamp when event will be redelivered
    "timestamp": 1757778462158
}
```

#### Discarding Events

The discard method allows you to permanently reject an event without processing it. This is useful when:

- The event contains invalid or corrupted data
- The event is no longer relevant or has expired
- The event was sent to the wrong recipient
- You want to implement a filtering mechanism

```python
# Discard an event permanently
discard_result = await subscription.discard(
    "event-idem-123",  # Event ID
    "Invalid data format"  # Optional reason
)
print(f"Discard result: {discard_result}")
```

The discard method returns an object with status information:

```python
{
    "status": "success",
    "action": "discarded",
    "event_idem": "event-idem-123",
    "timestamp": 1757778462158
}
```

```python
# Create a subscription
subscription = await client.subscribe("inventory/updates")

# Set up event handler
async def handle_event(event):
    print(f"Processing event: {event.id}")
    await process_event(event)

subscription.on(handle_event)

# Pause the subscription when needed
# This will temporarily stop receiving events
await subscription.pause()
print("Subscription paused - no events will be received")

# Perform some operations while subscription is paused
await perform_maintenance()

# Continue the subscription to resume receiving events
await subscription.continue_subscription()  # Note: 'continue' is a Python keyword
print("Subscription continued - now receiving events again")

# Example: Implementing controlled processing with pause/continue
async def process_in_batches(events):
    # Pause subscription while processing a batch
    await subscription.pause()
    
    try:
        # Process events without receiving new ones
        for event in events:
            await process_event(event)
    except Exception as error:
        print(f"Error processing batch: {error}")
    finally:
        # Always continue subscription when done
        await subscription.continue_subscription()
```

Use cases for pause/continue:

- Temporary maintenance or system updates
- Rate limiting or throttling event processing
- Implementing backpressure mechanisms
- Batch processing of events

#### Implementation Details

- Pause/continue operations are performed at the subscription level, not the client level
- The server maintains the subscription state even when paused
- Pausing affects only the specific subscription instance, not all subscriptions for the client
- Events that arrive during a pause may be delivered when continued (depending on TTL settings)
- The pause state is not persisted across client restarts or reconnections
