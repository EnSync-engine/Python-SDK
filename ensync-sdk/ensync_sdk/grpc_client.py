"""
EnSync gRPC client for Python.
Provides functionality for connecting to EnSync service via gRPC, publishing and subscribing to messages.
"""
import asyncio
import base64
import json
import logging
import time
from typing import Any, Callable, Dict, List, Optional, Set
from collections import deque, OrderedDict

import grpc

from ensync_core.error import EnSyncError, GENERIC_MESSAGE
from ensync_core.ecc_crypto import (
    encrypt_ed25519, decrypt_ed25519, hybrid_encrypt, hybrid_decrypt,
    decrypt_message_key, decrypt_with_message_key
)
from ensync_core.payload_utils import get_payload_metadata

# Import generated protobuf modules
try:
    from . import ensync_pb2
    from . import ensync_pb2_grpc
except ImportError as e:
    raise ImportError(f"Failed to import protobuf modules. Please run: python -m grpc_tools.protoc -I. --python_out=./ensync --grpc_python_out=./ensync ensync.proto") from e

# Configure logging
logger = logging.getLogger("EnSync:gRPC")
logger.setLevel(logging.CRITICAL + 1)  # Disable all logging by default
logger.addHandler(logging.NullHandler())
logger.propagate = False

SERVICE_NAME = ""


class SubscriptionHandler:
    """Wrapper for subscription handler with metadata."""
    def __init__(self, handler: Callable, app_secret_key: Optional[str], auto_ack: bool):
        self.handler = handler
        self.app_secret_key = app_secret_key
        self.auto_ack = auto_ack


class GrpcSubscription:
    """Represents a gRPC subscription to an message."""
    
    def __init__(self, message_name: str, client, app_secret_key: str = None, auto_ack: bool = True):
        """
        Initialize a subscription.
        
        Args:
            message_name: The name of the message to subscribe to
            client: The EnSyncGrpcClient instance
            app_secret_key: The secret key for decryption
            auto_ack: Whether to automatically acknowledge messages
        """
        self.message_name = message_name
        self._client = client
        self._app_secret_key = app_secret_key
        self._auto_ack = auto_ack
    
    def on(self, handler: Callable) -> Callable:
        """
        Register an message handler for this subscription.
        
        Args:
            handler: Async function to handle messages
            
        Returns:
            Function to remove the handler
        """
        return self._client._on(self.message_name, handler, self._app_secret_key, self._auto_ack)
    
    async def ack(self, message_idem: str, block: int) -> str:
        """
        Acknowledge an message.
        
        Args:
            message_idem: Event identifier
            block: Block number
            
        Returns:
            Acknowledgment response
        """
        return await self._client._ack(message_idem, block, self.message_name)
    
    async def resume(self) -> Dict[str, Any]:
        """Resume message processing."""
        return await self._client._continue_processing(self.message_name)
    
    async def pause(self, reason: str = "") -> Dict[str, Any]:
        """
        Pause message processing.
        
        Args:
            reason: Optional reason for pausing
            
        Returns:
            Pause response
        """
        return await self._client._pause_processing(self.message_name, reason)
    
    async def defer(self, message_idem: str, delay_ms: int = 1000, reason: str = "") -> Dict[str, Any]:
        """
        Defer processing of an message.
        
        Args:
            message_idem: Event identifier
            delay_ms: Delay in milliseconds
            reason: Optional reason for deferring
            
        Returns:
            Defer response
        """
        return await self._client._defer_message(message_idem, self.message_name, delay_ms, reason)
    
    async def discard(self, message_idem: str, reason: str = "") -> Dict[str, Any]:
        """
        Discard an message permanently.
        
        Args:
            message_idem: Event identifier
            reason: Optional reason for discarding
            
        Returns:
            Discard response
        """
        return await self._client._discard_message(message_idem, self.message_name, reason)
    
    async def replay(self, message_idem: str):
        """
        Replay a specific message by its ID.
        
        Args:
            message_idem: The ID of the message to replay
        
        Returns:
            Replayed message data
        """
        return await self._client._replay(message_idem, self.message_name, self._app_secret_key)
    
    async def unsubscribe(self):
        """Unsubscribe from this message."""
        return await self._client._unsubscribe(self.message_name)


