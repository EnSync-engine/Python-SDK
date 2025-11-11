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
import json
import importlib
from dotenv import load_dotenv

# Add parent directory to path to import ensync module
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '../..'))
sys.path.insert(0, project_root)
sys.path.insert(0, os.path.join(project_root, 'ensync-core'))

# Force reload the grpc_client module to ensure the latest code is used
from ensync import grpc_client
importlib.reload(grpc_client)

from ensync.grpc_client import EnSyncClient
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
        ensync_client = EnSyncClient(grpc_url, {
            "enableLogging": True,  # Enable logging to debug
            "heartbeatInterval": 15000,  # 15 seconds
            "reconnectInterval": 3000,  # 3 seconds
            "maxReconnectAttempts": 3,
            "recipientCacheSize": 1000
        })
        
        print("Creating gRPC client connection...")
        client = await ensync_client.create_client(access_key)
        
        # Verify authentication
        if not ensync_client.is_authenticated:
            print("Authentication failed; cannot publish")
            return 1
        
        print("Successfully created and authenticated gRPC client")
        print()
        
        # Track statistics
        durations = []
        total_start_time = time.time()
        successful_publishes = 0
        failed_publishes = 0
        stats_lock = asyncio.Lock()
        
        # Configuration for parallel workers
        num_workers = 1  # Number of parallel publisher workers
        num_events = 1
        
        # Create a queue for publishing events
        publish_queue = asyncio.Queue()

        # Worker task - each worker has its own client instance
        async def publisher_worker(worker_id: int):
            nonlocal successful_publishes, failed_publishes
            
            # Each worker creates its own client instance for true parallelism
            print(f"  Worker {worker_id}: Initializing client...")
            worker_client = EnSyncClient(grpc_url, {
                "enableLogging": False,  # Disable logging for workers to reduce noise
                "heartbeatInterval": 15000,
                "reconnectInterval": 3000,
                "maxReconnectAttempts": 0,  # Disable auto-reconnect for workers
                "recipientCacheSize": 1000
            })
            
            try:
                try:
                    await worker_client.create_client(access_key)
                    print(f"  Worker {worker_id}: Ready")
                except Exception as e:
                    print(f"  Worker {worker_id}: Failed to connect - {e}")
                    # Mark all remaining events as failed for this worker
                    while True:
                        event_data = await publish_queue.get()
                        if event_data is None:
                            publish_queue.task_done()
                            break
                        async with stats_lock:
                            failed_publishes += 1
                        publish_queue.task_done()
                    return
                
                while True:
                    event_data = await publish_queue.get()
                    if event_data is None:  # Sentinel for stopping
                        publish_queue.task_done()
                        break
                    
                    index, payload = event_data
                    start_time_event = time.time()
                    try:
                        response = await worker_client.publish(event_name, [recipient], payload)
                        duration = (time.time() - start_time_event) * 1000
                        print(f"  ✓ Worker {worker_id}: Published event {index + 1} (took {duration:.2f}ms)")
                        async with stats_lock:
                            successful_publishes += 1
                            durations.append(duration)
                    except EnSyncError as e:
                        duration = (time.time() - start_time_event) * 1000
                        print(f"  ✗ Worker {worker_id}: Failed event {index + 1}: {e}")
                        async with stats_lock:
                            failed_publishes += 1
                            durations.append(duration)
                    except Exception as e:
                        duration = (time.time() - start_time_event) * 1000
                        print(f"  ✗ Worker {worker_id}: Unexpected error on event {index + 1}: {e}")
                        async with stats_lock:
                            failed_publishes += 1
                            durations.append(duration)
                    
                    publish_queue.task_done()
            finally:
                # Clean up worker's client
                await worker_client.close()
                print(f"  Worker {worker_id}: Closed")

        # Start multiple publisher workers
        print(f"\nStarting {num_workers} parallel publisher workers...")
        worker_tasks = [asyncio.create_task(publisher_worker(i)) for i in range(num_workers)]

        # Enqueue events
        print(f"Enqueuing {num_events} test events...")
        
        for i in range(num_events):
            # Generate a payload that results in an encrypted size of ~1MB.
            # Raw JSON size should be ~100KB as encryption adds ~9-10x overhead.
            large_data = []
            for j in range(200):  # 200 items is approx 100KB raw JSON
                large_data.append({
                    "id": j,
                    "name": f"Item_{j}_for_event_{i}",
                    "description": f"This is a detailed description for item {j}. " * 2,
                    "value": j * 1.5,
                    "active": j % 2 == 0
                })

            payload = {
                "event_id": i + 1,
                "timestamp": time.time(),
                "message": f"Test event {i + 1} with large payload",
                "data": large_data
            }
            await publish_queue.put((i, payload))

        # Wait for the queue to be processed
        await publish_queue.join()

        # Stop all workers
        for _ in range(num_workers):
            await publish_queue.put(None)
        
        # Wait for all workers to finish
        await asyncio.gather(*worker_tasks)

        print(f"\nCompleted: {successful_publishes} successful, {failed_publishes} failed")
        
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
        print(f"  Total Time: {total_duration:.2f}ms ({total_duration/1000:.2f}s)")
        print(f"  Average Duration per Event: {avg_duration:.2f}ms")
        print(f"  Min Duration: {min_duration:.2f}ms")
        print(f"  Max Duration: {max_duration:.2f}ms")
        print(f"  Overall Throughput: {overall_throughput:.2f} events/sec")
        print("=" * 60)

        # Print encryption statistics
        if ensync_client.encryption_durations:
            print("\nEncryption Statistics:")
            print(f"  Average Encryption Latency: {sum(ensync_client.encryption_durations) / len(ensync_client.encryption_durations):.2f}ms")
            print(f"  Min Encryption Latency: {min(ensync_client.encryption_durations):.2f}ms")
            print(f"  Max Encryption Latency: {max(ensync_client.encryption_durations):.2f}ms")
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
