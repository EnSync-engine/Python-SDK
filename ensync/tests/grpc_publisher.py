"""
EnSync gRPC Publisher Test Script

This script demonstrates how to publish events using the EnSync gRPC client.
It connects to the EnSync server via gRPC and publishes test events.

Environment Variables Required:
- ENSYNC_ACCESS_KEY: Your EnSync access key for authentication
- EVENT_TO_PUBLISH: Name of the event to publish (e.g., "test/event")
- RECEIVER_IDENTIFICATION_NUMBER: Base64-encoded public key of the recipient
- ENSYNC_GRPC_URL: gRPC server URL (default: localhost:50051)
"""

import asyncio
import os
import sys
import time
import random
from dotenv import load_dotenv

# Add parent directory to path to import ensync module
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from ensync.grpc_client import EnSyncGrpcEngine
from ensync.error import EnSyncError

# Load environment variables
load_dotenv()


async def main():
    """Main function to test gRPC event publishing."""
    print("=" * 60)
    print("EnSync gRPC Publisher Test")
    print("=" * 60)
    
    # Validate environment variables
    required_vars = ["ENSYNC_ACCESS_KEY", "EVENT_TO_PUBLISH", "RECEIVER_IDENTIFICATION_NUMBER"]
    missing_vars = [var for var in required_vars if not os.getenv(var)]
    
    if missing_vars:
        print(f"Error: Missing required environment variables: {', '.join(missing_vars)}")
        print("\nPlease set the following environment variables:")
        print("- ENSYNC_ACCESS_KEY: Your EnSync access key")
        print("- EVENT_TO_PUBLISH: Event name to publish")
        print("- RECEIVER_IDENTIFICATION_NUMBER: Recipient's public key (base64)")
        print("- ENSYNC_GRPC_URL: gRPC server URL (optional, default: localhost:50051)")
        return 1
    
    # Get configuration from environment
    grpc_url = os.getenv("ENSYNC_GRPC_URL", "localhost:50051")
    access_key = os.getenv("ENSYNC_ACCESS_KEY")
    event_name = os.getenv("EVENT_TO_PUBLISH")
    recipient = os.getenv("RECEIVER_IDENTIFICATION_NUMBER")
    
    print(f"\nConfiguration:")
    print(f"  gRPC URL: {grpc_url}")
    print(f"  Event Name: {event_name}")
    print(f"  Recipient: {recipient[:20]}...{recipient[-20:]}")
    print()
    
    try:
        # Initialize gRPC client
        print("Initializing EnSync gRPC client...")
        ensync_client = EnSyncGrpcEngine(grpc_url, {
            "heartbeatInterval": 15000,  # 15 seconds
            "reconnectInterval": 3000,  # 3 seconds
            "maxReconnectAttempts": 3
        })
        
        print("Creating gRPC client connection...")
        client = await ensync_client.create_client(access_key)
        
        # Verify authentication
        if not ensync_client._state["isAuthenticated"]:
            print("Authentication failed; cannot publish")
            return 1
        
        print("Successfully created and authenticated gRPC client")
        print()
        
        # Track statistics
        durations = []
        total_start_time = time.time()
        publish_times = []  # Track when each event is published
        successful_publishes = 0
        failed_publishes = 0
        
        # Publish test events
        num_events = 100000
        concurrency = 100  # Number of concurrent publish operations
        print(f"Publishing {num_events} test events with concurrency={concurrency}...")
        print("-" * 60)
        
        # Create a semaphore to limit concurrency
        semaphore = asyncio.Semaphore(concurrency)
        
        async def publish_event(index):
            """Publish a single event with concurrency control."""
            nonlocal successful_publishes, failed_publishes
            async with semaphore:
                start = time.time()
                try:
                    # Create payload
                    payload = {
                        "data": {
                            "lol": "hi"
                        },
                        "count": random.randint(0, 30),
                        "items": [1,2,3],
                        "value": None,
                        "active": True,
                        "message": f"Test event {index + 1} via gRPC"
                    }
                    
                    # Publish event
                    response = await client.publish(
                        event_name,
                        [recipient],
                        payload,
                    )
                    
                    publish_time = time.time()
                    publish_times.append(publish_time)
                    duration = (publish_time - start) * 1000
                    durations.append(duration)
                    successful_publishes += 1
                    
                    # Print progress every 1000 events
                    if (index + 1) % 1000 == 0:
                        print(f"  Progress: {index + 1}/{num_events} events published")
                    
                    return {"success": True, "index": index, "duration": duration}
                    
                except EnSyncError as e:
                    duration = (time.time() - start) * 1000
                    durations.append(duration)
                    failed_publishes += 1
                    if failed_publishes <= 10:  # Only print first 10 errors
                        print(f"  ✗ Failed to publish event {index + 1}: {e}")
                    return {"success": False, "index": index, "duration": duration, "error": str(e)}
                except Exception as e:
                    duration = (time.time() - start) * 1000
                    durations.append(duration)
                    failed_publishes += 1
                    if failed_publishes <= 10:  # Only print first 10 errors
                        print(f"  ✗ Unexpected error publishing event {index + 1}: {e}")
                    return {"success": False, "index": index, "duration": duration, "error": str(e)}
        
        # Create all publish tasks
        tasks = [publish_event(i) for i in range(num_events)]
        
        # Execute all tasks concurrently
        print(f"Starting concurrent publishing...")
        results = await asyncio.gather(*tasks, return_exceptions=True)
        print(f"Completed: {successful_publishes} successful, {failed_publishes} failed")
        
        # Calculate statistics
        total_duration = (time.time() - total_start_time) * 1000
        avg_duration = sum(durations) / len(durations) if durations else 0
        min_duration = min(durations) if durations else 0
        max_duration = max(durations) if durations else 0
        
        # Overall throughput (events per second)
        overall_throughput = (successful_publishes / (total_duration / 1000)) if total_duration > 0 else 0
        
        print("\n" + "=" * 60)
        print("Publishing Statistics:")
        print(f"  Total Events: {num_events}")
        print(f"  Successful: {successful_publishes}")
        print(f"  Failed: {failed_publishes}")
        print(f"  Concurrency Level: {concurrency}")
        print(f"  Total Time: {total_duration:.2f}ms ({total_duration/1000:.2f}s)")
        print(f"  Average Duration per Event: {avg_duration:.2f}ms")
        print(f"  Min Duration: {min_duration:.2f}ms")
        print(f"  Max Duration: {max_duration:.2f}ms")
        print(f"  Overall Throughput: {overall_throughput:.2f} events/sec")
        print("=" * 60)
        
        # Close connection
        print("\nClosing gRPC connection...")
        await client.close()
        print("Connection closed successfully")
        
        return 0
        
    except EnSyncError as e:
        print(f"\n✗ EnSync Error: {e}")
        return 1
    except Exception as e:
        print(f"\n✗ Unexpected Error: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
