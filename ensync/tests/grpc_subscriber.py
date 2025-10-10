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

from ensync.grpc_client import EnSyncGrpcEngine
from ensync.error import EnSyncError

# Load environment variables
load_dotenv()


# Global statistics
event_count = 0
start_time = None
event_times = []


async def main():
    """Main function to test gRPC event subscription."""
    global start_time
    
    print("=" * 60)
    print("EnSync gRPC Subscriber Test")
    print("=" * 60)
    
    # Validate environment variables
    required_vars = ["ENSYNC_ACCESS_KEY", "EVENT_TO_SUBSCRIBE"]
    missing_vars = [var for var in required_vars if not os.getenv(var)]
    
    if missing_vars:
        print(f"Error: Missing required environment variables: {', '.join(missing_vars)}")
        print("\nPlease set the following environment variables:")
        print("- ENSYNC_ACCESS_KEY: Your EnSync access key")
        print("- EVENT_TO_SUBSCRIBE: Event name to subscribe to")
        print("- APP_SECRET_KEY: Secret key for decryption (optional)")
        print("- ENSYNC_GRPC_URL: gRPC server URL (optional, default: localhost:50051)")
        return 1
    
    # Get configuration from environment
    grpc_url = os.getenv("ENSYNC_GRPC_URL", "localhost:50051")
    access_key = os.getenv("ENSYNC_ACCESS_KEY")
    event_name = os.getenv("EVENT_TO_SUBSCRIBE")
    app_secret_key = os.getenv("APP_SECRET_KEY")
    
    print(f"\nConfiguration:")
    print(f"  gRPC URL: {grpc_url}")
    print(f"  Event Name: {event_name}")
    print(f"  Has Secret Key: {'Yes' if app_secret_key else 'No'}")
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
        client_options = {}
        if app_secret_key:
            client_options["appSecretKey"] = app_secret_key
        
        client = await ensync_client.create_client(access_key, client_options)
        
        # Verify authentication
        if not ensync_client._state["isAuthenticated"]:
            print("Authentication failed; cannot subscribe")
            return 1
        
        print("Successfully created and authenticated gRPC client")
        print()
        
        # Subscribe to event
        print(f"Subscribing to event: {event_name}")
        print("-" * 60)
        
        subscription = await client.subscribe(event_name, {
            "autoAck": False,  # Automatically acknowledge events
            "appSecretKey": app_secret_key
        })
        
        print(f"✓ Successfully subscribed to {event_name}")
        print("\nWaiting for events... (Press Ctrl+C to stop)")
        print("=" * 60)
        
        start_time = time.time()
        
        # Define event handler
        async def handle_event(event):
            global event_count, event_times
            event_count += 1
            event_time = time.time()
            event_times.append(event_time)
            
            print(f"\n[Event #{event_count}] Received at {time.strftime('%H:%M:%S')}")
            print(f"  Event ID: {event.get('idem')}")
            print(f"  Event Name: {event.get('eventName')}")
            print(f"  Event: {event}")
            print(f"  Block: {event.get('block')}")
            print(f"  Timestamp: {event.get('timestamp')}")
            
            # Display payload
            payload = event.get('payload')
            if payload:
                print(f"  Payload:")
                for key, value in payload.items():
                    print(f"    {key}: {value}")
            else:
                print(f"  Payload: (encrypted or unavailable)")
            
            # Display metadata
            metadata = event.get('metadata', {})
            if metadata:
                print(f"  Metadata: {metadata}")
            
            print("-" * 60)
            # if event_count == 1:
            #     defer_res = await subscription.defer(event.get('idem'), 1000)
            #     print(f"DEFER Response: {defer_res}")
            # else:
            ack_res = await subscription.ack(event.get('idem'), event.get('block'))
            print(f"ACK Response: {ack_res}")
            
            # Get the sender's public key from the event to send response back
            sender_public_key = event.get('sender')
            
            if not sender_public_key:
                print("Warning: No recipient public key found, skipping publish")
                return
            
            print("Publishing response...", sender_public_key)
            response = await client.publish(
             event.get('eventName'),
             [sender_public_key],
             {
              "conversation_id": payload.get("conversation_id"),
              "tenant_id": payload.get("tenant_id"),
              "tool": payload.get("tool"),
              "result": {
                "id": "iphone-12-pro-001",
                "name": "iPhone 12 Pro",
                "brand": "Apple",
                "category": "Smartphones",
                "price": 999.99,
                "currency": "USD",
                "storage": "128GB",
                "color": "Pacific Blue",
                "display": "6.1-inch Super Retina XDR",
                "camera": "Triple 12MP camera system",
                "processor": "A14 Bionic chip",
                "in_stock": True,
                "rating": 4.7,
                "release_year": 2020
              },
              "status": "success",
              "timestamp": int(time.time() * 1000)
             },
             {
              "original_event_id": event.get("eventIdem")
             }
            )

            print(f"Req-Response: {response}")
        
        # Register the event handler
        subscription.on(handle_event)
        
        # Keep the program running
        try:
            await asyncio.Future()  # Run indefinitely
        except KeyboardInterrupt:
            print("\n\n" + "=" * 60)
            print("Shutting down...")
            
            # Display statistics
            if event_count > 0:
                total_time = time.time() - start_time
                avg_rate = event_count / total_time if total_time > 0 else 0
                
                print("\nSubscription Statistics:")
                print(f"  Total Events Received: {event_count}")
                print(f"  Total Time: {total_time:.2f}s")
                print(f"  Average Rate: {avg_rate:.2f} events/sec")
                
                if len(event_times) > 1:
                    intervals = [event_times[i] - event_times[i-1] for i in range(1, len(event_times))]
                    avg_interval = sum(intervals) / len(intervals)
                    min_interval = min(intervals)
                    max_interval = max(intervals)
                    
                    print(f"  Average Interval: {avg_interval:.2f}s")
                    print(f"  Min Interval: {min_interval:.2f}s")
                    print(f"  Max Interval: {max_interval:.2f}s")
            else:
                print("\nNo events received during this session.")
            
            print("=" * 60)
            
            # Unsubscribe
            print("\nUnsubscribing from event...")
            await subscription.unsubscribe()
            print("Unsubscribed successfully")
            
            # Close connection
            print("Closing gRPC connection...")
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
