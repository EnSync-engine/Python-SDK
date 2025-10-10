"""
EnSync gRPC client for Python.
Provides functionality for connecting to EnSync service via gRPC, publishing and subscribing to events.
"""
import asyncio
import base64
import json
import logging
from typing import Any, Callable, Dict, List, Optional, Set
from collections import deque

import grpc

from .error import EnSyncError, GENERIC_MESSAGE
from .ecc_crypto import (
    encrypt_ed25519, decrypt_ed25519, hybrid_encrypt, hybrid_decrypt,
    decrypt_message_key, decrypt_with_message_key
)

# Import generated protobuf modules
try:
    from . import ensync_pb2
    from . import ensync_pb2_grpc
except ImportError as e:
    raise ImportError(f"Failed to import protobuf modules. Please run: python -m grpc_tools.protoc -I. --python_out=./ensync --grpc_python_out=./ensync ensync.proto") from e

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("EnSync:gRPC")

SERVICE_NAME = ""


class SubscriptionHandler:
    """Wrapper for subscription handler with metadata."""
    def __init__(self, handler: Callable, app_secret_key: Optional[str], auto_ack: bool):
        self.handler = handler
        self.app_secret_key = app_secret_key
        self.auto_ack = auto_ack


class GrpcSubscription:
    """Represents a gRPC subscription to an event."""
    
    def __init__(self, event_name: str, engine: "EnSyncGrpcEngine", app_secret_key: Optional[str] = None, auto_ack: bool = True):
        """
        Initialize a subscription.
        
        Args:
            event_name: Name of the event
            engine: Reference to the EnSyncGrpcEngine instance
            app_secret_key: Optional secret key for decryption
            auto_ack: Whether to automatically acknowledge events
        """
        self.event_name = event_name
        self._engine = engine
        self._app_secret_key = app_secret_key
        self._auto_ack = auto_ack
    
    def on(self, handler: Callable) -> Callable:
        """
        Register an event handler for this subscription.
        
        Args:
            handler: Async function to handle events
            
        Returns:
            Function to remove the handler
        """
        return self._engine._on(self.event_name, handler, self._app_secret_key, self._auto_ack)
    
    async def ack(self, event_idem: str, block: int) -> str:
        """
        Acknowledge an event.
        
        Args:
            event_idem: Event identifier
            block: Block number
            
        Returns:
            Acknowledgment response
        """
        return await self._engine._ack(event_idem, block, self.event_name)
    
    async def resume(self) -> Dict[str, Any]:
        """Resume event processing."""
        return await self._engine._continue_processing(self.event_name)
    
    async def pause(self, reason: str = "") -> Dict[str, Any]:
        """
        Pause event processing.
        
        Args:
            reason: Optional reason for pausing
            
        Returns:
            Pause response
        """
        return await self._engine._pause_processing(self.event_name, reason)
    
    async def defer(self, event_idem: str, delay_ms: int = 1000, reason: str = "") -> Dict[str, Any]:
        """
        Defer processing of an event.
        
        Args:
            event_idem: Event identifier
            delay_ms: Delay in milliseconds
            reason: Optional reason for deferring
            
        Returns:
            Defer response
        """
        return await self._engine._defer_event(event_idem, self.event_name, delay_ms, reason)
    
    async def discard(self, event_idem: str, reason: str = "") -> Dict[str, Any]:
        """
        Discard an event permanently.
        
        Args:
            event_idem: Event identifier
            reason: Optional reason for discarding
            
        Returns:
            Discard response
        """
        return await self._engine._discard_event(event_idem, self.event_name, reason)
    
    async def replay(self, event_idem: str):
        """
        Replay a specific event.
        
        Args:
            event_idem: Event identifier
            
        Returns:
            Replayed event data
        """
        return await self._engine._replay(event_idem, self.event_name, self._app_secret_key)
    
    async def unsubscribe(self):
        """Unsubscribe from this event."""
        return await self._engine._unsubscribe(self.event_name)


