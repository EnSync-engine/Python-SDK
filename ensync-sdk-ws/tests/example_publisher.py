"""
Example WebSocket publisher for testing ensync-websocket package.
"""
import asyncio
import os
from dotenv import load_dotenv
from ensync_sdk_ws import EnSyncEngine

load_dotenv()


async def main():
    """Example publisher using WebSocket client."""
    # Initialize engine
    engine = EnSyncEngine(
        os.getenv("ENSYNC_WS_URL", "wss://node.ensync.cloud"),
        {"enableLogging": True}
    )
    
    # Create client
    client = await engine.create_client(os.getenv("ENSYNC_APP_KEY"))
    
    print("Publishing test event...")
    
    # Publish an event
    event_id = await client.publish(
        "test/websocket/event",
        [os.getenv("ENSYNC_RECIPIENT_ID")],
        {"message": "Hello from WebSocket!", "timestamp": asyncio.get_event_loop().time()}
    )
    
    print(f"Published event: {event_id}")
    
    # Close connection
    await client.close()
    print("Connection closed")


if __name__ == "__main__":
    asyncio.run(main())
