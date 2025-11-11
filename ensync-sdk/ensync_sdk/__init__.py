"""
EnSync SDK - Python SDK for EnSync Engine.
Provides high-performance gRPC client for real-time messaging.
"""

from .grpc_client import EnSyncGrpcClient as EnSyncEngine

__version__ = "0.4.0"

# Export both names for compatibility
__all__ = ['EnSyncEngine', 'EnSyncGrpcClient']
