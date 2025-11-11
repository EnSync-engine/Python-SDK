"""
Example WebSocket subscriber for testing ensync-websocket package.
"""
import asyncio
import os
from dotenv import load_dotenv
from ensync_sdk_ws import EnSyncEngine

load_dotenv()


async def main():
    """Example subscriber using WebSocket client."""
    # Initialize engine
    engine = EnSyncEngine(
        os.getenv("ENSYNC_WS_URL", "wss://node.ensync.cloud"),
        {"enableLogging": True}
    )
    
    # Create client with secret key for decryption
    client = await engine.create_client(
        os.getenv("ENSYNC_APP_KEY"),
        {"app_secret_key": os.getenv("ENSYNC_SECRET_KEY")}
    )
    
    print("Subscribing to test events...")
    
    # Subscribe to events
    subscription = await client.subscribe("test/websocket/event")
    
    # Handle incoming events
    async def handle_event(event):
        print(f"\n📨 Received event:")
        print(f"  Event Name: {event.get('event_name')}")
        print(f"  Payload: {event.get('payload')}")
        print(f"  Timestamp: {event.get('timestamp')}")
        print(f"  Idem: {event.get('idem')}")
    
    subscription.on(handle_event)
    
    print("Listening for events... (Press Ctrl+C to stop)")
    
    # Keep running
    try:
        await asyncio.Future()
    except KeyboardInterrupt:
        print("\nShutting down...")
        await subscription.unsubscribe()
        await client.close()


if __name__ == "__main__":
    asyncio.run(main())
