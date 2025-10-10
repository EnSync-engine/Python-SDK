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
        
        # Publish test events
        num_events = 5
        print(f"Publishing {num_events} test events...")
        print("-" * 60)
        
        for index in range(num_events):
            start = time.time()
            try:
                # Create payload
                payload = {
                    "meter_per_seconds": random.randint(0, 30),
                    "temperature": random.uniform(20.0, 30.0),
                    "humidity": random.uniform(40.0, 70.0),
                    "timestamp": int(time.time() * 1000),
                    "event_index": index + 1,
                    "message": f"Test event {index + 1} via gRPC"
                }
                
                # Publish event
                print(f"\nEvent {index + 1}:")
                print(f"  Publishing to: {event_name}")
                print(f"  Payload: {payload}")
                
                response = await client.publish(
                    event_name,
                    [recipient],
                    payload,
                )
                
                duration = (time.time() - start) * 1000
                durations.append(duration)
                
                print(f"  ✓ Published successfully")
                print(f"  Response: {response}")
                print(f"  Duration: {duration:.2f}ms")
                
                # Wait between events
                if index < num_events - 1:
                    await asyncio.sleep(1)
                
            except EnSyncError as e:
                print(f"  ✗ Failed to publish event {index + 1}: {e}")
                duration = (time.time() - start) * 1000
                durations.append(duration)
            except Exception as e:
                print(f"  ✗ Unexpected error publishing event {index + 1}: {e}")
                duration = (time.time() - start) * 1000
                durations.append(duration)
        
        # Calculate statistics
        total_duration = (time.time() - total_start_time) * 1000
        avg_duration = sum(durations) / len(durations) if durations else 0
        min_duration = min(durations) if durations else 0
        max_duration = max(durations) if durations else 0
        
        print("\n" + "=" * 60)
        print("Publishing Statistics:")
        print(f"  Total Events: {num_events}")
        print(f"  Total Time: {total_duration:.2f}ms")
        print(f"  Average Duration: {avg_duration:.2f}ms")
        print(f"  Min Duration: {min_duration:.2f}ms")
        print(f"  Max Duration: {max_duration:.2f}ms")
        print(f"  Events/sec: {(num_events / (total_duration / 1000)):.2f}")
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
