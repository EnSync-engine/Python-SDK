from .grpc_client import EnSyncClient as EnSyncEngine
from .websocket import EnSyncClient as EnSyncWebSocketEngine

# gRPC is the default, WebSocket is an alternative
__all__ = ['EnSyncEngine', 'EnSyncWebSocketEngine']
