#!/usr/bin/env python3
"""
Example publisher script for EnSync Python SDK.
"""
import asyncio
import os
import random
import time
from dotenv import load_dotenv

from ensync import EnSyncEngine

async def main():
    """Run the WebSocket publisher test."""
    print("Starting WebSocket publisher test...")
    
    # Load environment variables
    load_dotenv()
    
    # Check required environment variables
    if not os.getenv("ENSYNC_ACCESS_KEY"):
        print("ERROR: ENSYNC_ACCESS_KEY environment variable is not set")
        return 1
    
    if not os.getenv("EVENT_TO_PUBLISH"):
        print("ERROR: EVENT_TO_PUBLISH environment variable is not set")
        return 1
    
    if not os.getenv("RECEIVER_IDENTIFICATION_NUMBER"):
        print("ERROR: RECEIVER_IDENTIFICATION_NUMBER environment variable is not set")
        return 1
    
    try:
        # Initialize EnSync client
        ensync_client = EnSyncEngine("wss://node.gms.ensync.cloud", {
            "pingInterval": 15000,  # 15 seconds
            "reconnectInterval": 3000,  # 3 seconds
            "maxReconnectAttempts": 3
        })
        
        print("Creating WebSocket client...")
        client = await ensync_client.create_client(os.getenv("ENSYNC_ACCESS_KEY"))
        # Post-create check to ensure authentication succeeded before proceeding
        if not ensync_client._state["isAuthenticated"]:
            print("Authentication failed; cannot publish")
            return 1
        print("Successfully created and authenticated WebSocket client")
        
        # Track statistics
        durations = []
        total_start_time = time.time()
        
        # Publish test events
        event_name = os.getenv("EVENT_TO_PUBLISH")
        for index in range(2):  # Publish 2 events
            start = time.time()
            try:
                # Create payload
                payload = {
                    "meter_per_seconds": random.randint(0, 30),
                }
                
                # Publish event
                result = await client.publish(
                    event_name,
                    [os.getenv("RECEIVER_IDENTIFICATION_NUMBER")],
                    payload,
                    {"persist": True, "headers": {}}
                )
                
                end = time.time()
                duration = (end - start) * 1000  # Convert to ms
                durations.append(duration)
                
                # Log the response
                print(f"Response: {result}")
                print(f"Duration: {duration:.2f} ms, index: {index}")
                
            except Exception as error:
                print(f"Error publishing event {index}:", error)
        
        # Close the connection
        await client.close()
        
        # Calculate and display final statistics
        total_time = (time.time() - total_start_time) * 1000  # Convert to ms
        avg = sum(durations) / len(durations) if durations else 0
        min_duration = min(durations) if durations else 0
        max_duration = max(durations) if durations else 0
        
        print("\n=== Final Statistics ===")
        print(f"Total requests: {len(durations)}")
        print(f"Average duration: {avg:.2f} ms")
        print(f"Minimum duration: {min_duration:.2f} ms")
        print(f"Maximum duration: {max_duration:.2f} ms")
        print(f"Date of Execution: {time.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"\nTotal execution time: {total_time/1000:.2f} seconds\n")
        print("=====================")
        
        return 0
        
    except Exception as error:
        print("Fatal error occurred:", error)
        if hasattr(error, "cause") and error.cause:
            print("Caused by:", error.cause)
        return 1

if __name__ == "__main__":
    asyncio.run(main())
