"""
EnSync gRPC Subscriber Test Script

This script demonstrates how to subscribe to events using the EnSync gRPC client.
It connects to the EnSync server via gRPC and listens for incoming events.

Environment Variables Required:
- ENSYNC_ACCESS_KEY: Your EnSync access key for authentication
- EVENT_TO_SUBSCRIBE: Name of the event to subscribe to (e.g., "test/event")
- APP_SECRET_KEY: Secret key for decrypting messages (optional)
- ENSYNC_GRPC_URL: gRPC server URL (default: localhost:50051)
"""

import asyncio
import os
import sys
import time
from dotenv import load_dotenv

# Add parent directory to path to import ensync module
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from ensync.grpc_client import EnSyncClient
from ensync.error import EnSyncError

# Load environment variables
load_dotenv()


# Global statistics
event_count = 0
start_time = None
event_times = []
processing_times = []  # Track processing completion times


# Get configuration from environment
grpc_url = os.getenv("ENSYNC_GRPC_URL", "localhost:50051")
access_key = os.getenv("ENSYNC_ACCESS_KEY")
event_name = os.getenv("EVENT_TO_SUBSCRIBE")
app_secret_key = os.getenv("APP_SECRET_KEY")

# Initialize gRPC client
ensync_client = EnSyncClient(grpc_url, {
    "enableLogging": True,
    "heartbeatInterval": 15000,
    "reconnectInterval": 3000,
    "maxReconnectAttempts": 3
})

@ensync_client.subscribe(event_name, auto_ack=True, app_secret_key=app_secret_key)
# @ensync_client.subscribe("another/event", auto_ack=True)
async def handle_event(event):
    """Handles incoming events from subscriptions."""
    global event_count, event_times, processing_times
    event_count += 1
    event_time = time.time()
    event_times.append(event_time)

    print(f"\n[Event #{event_count}] Received at {time.strftime('%H:%M:%S')}")
    print(f"  Event Name: {event.get('eventName')}")
    print(f"  Payload: {event.get('payload')}")
    print("-" * 60)

    processing_times.append(time.time())

async def main():
    """Main function to connect the client and run indefinitely."""
    global start_time

    print("=" * 60)
    print("EnSync gRPC Subscriber Test")
    print("=" * 60)

    if not access_key or not event_name:
        print("Error: Missing ENSYNC_ACCESS_KEY or EVENT_TO_SUBSCRIBE env variables.")
        return 1

    print(f"\nConfiguration:")
    print(f"  gRPC URL: {grpc_url}")
    print(f"  Subscribing to: '{event_name}' and 'another/event'")
    print()

    try:
        print("Connecting and authenticating client...")
        client_options = {"appSecretKey": app_secret_key} if app_secret_key else {}
        await ensync_client.create_client(access_key, client_options)

        if not ensync_client._state["is_authenticated"]:
            print("Authentication failed.")
            return 1

        print("✓ Client connected. Waiting for events... (Press Ctrl+C to stop)")
        start_time = time.time()
        await asyncio.Future()  # Run indefinitely

    except KeyboardInterrupt:
        print("\n\nShutting down...")
    except EnSyncError as e:
        print(f"\n✗ EnSync Error: {e}")
        return 1
    except Exception as e:
        print(f"\n✗ Unexpected Error: {e}")
        import traceback
        traceback.print_exc()
        return 1
    finally:
        if ensync_client._state["is_connected"]:
            await ensync_client.close()
        print_statistics()

def print_statistics():
    """Prints the event processing statistics."""
    print("=" * 60)
    if event_count > 0:
        total_time = time.time() - start_time
        avg_rate = event_count / total_time if total_time > 0 else 0
        print("\nSubscription Statistics:")
        print(f"  Total Events Received: {event_count}")
        print(f"  Total Time: {total_time:.2f}s")
        print(f"  Overall Receive Rate: {avg_rate:.2f} events/sec")
    else:
        print("\nNo events received during this session.")
    print("=" * 60)


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