class EnSyncGrpcEngine:
    """
    Main gRPC client for interacting with EnSync service.
    
    Provides methods for connecting, publishing and subscribing to events via gRPC.
    """
    
    def __init__(self, url: str, options: Dict[str, Any] = None):
        """
        Initialize EnSync gRPC client.
        
        Args:
            url: gRPC server URL for EnSync service
            options: Configuration options
        """
        options = options or {}
        
        # Configuration (private, internal use only)
        self.__config = {
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
        
        # Subscriptions: event_name -> Set[SubscriptionHandler]
        self._subscriptions = {}
        
        # Active subscription streams: event_name -> asyncio.Task
        self._subscription_tasks = {}
    
    async def create_client(self, access_key: str, options: Dict[str, Any] = None) -> "EnSyncGrpcEngine":
        """
        Create and authenticate an EnSync gRPC client.
        
        Args:
            access_key: Access key for authentication
            options: Additional options
            
        Returns:
            Authenticated EnSyncGrpcEngine instance
            
        Raises:
            EnSyncError: If authentication fails
        """
        options = options or {}
        self.__config["accessKey"] = access_key
        if options.get("appSecretKey"):
            self.__config["appSecretKey"] = options["appSecretKey"]
        await self.connect()
        return self
    
    async def connect(self):
        """Connect to the EnSync gRPC server."""
        logger.info(f"{SERVICE_NAME} Connecting to {self.__config['url']}...")
        
        try:
            # Create gRPC channel (secure or insecure based on URL)
            url = self.__config["url"]
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
        request = ensync_pb2.ConnectRequest(access_key=self.__config["accessKey"])
        
        try:
            response = await self._stub.Connect(request)
            
            if response.success:
                logger.info(f"{SERVICE_NAME} Authentication successful")
                self.__config["clientId"] = response.client_id
                self.__config["clientHash"] = response.client_hash
                self._state["isAuthenticated"] = True
                
                # Store the current subscriptions before clearing them
                current_subscriptions = {}
                
                # Deep copy the handlers to preserve them properly
                for event_name, handlers in self._subscriptions.items():
                    handlers_copy = set()
                    for handler_obj in handlers:
                        handlers_copy.add(SubscriptionHandler(
                            handler_obj.handler,
                            handler_obj.app_secret_key,
                            handler_obj.auto_ack
                        ))
                    current_subscriptions[event_name] = handlers_copy
                
                # Clear existing subscriptions as we'll recreate them
                self._subscriptions.clear()
                
                # Resubscribe to each event and restore its handlers
                for event_name, handlers in current_subscriptions.items():
                    try:
                        logger.info(f"{SERVICE_NAME} Resubscribing to {event_name}")
                        await self.subscribe(event_name)
                        
                        # Restore all handlers for this event
                        if handlers and len(handlers) > 0:
                            for handler_obj in handlers:
                                self._on(event_name, handler_obj.handler, handler_obj.app_secret_key, handler_obj.auto_ack)
                    except Exception as error:
                        logger.error(f"{SERVICE_NAME} Failed to resubscribe to {event_name}: {error}")
                
                return response
            else:
                raise EnSyncError(f"Authentication failed: {response.error_message}", "EnSyncAuthError")
        except grpc.RpcError as e:
            raise EnSyncError(f"gRPC authentication error: {e.details()}", "EnSyncAuthError")
    
    async def _handle_close(self, reason: str):
        """Handle gRPC connection close events."""
        self._state["isConnected"] = False
        self._state["isAuthenticated"] = False
        self._clear_timers()
        
        logger.info(f"{SERVICE_NAME} Connection closed, reason: {reason or 'none provided'}")
        
        # Attempt reconnection with retry loop
        while self._state["shouldReconnect"] and self._state["reconnectAttempts"] < self.__config["maxReconnectAttempts"]:
            self._state["reconnectAttempts"] += 1
            delay = self.__config["reconnectInterval"] * (1.5 ** (self._state["reconnectAttempts"] - 1)) / 1000
            logger.info(f"{SERVICE_NAME} Attempting reconnect {self._state['reconnectAttempts']}/{self.__config['maxReconnectAttempts']} in {delay}s...")
            
            await asyncio.sleep(delay)
            try:
                await self.connect()
                # If connection succeeds, reset reconnect attempts and break
                self._state["reconnectAttempts"] = 0
                logger.info(f"{SERVICE_NAME} Reconnection successful")
                break
            except Exception as error:
                logger.error(f"{SERVICE_NAME} Reconnection attempt {self._state['reconnectAttempts']} failed: {error}")
                # Continue to next iteration if we haven't reached max attempts
                if self._state["reconnectAttempts"] >= self.__config["maxReconnectAttempts"]:
                    logger.error(f"{SERVICE_NAME} Maximum reconnection attempts ({self.__config['maxReconnectAttempts']}) reached. Giving up.")
                    break
    
    def _decrypt_payload(self, encrypted_payload: str, app_secret_key: Optional[str] = None) -> Dict[str, Any]:
        """Decrypt an encrypted payload."""
        try:
            decryption_key = app_secret_key or self.__config.get("appSecretKey") or self.__config.get("clientHash")
            
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
                await asyncio.sleep(self.__config["heartbeatInterval"] / 1000)
                if self._stub and self._state["isAuthenticated"]:
                    request = ensync_pb2.HeartbeatRequest(client_id=self.__config["clientId"])
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
    
    def _get_payload_skeleton(self, payload: Dict[str, Any]) -> Dict[str, str]:
        """Extract top-level skeleton with datatypes."""
        skeleton = {}
        for key, value in payload.items():
            if isinstance(value, bool):  # Check bool before int (bool is subclass of int)
                skeleton[key] = "boolean"
            elif isinstance(value, str):
                skeleton[key] = "string"
            elif isinstance(value, int):
                skeleton[key] = "integer"
            elif isinstance(value, float):
                skeleton[key] = "number"
            elif isinstance(value, dict):
                skeleton[key] = "object"
            elif isinstance(value, list):
                skeleton[key] = "array"
            elif value is None:
                skeleton[key] = "null"
            else:
                skeleton[key] = type(value).__name__
        return skeleton
    
    async def publish(self, event_name: str, recipients: List[str] = None, payload: Dict[str, Any] = None,
                    metadata: Dict[str, Any] = None, options: Dict[str, Any] = None) -> str:
        """
        Publish an event to the EnSync system via gRPC.
        
        Args:
            event_name: Name of the event
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
        
        use_hybrid_encryption = options.get("useHybridEncryption", True) if options else True
        metadata = metadata or {}
        
        # Calculate payload metadata before encryption
        payload_bytes = json.dumps(payload).encode('utf-8')
        payload_metadata = {
            "byte_size": len(payload_bytes),
            "skeleton": self._get_payload_skeleton(payload) if isinstance(payload, dict) else {}
        }
        
        # Serialize payload_metadata as JSON string for gRPC
        payload_metadata_json = json.dumps(payload_metadata)
        print("Payload metadata:", payload_metadata_json)
        print()
        print("Payload:", payload)
        
        try:
            responses = []
            
            # Only use hybrid encryption when there are multiple recipients
            if use_hybrid_encryption and len(recipients) > 1:
                # Use hybrid encryption (one encryption for all recipients)
                recipient_keys_bytes = [base64.b64decode(r) for r in recipients]
                encrypted_data = hybrid_encrypt(payload_bytes, recipient_keys_bytes)
                
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
                        client_id=self.__config["clientId"],
                        event_name=event_name,
                        payload=encrypted_base64,
                        delivery_to=recipient,
                        metadata=json.dumps(metadata),
                        payload_metadata=payload_metadata_json
                    )
                    response = await self._stub.PublishEvent(request)
                    
                    if not response.success:
                        raise EnSyncError(response.error_message, "EnSyncPublishError")
                    
                    responses.append(response.event_idem)
            else:
                # Use traditional encryption (separate encryption for each recipient)
                for recipient in recipients:
                    recipient_bytes = base64.b64decode(recipient)
                    encrypted = encrypt_ed25519(payload_bytes, recipient_bytes)
                    encrypted_base64 = base64.b64encode(json.dumps(encrypted).encode('utf-8')).decode('utf-8')
                    
                    request = ensync_pb2.PublishEventRequest(
                        client_id=self.__config["clientId"],
                        event_name=event_name,
                        payload=encrypted_base64,
                        delivery_to=recipient,
                        metadata=json.dumps(metadata),
                        payload_metadata=payload_metadata_json
                    )
                    response = await self._stub.PublishEvent(request)
                    
                    if not response.success:
                        raise EnSyncError(response.error_message, "EnSyncPublishError")
                    
                    responses.append(response.event_idem)
            
            return ",".join(responses)
        except grpc.RpcError as e:
            raise EnSyncError(f"gRPC publish error: {e.details()}", "EnSyncPublishError")
        except Exception as error:
            raise EnSyncError(str(error), "EnSyncPublishError")
    
    async def subscribe(self, event_name: str, options: Dict[str, Any] = None):
        """
        Subscribe to an event via gRPC streaming.
        
        Args:
            event_name: Name of the event to subscribe to
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
                client_id=self.__config["clientId"],
                event_name=event_name
            )
            
            # Initialize subscription handlers set
            if event_name not in self._subscriptions:
                self._subscriptions[event_name] = set()
            
            # Start streaming task
            stream_task = asyncio.create_task(
                self._handle_event_stream(event_name, request, options)
            )
            self._subscription_tasks[event_name] = stream_task
            
            logger.info(f"{SERVICE_NAME} Successfully subscribed to {event_name}")
            
            # Return subscription object
            return GrpcSubscription(
                event_name, 
                self, 
                options.get("appSecretKey"),
                options.get("autoAck", True)
            )
        except grpc.RpcError as e:
            raise EnSyncError(f"gRPC subscription error: {e.details()}", "EnSyncSubscriptionError")
        except Exception as error:
            raise EnSyncError(str(error), "EnSyncSubscriptionError")
    
    async def _handle_event_stream(self, event_name: str, request, options: Dict[str, Any]):
        """Handle incoming event stream for a subscription."""
        try:
            async for event_response in self._stub.Subscribe(request):
                if event_name in self._subscriptions:
                    handlers = self._subscriptions[event_name]
                    
                    # Create event data structure
                    event_data = {
                        "idem": event_response.event_idem,
                        "eventName": event_response.event_name,
                        "block": event_response.partition_block,
                        "timestamp": None,
                        "payload": None,
                        "sender": event_response.sender,
                        "metadata": json.loads(event_response.metadata) if event_response.metadata else {}
                    }
                    
                    # Process handlers sequentially
                    for handler_obj in handlers:
                        try:
                            # Decrypt the payload
                            decryption_result = self._decrypt_payload(
                                event_response.payload,
                                handler_obj.app_secret_key
                            )
                            
                            if not decryption_result.get("success"):
                                logger.error(f"{SERVICE_NAME} Failed to decrypt event payload")
                                continue
                            
                            event_data["payload"] = decryption_result["payload"]
                            
                            # Call handler
                            result = handler_obj.handler(event_data)
                            if asyncio.iscoroutine(result):
                                await result
                            
                            # Auto-acknowledge if enabled
                            if handler_obj.auto_ack and event_data.get("idem") and event_data.get("block"):
                                try:
                                    await self._ack(event_data["idem"], event_data["block"], event_data["eventName"])
                                except Exception as err:
                                    logger.error(f"{SERVICE_NAME} Auto-acknowledge error: {err}")
                        except Exception as e:
                            logger.error(f"{SERVICE_NAME} Event handler error - {e}")
        except grpc.RpcError as e:
            # Log the error but don't disconnect the entire client
            # Subscription errors should only affect this specific subscription
            logger.error(f"{SERVICE_NAME} Subscription stream error for '{event_name}': {e.details()}")
            
            # Clean up this subscription
            if event_name in self._subscription_tasks:
                del self._subscription_tasks[event_name]
            
            # Only trigger reconnection for connection-level errors
            if e.code() in [grpc.StatusCode.UNAVAILABLE, grpc.StatusCode.INTERNAL]:
                logger.warning(f"{SERVICE_NAME} Connection-level error detected, triggering reconnection")
                await self._handle_close(f"Connection error: {e.details()}")
        except Exception as e:
            logger.error(f"{SERVICE_NAME} Error in event stream for '{event_name}': {str(e)}")
            
            # Clean up this subscription
            if event_name in self._subscription_tasks:
                del self._subscription_tasks[event_name]
    
    def _on(self, event_name: str, handler: Callable, app_secret_key: Optional[str], auto_ack: bool = True):
        """Add an event handler for a subscribed event."""
        if event_name not in self._subscriptions:
            self._subscriptions[event_name] = set()
        
        wrapped_handler = SubscriptionHandler(handler, app_secret_key, auto_ack)
        self._subscriptions[event_name].add(wrapped_handler)
        
        def remove_handler():
            if event_name in self._subscriptions:
                handlers = self._subscriptions[event_name]
                to_remove = None
                for h in handlers:
                    if h.handler == handler:
                        to_remove = h
                        break
                if to_remove:
                    handlers.discard(to_remove)
                if len(handlers) == 0:
                    del self._subscriptions[event_name]
        
        return remove_handler
    
    async def _unsubscribe(self, event_name: str):
        """Unsubscribe from an event."""
        if not self._state["isAuthenticated"]:
            raise EnSyncError("Not authenticated", "EnSyncAuthError")
        
        try:
            request = ensync_pb2.UnsubscribeRequest(
                client_id=self.__config["clientId"],
                event_name=event_name
            )
            response = await self._stub.Unsubscribe(request)
            
            if response.success:
                # Cancel the stream task
                if event_name in self._subscription_tasks:
                    self._subscription_tasks[event_name].cancel()
                    del self._subscription_tasks[event_name]
                
                # Remove handlers
                if event_name in self._subscriptions:
                    del self._subscriptions[event_name]
                
                logger.info(f"{SERVICE_NAME} Successfully unsubscribed from {event_name}")
            else:
                raise EnSyncError(f"Unsubscribe failed: {response.message}", "EnSyncSubscriptionError")
        except grpc.RpcError as e:
            raise EnSyncError(f"gRPC unsubscribe error: {e.details()}", "EnSyncSubscriptionError")
    
    async def _ack(self, event_idem: str, block: int, event_name: str) -> str:
        """Acknowledge a record."""
        if not self._state["isAuthenticated"]:
            raise EnSyncError("Not authenticated", "EnSyncAuthError")
        
        try:
            request = ensync_pb2.AcknowledgeRequest(
                client_id=self.__config["clientId"],
                event_idem=event_idem,
                partition_block=block,
                event_name=event_name
            )
            response = await self._stub.AcknowledgeEvent(request)
            
            if not response.success:
                raise EnSyncError(response.message, "EnSyncGenericError")
            
            return response.message
        except grpc.RpcError as e:
            raise EnSyncError(f"gRPC acknowledge error: {e.details()}", "EnSyncGenericError")
        except Exception as e:
            raise EnSyncError(f"Failed to acknowledge event. {str(e)}", "EnSyncGenericError")
    
    async def _discard_event(self, event_id: str, event_name: str, reason: str = "") -> Dict[str, Any]:
        """Permanently discard an event."""
        if not self._state["isAuthenticated"]:
            raise EnSyncError("Not authenticated", "EnSyncAuthError")
        
        try:
            request = ensync_pb2.DiscardRequest(
                client_id=self.__config["clientId"],
                event_idem=event_id,
                event_name=event_name,
                reason=reason
            )
            response = await self._stub.DiscardEvent(request)
            
            if not response.success:
                raise EnSyncError(response.message, "EnSyncEventError")
            
            return {
                "status": "success",
                "action": "discarded",
                "eventId": event_id,
                "timestamp": int(asyncio.get_event_loop().time() * 1000)
            }
        except grpc.RpcError as e:
            raise EnSyncError(f"gRPC discard error: {e.details()}", "EnSyncDiscardError")
        except Exception as error:
            if isinstance(error, EnSyncError):
                raise error
            raise EnSyncError(str(error), "EnSyncDiscardError")
    
    async def _defer_event(self, event_id: str, event_name: str, delay_ms: int = 0, reason: str = "") -> Dict[str, Any]:
        """Defer processing of an event."""
        if not self._state["isAuthenticated"]:
            raise EnSyncError("Not authenticated", "EnSyncAuthError")
        
        if delay_ms < 1000 or delay_ms > 24 * 60 * 60 * 1000:
            raise EnSyncError("Invalid delay", "EnSyncValidationError")
        
        try:
            request = ensync_pb2.DeferRequest(
                client_id=self.__config["clientId"],
                event_idem=event_id,
                event_name=event_name,
                delay_ms=delay_ms,
                reason=reason
            )
            response = await self._stub.DeferEvent(request)
            
            if not response.success:
                raise EnSyncError(response.message, "EnSyncEventError")
            
            now = int(asyncio.get_event_loop().time() * 1000)
            return {
                "status": "success",
                "action": "deferred",
                "eventId": event_id,
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
    
    async def _continue_processing(self, event_name: str) -> Dict[str, Any]:
        """Resume event processing."""
        if not self._state["isAuthenticated"]:
            raise EnSyncError("Not authenticated", "EnSyncAuthError")
        
        try:
            request = ensync_pb2.ContinueRequest(
                client_id=self.__config["clientId"],
                event_name=event_name
            )
            response = await self._stub.ContinueEvents(request)
            
            if not response.success:
                raise EnSyncError(response.message, "EnSyncContinueError")
            
            return {
                "status": "success",
                "action": "continued",
                "eventName": event_name
            }
        except grpc.RpcError as e:
            raise EnSyncError(f"gRPC continue error: {e.details()}", "EnSyncContinueError")
        except Exception as error:
            if isinstance(error, EnSyncError):
                raise error
            raise EnSyncError(str(error), "EnSyncContinueError")
    
    async def _pause_processing(self, event_name: str, reason: str = "") -> Dict[str, Any]:
        """Pause event processing."""
        if not self._state["isAuthenticated"]:
            raise EnSyncError("Not authenticated", "EnSyncAuthError")
        
        try:
            request = ensync_pb2.PauseRequest(
                client_id=self.__config["clientId"],
                event_name=event_name,
                reason=reason
            )
            response = await self._stub.PauseEvents(request)
            
            if not response.success:
                raise EnSyncError(response.message, "EnSyncPauseError")
            
            return {
                "status": "success",
                "action": "paused",
                "eventName": event_name,
                "reason": reason or None
            }
        except grpc.RpcError as e:
            raise EnSyncError(f"gRPC pause error: {e.details()}", "EnSyncPauseError")
        except Exception as error:
            if isinstance(error, EnSyncError):
                raise error
            raise EnSyncError(str(error), "EnSyncPauseError")
    
    async def _replay(self, event_idem: str, event_name: str, app_secret_key: Optional[str] = None):
        """Request a specific event to be replayed."""
        if not self._state["isAuthenticated"]:
            raise EnSyncError("Not authenticated", "EnSyncAuthError")
        
        if not event_idem:
            raise EnSyncError("Event identifier (eventIdem) is required", "EnSyncReplayError")
        
        try:
            request = ensync_pb2.ReplayRequest(
                client_id=self.__config["clientId"],
                event_idem=event_idem,
                event_name=event_name
            )
            response = await self._stub.ReplayEvent(request)
            
            if not response.success:
                raise EnSyncError(response.message, "EnSyncReplayError")
            
            # Decrypt the event data
            decryption_result = self._decrypt_payload(response.event_data, app_secret_key)
            
            if not decryption_result.get("success"):
                raise EnSyncError("Failed to decrypt replayed event", "EnSyncReplayError")
            
            return {
                "idem": event_idem,
                "eventName": event_name,
                "payload": decryption_result["payload"]
            }
        except grpc.RpcError as e:
            raise EnSyncError(f"gRPC replay error: {e.details()}", "EnSyncReplayError")
        except Exception as error:
            if isinstance(error, EnSyncError):
                raise error
            raise EnSyncError(str(error), "EnSyncReplayError")
    
    def get_client_public_key(self) -> str:
        """Get the client's public key (client hash)."""
        return self.__config.get("clientHash")
    
    async def close(self):
        """Close the gRPC connection."""
        self._state["shouldReconnect"] = False
        self._clear_timers()
        
        if self._channel:
            await self._channel.close()