class EnSyncGrpcClient:
    """
    Main gRPC client for interacting with EnSync service.
    
    Provides methods for connecting, publishing and subscribing to messages via gRPC.
    """
    
    def __init__(self, url: str, options: Dict[str, Any] = None):
        """
        Initialize EnSync gRPC client.
        
        Args:
            url: gRPC server URL for EnSync service
            options: Configuration options
        """
        options = options or {}
        
        # Enable logging if requested
        enable_logging = options.get("enableLogging", False)
        if enable_logging:
            logging.basicConfig(level=logging.INFO)
            logger.setLevel(logging.INFO)
            # Remove NullHandler and add StreamHandler if needed
            logger.handlers.clear()
            handler = logging.StreamHandler()
            handler.setFormatter(logging.Formatter('%(name)s - %(levelname)s - %(message)s'))
            logger.addHandler(handler)
        
        # Configuration (private, internal use only)
        self._config = {
            "url": url,
            "accessKey": None,
            "clientId": None,
            "clientHash": None,
            "appSecretKey": None,
            "heartbeatInterval": options.get("heartbeatInterval", 30000),
            "reconnectInterval": options.get("reconnectInterval", 5000),
            "maxReconnectAttempts": options.get("maxReconnectAttempts", 5)
        }
        
        # State
        self._state = {
            "isConnected": False,
            "isAuthenticated": False,
            "reconnectAttempts": 0,
            "shouldReconnect": True
        }
        
        # gRPC channel and stub
        self._channel = None
        self._stub = None
        self._heartbeat_task = None
        
        # Subscriptions: message_name -> Set[SubscriptionHandler]
        self._subscriptions = {}
        
        # Active subscription streams: message_name -> asyncio.Task
        self._subscription_tasks = {}

        # Decorated handlers to be registered on connect
        self._decorated_handlers = []

        # LRU Cache for decoded recipient keys
        self._recipient_key_cache_size = options.get("recipientCacheSize", 1000)
        self._recipient_key_cache = OrderedDict()

        # List to store encryption latencies
        self.encryption_durations = []
    
    async def create_client(self, access_key: str, options: Dict[str, Any] = None) -> "EnSyncGrpcClient":
        """
        Create and authenticate an EnSync gRPC client.
        
        Args:
            access_key: Access key for authentication
            options: Additional options
            
        Returns:
            Authenticated EnSyncGrpcClient instance
            
        Raises:
            EnSyncError: If authentication fails
        """
        options = options or {}
        self._config["accessKey"] = access_key
        if options.get("appSecretKey"):
            self._config["appSecretKey"] = options["appSecretKey"]
        await self.connect()
        return self
    
    async def __aenter__(self) -> "EnSyncGrpcClient":
        """Async context manager entry."""
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.close()
        return False
    
    async def close(self, should_reconnect: bool = False):
        """Close the gRPC connection and clean up resources."""
        self._state["shouldReconnect"] = should_reconnect

        # 1. Cancel all running tasks
        self._clear_timers()

        # 2. Close the gRPC channel
        if self._channel:
            logger.info(f"{SERVICE_NAME} Closing gRPC channel.")
            await self._channel.close()
            self._channel = None
        
        # 3. Reset state
        self._stub = None
        self._state["isConnected"] = False
        self._state["isAuthenticated"] = False
        
        if not should_reconnect:
            logger.info(f"{SERVICE_NAME} Connection permanently closed.")

    async def connect(self):
        """Establishes a new gRPC connection and authenticates."""
        logger.info(f"{SERVICE_NAME} Connecting to {self._config['url']}...")
        
        try:
            # Create gRPC channel (secure or insecure based on URL)
            url = self._config["url"]
            if url.startswith("grpcs://"):
                # Use secure channel with TLS
                url = url.replace("grpcs://", "")
                # Add default port 443 if not specified
                if ":" not in url:
                    url = f"{url}:443"
                credentials = grpc.ssl_channel_credentials()
                self._channel = grpc.aio.secure_channel(url, credentials)
                logger.debug(f"{SERVICE_NAME} Using secure gRPC channel (TLS)")
            elif url.startswith("grpc://"):
                # Use insecure channel
                url = url.replace("grpc://", "")
                # Add default port 50051 if not specified
                if ":" not in url:
                    url = f"{url}:50051"
                self._channel = grpc.aio.insecure_channel(url)
                logger.debug(f"{SERVICE_NAME} Using insecure gRPC channel")
            else:
                # Default: assume secure for production URLs, insecure for localhost
                if "localhost" in url or "127.0.0.1" in url:
                    # Add default port 50051 if not specified
                    if ":" not in url:
                        url = f"{url}:50051"
                    self._channel = grpc.aio.insecure_channel(url)
                    logger.debug(f"{SERVICE_NAME} Using insecure gRPC channel (localhost)")
                else:
                    # Add default port 443 if not specified
                    if ":" not in url:
                        url = f"{url}:443"
                    credentials = grpc.ssl_channel_credentials()
                    self._channel = grpc.aio.secure_channel(url, credentials)
                    logger.debug(f"{SERVICE_NAME} Using secure gRPC channel (TLS)")
            
            self._stub = ensync_pb2_grpc.EnSyncServiceStub(self._channel)
            
            logger.info(f"{SERVICE_NAME} gRPC channel established")
            self._state["isConnected"] = True
            self._state["reconnectAttempts"] = 0
            
            # Start heartbeat interval
            self._heartbeat_task = asyncio.create_task(self._start_heartbeat_interval())
            
            # Authenticate
            logger.info(f"{SERVICE_NAME} Attempting authentication...")
            await self._authenticate()
            
        except Exception as error:
            grpc_error = EnSyncError(str(error), "EnSyncConnectionError")
            logger.error(f"{SERVICE_NAME} Connection error - {error}")
            raise grpc_error
    
    async def _authenticate(self):
        """
        Authenticate with the EnSync gRPC server.
        
        Raises:
            EnSyncError: If authentication fails
        """
        logger.info(f"{SERVICE_NAME} Sending authentication request...")
        request = ensync_pb2.ConnectRequest(access_key=self._config["accessKey"])
        
        try:
            response = await self._stub.Connect(request)
            
            if response.success:
                logger.info(f"{SERVICE_NAME} Authentication successful")
                self._config["clientId"] = response.client_id
                self._config["clientHash"] = response.client_hash
                self._state["isAuthenticated"] = True
                
                # Resubscribe to all messages (manual and decorated)
                await self._resubscribe_all()
                
                return response
            else:
                raise EnSyncError(f"Authentication failed: {response.error_message}", "EnSyncAuthError")
        except grpc.RpcError as e:
            raise EnSyncError(f"gRPC authentication error: {e.details()}", "EnSyncAuthError")

    async def _resubscribe_all(self):
        """Handles the logic of subscribing to all registered handlers upon connection."""
        # Combine decorated handlers with existing subscriptions for a unified process
        all_handlers_to_process = list(self._decorated_handlers)

        # Also re-process handlers from manually created subscriptions
        if self._subscriptions:
            for message_name, handlers_set in self._subscriptions.items():
                for handler_obj in handlers_set:
                    opts = {"auto_ack": handler_obj.auto_ack, "app_secret_key": handler_obj.app_secret_key}
                    all_handlers_to_process.append((message_name, handler_obj.handler, opts))

        # Clear previous subscription state before re-establishing
        self._subscription_tasks.clear()
        self._subscriptions.clear()

        # Get unique message names to create one subscription stream per message
        unique_message_names = {item[0] for item in all_handlers_to_process}

        for message_name in unique_message_names:
            try:
                # Find the first handler for this message to get its options
                first_handler_tuple = next((item for item in all_handlers_to_process if item[0] == message_name), None)
                if first_handler_tuple:
                    _, _, kwargs = first_handler_tuple
                    logger.info(f"{SERVICE_NAME} Establishing subscription for {message_name}")
                    await self._create_subscription(message_name, kwargs)
            except Exception as error:
                logger.error(f"{SERVICE_NAME} Failed to create subscription for {message_name}: {error}")

        # Now, register all handlers to their respective (now active) subscriptions
        for message_name, handler, kwargs in all_handlers_to_process:
            app_secret_key = kwargs.get("app_secret_key")
            auto_ack = kwargs.get("auto_ack", True)
            self._on(message_name, handler, app_secret_key, auto_ack)
    
    async def _handle_close(self, reason: str):
        """Handle gRPC connection close messages and trigger reconnection if configured."""
        if not self._state["isConnected"] and self._state["reconnectAttempts"] == 0:
            return

        logger.warning(f"{SERVICE_NAME} Connection lost, reason: {reason or 'none provided'}")
        
        # Close the connection and signal that we want to reconnect
        await self.close(should_reconnect=True)

        # Attempt reconnection with exponential backoff
        while self._state["shouldReconnect"] and self._state["reconnectAttempts"] < self._config["maxReconnectAttempts"]:
            self._state["reconnectAttempts"] += 1
            delay = (self._config["reconnectInterval"] / 1000) * (1.5 ** (self._state["reconnectAttempts"] - 1))
            logger.info(f"{SERVICE_NAME} Reconnecting in {delay:.2f}s (attempt {self._state['reconnectAttempts']}/{self._config['maxReconnectAttempts']})...")
            
            await asyncio.sleep(delay)
            try:
                await self.connect()
                logger.info(f"{SERVICE_NAME} Reconnection successful.")
                break  # Exit loop on success
            except Exception as error:
                logger.error(f"{SERVICE_NAME} Reconnection attempt failed: {error}")

        if self._state["reconnectAttempts"] >= self._config["maxReconnectAttempts"]:
            logger.error(f"{SERVICE_NAME} Max reconnection attempts reached. Giving up.")
            self._state["shouldReconnect"] = False
    
    def _decrypt_payload(self, encrypted_payload: str, app_secret_key: Optional[str] = None) -> Dict[str, Any]:
        """Decrypt an encrypted payload."""
        try:
            decryption_key = app_secret_key or self._config.get("appSecretKey") or self._config.get("clientHash")
            
            if not decryption_key:
                logger.error(f"{SERVICE_NAME} No decryption key available")
                return {"success": False}
            
            # Decode the base64 payload
            decoded_payload = base64.b64decode(encrypted_payload)
            encrypted_data = json.loads(decoded_payload.decode('utf-8'))
            
            # Check if this is a hybrid encrypted message
            if encrypted_data and encrypted_data.get("type") == "hybrid":
                encrypted_payload_data = encrypted_data["payload"]
                keys = encrypted_data["keys"]
                
                decrypted = False
                recipient_ids = list(keys.keys())
                
                for recipient_id in recipient_ids:
                    try:
                        encrypted_key = keys[recipient_id]
                        message_key = decrypt_message_key(encrypted_key, decryption_key)
                        decrypted_str = decrypt_with_message_key(encrypted_payload_data, message_key)
                        payload = json.loads(decrypted_str)
                        decrypted = True
                        break
                    except Exception as error:
                        logger.debug(f"{SERVICE_NAME} Couldn't decrypt with recipient ID {recipient_id}: {str(error)}")
                
                if not decrypted:
                    logger.error(f"{SERVICE_NAME} Failed to decrypt hybrid message with any of the {len(recipient_ids)} recipient keys")
                    return {"success": False}
                
                return {"success": True, "payload": payload}
            else:
                # Handle traditional encryption
                decrypted_str = decrypt_ed25519(encrypted_data, decryption_key)
                payload = json.loads(decrypted_str)
                return {"success": True, "payload": payload}
        except Exception as e:
            logger.error(f"{SERVICE_NAME} Failed to decrypt with key: {str(e)}")
            return {"success": False}
    
    async def _start_heartbeat_interval(self):
        """Start the heartbeat interval."""
        while self._state["shouldReconnect"]:
            try:
                await asyncio.sleep(self._config["heartbeatInterval"] / 1000)
                if self._stub and self._state["isAuthenticated"]:
                    request = ensync_pb2.HeartbeatRequest(client_id=self._config["clientId"])
                    await self._stub.Heartbeat(request)
            except Exception as e:
                logger.error(f"{SERVICE_NAME} Error in heartbeat interval: {str(e)}")
                break
    
    def _clear_timers(self):
        """Clear all timers and tasks."""
        if self._heartbeat_task:
            self._heartbeat_task.cancel()
            self._heartbeat_task = None
        
        # Cancel all subscription tasks
        for task in self._subscription_tasks.values():
            task.cancel()
        self._subscription_tasks.clear()
    
    def _get_recipient_key(self, recipient: str) -> bytes:
        """Get a decoded recipient key from the cache, managing LRU policy."""
        if recipient in self._recipient_key_cache:
            self._recipient_key_cache.move_to_end(recipient)
            return self._recipient_key_cache[recipient]

        if len(self._recipient_key_cache) >= self._recipient_key_cache_size:
            self._recipient_key_cache.popitem(last=False)

        decoded_key = base64.b64decode(recipient)
        self._recipient_key_cache[recipient] = decoded_key
        return decoded_key

    
    async def publish(self, message_name: str, recipients: List[str] = None, payload: Dict[str, Any] = None,
                    metadata: Dict[str, Any] = None, options: Dict[str, Any] = None) -> str:
        """
        Publish an message to the EnSync system via gRPC.
        
        Args:
            message_name: Name of the message
            recipients: List of recipient public keys
            payload: Event payload
            metadata: Event metadata
            options: Publishing options
            
        Returns:
            Event identifier
            
        Raises:
            EnSyncError: If publishing fails
        """
        if not self._state["isAuthenticated"]:
            raise EnSyncError("Not authenticated", "EnSyncAuthError")
        
        if not isinstance(recipients, list):
            raise EnSyncError("recipients must be an array", "EnSyncAuthError")
        
        if len(recipients) == 0:
            raise EnSyncError("recipients array cannot be empty", "EnSyncAuthError")
        
        if payload is None:
            raise EnSyncError("payload cannot be None", "EnSyncPublishError")
        
        use_hybrid_encryption = options.get("useHybridEncryption", True) if options else True
        metadata = metadata or {}
        
        # Calculate payload metadata before encryption
        payload_bytes = json.dumps(payload).encode('utf-8')
        payload_metadata = get_payload_metadata(payload) if isinstance(payload, dict) else {
            "byte_size": len(payload_bytes),
            "skeleton": {}
        }
        
        # Serialize payload_metadata as JSON string for gRPC
        payload_metadata_json = json.dumps(payload_metadata)
        
        try:
            responses = []
            
            # Only use hybrid encryption when there are multiple recipients
            if use_hybrid_encryption and len(recipients) > 1:
                # Use hybrid encryption (one encryption for all recipients)
                recipient_keys_bytes = [self._get_recipient_key(r) for r in recipients]
                
                start_time = time.time()
                encrypted_data = hybrid_encrypt(payload_bytes, recipient_keys_bytes)
                end_time = time.time()
                self.encryption_durations.append((end_time - start_time) * 1000)  # in ms
                
                # Format for transmission
                hybrid_message = {
                    "type": "hybrid",
                    "payload": encrypted_data["encryptedPayload"],
                    "keys": encrypted_data["encryptedKeys"]
                }
                
                # Serialize and base64 encode
                encrypted_base64 = base64.b64encode(json.dumps(hybrid_message).encode('utf-8')).decode('utf-8')
                
                # Send to all recipients with the same encrypted payload
                for recipient in recipients:
                    request = ensync_pb2.PublishEventRequest(
                        client_id=self._config["clientId"],
                        message_name=message_name,
                        payload=encrypted_base64,
                        delivery_to=recipient,
                        metadata=json.dumps(metadata),
                        payload_metadata=payload_metadata_json
                    )
                    response = await self._stub.PublishEvent(request)
                    
                    if not response.success:
                        raise EnSyncError(response.error_message, "EnSyncPublishError")
                    
                    responses.append(response.message_idem)
            else:
                # Use traditional encryption (separate encryption for each recipient)
                for recipient in recipients:
                    recipient_bytes = self._get_recipient_key(recipient)
                    
                    start_time = time.time()
                    encrypted = encrypt_ed25519(payload_bytes, recipient_bytes)
                    end_time = time.time()
                    self.encryption_durations.append((end_time - start_time) * 1000)  # in ms

                    encrypted_base64 = base64.b64encode(json.dumps(encrypted).encode('utf-8')).decode('utf-8')
                    
                    request = ensync_pb2.PublishEventRequest(
                        client_id=self._config["clientId"],
                        message_name=message_name,
                        payload=encrypted_base64,
                        delivery_to=recipient,
                        metadata=json.dumps(metadata),
                        payload_metadata=payload_metadata_json
                    )
                    response = await self._stub.PublishEvent(request)
                    
                    if not response.success:
                        raise EnSyncError(response.error_message, "EnSyncPublishError")
                    
                    responses.append(response.message_idem)
            
            return ",".join(responses)
        except grpc.RpcError as e:
            raise EnSyncError(f"gRPC publish error: {e.details()}", "EnSyncPublishError")
        except Exception as error:
            raise EnSyncError(str(error), "EnSyncPublishError")
    
    def subscribe(self, message_name: str, **kwargs):
        """
        Decorator to register an message handler for a subscription.

        This will automatically manage the subscription lifecycle. When the client
        connects, it will subscribe to the message and attach this handler.

        Args:
            message_name (str): The name of the message to subscribe to.
            **kwargs: Subscription options like `auto_ack` and `app_secret_key`.

        Example:
            @engine.subscribe("my.message", auto_ack=True)
            async def handle_my_message(message):
                print(f"Received: {message['payload']}")
        """
        def decorator(handler: Callable):
            self._decorated_handlers.append((message_name, handler, kwargs))
            # To allow stacking decorators, we return the original handler.
            return handler
        return decorator

    async def _create_subscription(self, message_name: str, options: Dict[str, Any] = None):
        """
        Subscribe to an message via gRPC streaming.
        
        Args:
            message_name: Name of the message to subscribe to
            options: Subscription options
            
        Returns:
            Subscription object with methods
            
        Raises:
            EnSyncError: If subscription fails
        """
        if not self._state["isAuthenticated"]:
            raise EnSyncError("Not authenticated", "EnSyncAuthError")
        
        options = options or {"autoAck": True, "appSecretKey": None}
        
        try:
            # Create subscription request
            request = ensync_pb2.SubscribeRequest(
                client_id=self._config["clientId"],
                message_name=message_name
            )
            
            # Initialize subscription handlers set
            if message_name not in self._subscriptions:
                self._subscriptions[message_name] = set()
            
            # Start streaming task
            stream_task = asyncio.create_task(
                self._handle_message_stream(message_name, request, options)
            )
            self._subscription_tasks[message_name] = stream_task
            
            logger.info(f"{SERVICE_NAME} Successfully subscribed to {message_name}")
            
            # Return subscription object
            return GrpcSubscription(
                message_name, 
                self, 
                options.get("appSecretKey"),
                options.get("autoAck", True)
            )
        except grpc.RpcError as e:
            raise EnSyncError(f"gRPC subscription error: {e.details()}", "EnSyncSubscriptionError")
        except Exception as error:
            raise EnSyncError(str(error), "EnSyncSubscriptionError")
    
    async def _handle_message_stream(self, message_name: str, request, options: Dict[str, Any]):
        """Handle incoming message stream for a subscription."""
        try:
            async for message_response in self._stub.Subscribe(request):
                if message_name in self._subscriptions:
                    handlers = self._subscriptions[message_name]
                    
                    # Create message data structure
                    message_data = {
                        "idem": message_response.message_idem,
                        "messageName": message_response.message_name,
                        "block": message_response.partition_block,
                        "timestamp": None,
                        "payload": None,
                        "sender": message_response.sender,
                        "metadata": json.loads(message_response.metadata) if message_response.metadata else {}
                    }
                    
                    # Process handlers sequentially
                    for handler_obj in handlers:
                        try:
                            # Decrypt the payload
                            decryption_result = self._decrypt_payload(
                                message_response.payload,
                                handler_obj.app_secret_key
                            )
                            
                            if not decryption_result.get("success"):
                                logger.error(f"{SERVICE_NAME} Failed to decrypt message payload")
                                continue
                            
                            message_data["payload"] = decryption_result["payload"]
                            
                            # Call handler
                            result = handler_obj.handler(message_data)
                            if asyncio.iscoroutine(result):
                                await result
                            
                            # Auto-acknowledge if enabled
                            if handler_obj.auto_ack and message_data.get("idem") and message_data.get("block"):
                                try:
                                    await self._ack(message_data["idem"], message_data["block"], message_data["messageName"])
                                except Exception as err:
                                    logger.error(f"{SERVICE_NAME} Auto-acknowledge error: {err}")
                        except Exception as e:
                            logger.error(f"{SERVICE_NAME} Event handler error - {e}")
        except grpc.RpcError as e:
            # Log the error but don't disconnect the entire client
            # Subscription errors should only affect this specific subscription
            logger.error(f"{SERVICE_NAME} Subscription stream error for '{message_name}': {e.details()}")
            
            # Clean up this subscription
            if message_name in self._subscription_tasks:
                del self._subscription_tasks[message_name]
            
            # Only trigger reconnection for connection-level errors
            if e.code() in [grpc.StatusCode.UNAVAILABLE, grpc.StatusCode.INTERNAL]:
                logger.warning(f"{SERVICE_NAME} Connection-level error detected, triggering reconnection")
                await self._handle_close(f"Connection error: {e.details()}")
        except Exception as e:
            logger.error(f"{SERVICE_NAME} Error in message stream for '{message_name}': {str(e)}")
            
            # Clean up this subscription
            if message_name in self._subscription_tasks:
                del self._subscription_tasks[message_name]
    
    def _on(self, message_name: str, handler: Callable, app_secret_key: Optional[str], auto_ack: bool = True):
        """Add an message handler for a subscribed message."""
        if message_name not in self._subscriptions:
            self._subscriptions[message_name] = set()
        
        wrapped_handler = SubscriptionHandler(handler, app_secret_key, auto_ack)
        self._subscriptions[message_name].add(wrapped_handler)
        
        def remove_handler():
            if message_name in self._subscriptions:
                handlers = self._subscriptions[message_name]
                to_remove = None
                for h in handlers:
                    if h.handler == handler:
                        to_remove = h
                        break
                if to_remove:
                    handlers.discard(to_remove)
                if len(handlers) == 0:
                    del self._subscriptions[message_name]
        
        return remove_handler
    
    async def _unsubscribe(self, message_name: str):
        """Unsubscribe from an message."""
        if not self._state["isAuthenticated"]:
            raise EnSyncError("Not authenticated", "EnSyncAuthError")
        
        try:
            request = ensync_pb2.UnsubscribeRequest(
                client_id=self._config["clientId"],
                message_name=message_name
            )
            response = await self._stub.Unsubscribe(request)
            
            if response.success:
                # Cancel the stream task
                if message_name in self._subscription_tasks:
                    self._subscription_tasks[message_name].cancel()
                    del self._subscription_tasks[message_name]
                
                # Remove handlers
                if message_name in self._subscriptions:
                    del self._subscriptions[message_name]
                
                logger.info(f"{SERVICE_NAME} Successfully unsubscribed from {message_name}")
            else:
                raise EnSyncError(f"Unsubscribe failed: {response.message}", "EnSyncSubscriptionError")
        except grpc.RpcError as e:
            raise EnSyncError(f"gRPC unsubscribe error: {e.details()}", "EnSyncSubscriptionError")
    
    async def _ack(self, message_idem: str, block: int, message_name: str) -> str:
        """Acknowledge a record."""
        if not self._state["isAuthenticated"]:
            raise EnSyncError("Not authenticated", "EnSyncAuthError")
        
        try:
            request = ensync_pb2.AcknowledgeRequest(
                client_id=self._config["clientId"],
                message_idem=message_idem,
                partition_block=block,
                message_name=message_name
            )
            response = await self._stub.AcknowledgeEvent(request)
            
            if not response.success:
                raise EnSyncError(response.message, "EnSyncGenericError")
            
            return response.message
        except grpc.RpcError as e:
            raise EnSyncError(f"gRPC acknowledge error: {e.details()}", "EnSyncGenericError")
        except Exception as e:
            raise EnSyncError(f"Failed to acknowledge message. {str(e)}", "EnSyncGenericError")

    async def close(self):
        """Gracefully close the connection and all subscriptions."""
        self._state["shouldReconnect"] = False

        # Unsubscribe from all messages
        if self._stub and self._state["isAuthenticated"]:
            for message_name in list(self._subscriptions.keys()):
                try:
                    await self._unsubscribe(message_name)
                except Exception as e:
                    logger.error(f"{SERVICE_NAME} Error during unsubscribe on close for {message_name}: {e}")

        # Clear timers and cancel tasks
        self._clear_timers()

        # Close the gRPC channel
        if self._channel:
            await self._channel.close()

        logger.info(f"{SERVICE_NAME} Connection closed.")
    
    async def _discard_message(self, message_id: str, message_name: str, reason: str = "") -> Dict[str, Any]:
        """Permanently discard an message."""
        if not self._state["isAuthenticated"]:
            raise EnSyncError("Not authenticated", "EnSyncAuthError")
        
        try:
            request = ensync_pb2.DiscardRequest(
                client_id=self._config["clientId"],
                message_idem=message_id,
                message_name=message_name,
                reason=reason
            )
            response = await self._stub.DiscardEvent(request)
            
            if not response.success:
                raise EnSyncError(response.message, "EnSyncEventError")
            
            return {
                "status": "success",
                "action": "discarded",
                "messageId": message_id,
                "timestamp": int(asyncio.get_message_loop().time() * 1000)
            }
        except grpc.RpcError as e:
            raise EnSyncError(f"gRPC discard error: {e.details()}", "EnSyncDiscardError")
        except Exception as error:
            if isinstance(error, EnSyncError):
                raise error
            raise EnSyncError(str(error), "EnSyncDiscardError")
    
    async def _defer_message(self, message_id: str, message_name: str, delay_ms: int = 0, reason: str = "") -> Dict[str, Any]:
        """Defer processing of an message."""
        if not self._state["isAuthenticated"]:
            raise EnSyncError("Not authenticated", "EnSyncAuthError")
        
        if delay_ms < 1000 or delay_ms > 24 * 60 * 60 * 1000:
            raise EnSyncError("Invalid delay", "EnSyncValidationError")
        
        try:
            request = ensync_pb2.DeferRequest(
                client_id=self._config["clientId"],
                message_idem=message_id,
                message_name=message_name,
                delay_ms=delay_ms,
                reason=reason
            )
            response = await self._stub.DeferEvent(request)
            
            if not response.success:
                raise EnSyncError(response.message, "EnSyncEventError")
            
            now = int(asyncio.get_message_loop().time() * 1000)
            return {
                "status": "success",
                "action": "deferred",
                "messageId": message_id,
                "delayMs": delay_ms,
                "scheduledDelivery": response.delivery_time,
                "timestamp": now
            }
        except grpc.RpcError as e:
            raise EnSyncError(f"gRPC defer error: {e.details()}", "EnSyncDeferError")
        except Exception as error:
            if isinstance(error, EnSyncError):
                raise error
            raise EnSyncError(str(error), "EnSyncDeferError")
    
    async def _continue_processing(self, message_name: str) -> Dict[str, Any]:
        """Resume message processing."""
        if not self._state["isAuthenticated"]:
            raise EnSyncError("Not authenticated", "EnSyncAuthError")
        
        try:
            request = ensync_pb2.ContinueRequest(
                client_id=self._config["clientId"],
                message_name=message_name
            )
            response = await self._stub.ContinueEvents(request)
            
            if not response.success:
                raise EnSyncError(response.message, "EnSyncContinueError")
            
            return {
                "status": "success",
                "action": "continued",
                "messageName": message_name
            }
        except grpc.RpcError as e:
            raise EnSyncError(f"gRPC continue error: {e.details()}", "EnSyncContinueError")
        except Exception as error:
            if isinstance(error, EnSyncError):
                raise error
            raise EnSyncError(str(error), "EnSyncContinueError")
    
    async def _pause_processing(self, message_name: str, reason: str = "") -> Dict[str, Any]:
        """Pause message processing."""
        if not self._state["isAuthenticated"]:
            raise EnSyncError("Not authenticated", "EnSyncAuthError")
        
        try:
            request = ensync_pb2.PauseRequest(
                client_id=self._config["clientId"],
                message_name=message_name,
                reason=reason
            )
            response = await self._stub.PauseEvents(request)
            
            if not response.success:
                raise EnSyncError(response.message, "EnSyncPauseError")
            
            return {
                "status": "success",
                "action": "paused",
                "messageName": message_name,
                "reason": reason or None
            }
        except grpc.RpcError as e:
            raise EnSyncError(f"gRPC pause error: {e.details()}", "EnSyncPauseError")
        except Exception as error:
            if isinstance(error, EnSyncError):
                raise error
            raise EnSyncError(str(error), "EnSyncPauseError")
    
    async def _replay(self, message_idem: str, message_name: str, app_secret_key: Optional[str] = None):
        """Request a specific message to be replayed."""
        if not self._state["isAuthenticated"]:
            raise EnSyncError("Not authenticated", "EnSyncAuthError")
        
        if not message_idem:
            raise EnSyncError("Event identifier (messageIdem) is required", "EnSyncReplayError")
        
        try:
            request = ensync_pb2.ReplayRequest(
                client_id=self._config["clientId"],
                message_idem=message_idem,
                message_name=message_name
            )
            response = await self._stub.ReplayEvent(request)
            
            if not response.success:
                raise EnSyncError(response.message, "EnSyncReplayError")
            
            # Decrypt the message data
            decryption_result = self._decrypt_payload(response.message_data, app_secret_key)
            
            if not decryption_result.get("success"):
                raise EnSyncError("Failed to decrypt replayed message", "EnSyncReplayError")
            
            return {
                "idem": message_idem,
                "messageName": message_name,
                "payload": decryption_result["payload"]
            }
        except grpc.RpcError as e:
            raise EnSyncError(f"gRPC replay error: {e.details()}", "EnSyncReplayError")
        except Exception as error:
            if isinstance(error, EnSyncError):
                raise error
            raise EnSyncError(str(error), "EnSyncReplayError")
    
    @property
    def is_connected(self) -> bool:
        """Check if the client is connected."""
        return self._state["isConnected"]
    
    @property
    def is_authenticated(self) -> bool:
        """Check if the client is authenticated."""
        return self._state["isAuthenticated"]
    
    @property
    def client_id(self) -> Optional[str]:
        """Get the client ID."""
        return self._config.get("clientId")
    
    @property
    def client_hash(self) -> Optional[str]:
        """Get the client's public key (client hash)."""
        return self._config.get("clientHash")
    
    def get_client_public_key(self) -> str:
        """Get the client's public key (client hash). Deprecated: use client_hash property."""
        return self.client_hash
    
    async def close(self):
        """Close the gRPC connection."""
        self._state["shouldReconnect"] = False
        self._clear_timers()
        
        if self._channel:
            await self._channel.close()
