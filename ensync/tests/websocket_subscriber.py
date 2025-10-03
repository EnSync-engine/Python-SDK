#!/usr/bin/env python3
"""
Example subscriber script for EnSync Python SDK.
"""
import asyncio
import os
import signal
import sys
from dotenv import load_dotenv

from ensync import EnSyncEngine

# Track statistics
total_events_received = 0
total_events_acknowledged = 0
processed_events = []
event_count = -1

# Flag to control the main loop
running = True

def handle_sigint(sig, frame):
    """Handle Ctrl+C to gracefully exit."""
    global running
    print("\nUnsubscribing and closing connection...")
    running = False

async def main():
    """Run the WebSocket subscriber test."""
    global total_events_received, total_events_acknowledged, processed_events, event_count, running
    
    # Set up signal handler
    signal.signal(signal.SIGINT, handle_sigint)
    
    # Load environment variables
    load_dotenv()
    
    # Check required environment variables
    if not os.getenv("CLIENT_ACCESS_KEY"):
        print("ERROR: CLIENT_ACCESS_KEY environment variable is not set")
        return 1
    
    try:
        # Get event name from environment or use default
        event_name = os.getenv("EVENT_TO_SUBSCRIBE", "progo/bicycles/coordinates")
        
        # Initialize EnSync client
        ensync_client = EnSyncEngine("wss://node.gms.ensync.cloud")
        
        # Create client with optional app secret key
        client_options = {}
        if os.getenv("APP_SECRET_KEY"):
            client_options["appSecretKey"] = os.getenv("APP_SECRET_KEY")
            
        await ensync_client.create_client(os.getenv("CLIENT_ACCESS_KEY"), client_options if client_options else None)
        
        # Subscribe to the event with autoAck set to false for manual acknowledgment
        subscription = await ensync_client.subscribe(event_name, {"autoAck": False})
        
        # Optionally replay a specific event if ID is provided
        replay_event_id = os.getenv("REPLAY_EVENT_ID")
        if replay_event_id:
            replay_result = await subscription["replay"](replay_event_id)
            print("Replay Result:", replay_result)
        
        # Set up event handler
        async def event_handler(event):
            global event_count, total_events_received, total_events_acknowledged, processed_events
            
            event_count += 1
            print(f"\nSpeed Event received: {event} (Event #{event_count})")
            total_events_received += 1
            
            # Process based on event count for demonstration
            if event_count == 0:
                # Acknowledge the first event
                if "idem" in event and "block" in event:
                    ack_result = await subscription["ack"](event["idem"], event["block"])
                    print("Acknowledge Result:", ack_result)
                    total_events_acknowledged += 1
                    processed_events.append(event)
            
            elif event_count == 1:
                # Defer the second event
                if "idem" in event:
                    defer_result = await subscription["defer"](event["idem"], 10000, "Deferring second event")
                    print("Deferred Result:", defer_result)
                    return
            
            else:
                # Discard other events
                if "idem" in event:
                    discard_result = await subscription["discard"](event["idem"], "Event discarded by test script")
                    print("Discard Result:", discard_result)
        
        # Add the event handler to the subscription
        remove_handler = subscription["on"](event_handler)
        
        # Keep the script running until Ctrl+C
        print(f"Subscribed to {event_name}. Press Ctrl+C to exit.")
        
        # Main loop
        while running:
            await asyncio.sleep(1)
        
        # Clean up
        remove_handler()
        await ensync_client.close()
        
        # Print final statistics
        print("Total Events Received:", total_events_received)
        print("Total Events Acknowledged:", total_events_acknowledged)
        print("Processed Events:", processed_events)
        
        return 0
        
    except Exception as error:
        print("Fatal error occurred:", error)
        if hasattr(error, "cause") and error.cause:
            print("Caused by:", error.cause)
        return 1

if __name__ == "__main__":
    asyncio.run(main())
