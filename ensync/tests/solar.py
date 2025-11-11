import asyncio
import os
import sys
import importlib

# Add parent directory to path to import ensync module FIRST
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from ensync import grpc_client
importlib.reload(grpc_client)

from ensync.grpc_client import EnSyncGrpcClient
from ensync.error import EnSyncError


grpc_url = "grpcs://node.gms.ensync.cloud"
app_key = "J1ic4fbQzJq7YkgSsB3kZmkeMNbZsgcs"

async def main():
  ensync_client = EnSyncGrpcClient(grpc_url, {"enableLogging": True})

  print("Creating gRPC client connection...")
  client = await ensync_client.create_client(app_key)
  
  # Demonstrate new Pythonic properties
  print(f"Connected: {client.is_connected}")
  print(f"Authenticated: {client.is_authenticated}")
  print(f"Client ID: {client.client_id}")
  print(f"Client Hash: {client.client_hash[:20]}..." if client.client_hash else "None")


if __name__ == "__main__":
    asyncio.run(main())