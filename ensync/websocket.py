"""
EnSync WebSocket client for Python.
Provides functionality for connecting to EnSync service, publishing and subscribing to events.
"""
import asyncio
import base64
import json
import logging
from typing import Any, Callable, Dict, List, Optional, Set
from collections import deque

import websockets

from .error import EnSyncError, GENERIC_MESSAGE
from .ecc_crypto import (
    encrypt_ed25519, decrypt_ed25519, hybrid_encrypt, hybrid_decrypt,
    decrypt_message_key, decrypt_with_message_key
)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("EnSync WS:")

SERVICE_NAME = ""


class SubscriptionHandler:
    """Wrapper for subscription handler with metadata."""
    def __init__(self, handler: Callable, app_secret_key: Optional[str], auto_ack: bool):
        self.handler = handler
        self.app_secret_key = app_secret_key
        self.auto_ack = auto_ack


class WebSocketSubscription:
    """Represents a WebSocket subscription to an event."""
    
    def __init__(self, event_name: str, engine: "EnSyncEngine", app_secret_key: Optional[str] = None, auto_ack: bool = True):
        """
        Initialize a subscription.
        
        Args:
            event_name: Name of the event
            engine: Reference to the EnSyncEngine instance
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
    
    async def ack(self, event_idem: str, block: str) -> str:
        """
        Acknowledge an event.
        
        Args:
            event_idem: Event identifier
            block: Block identifier
            
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
    
    async def rollback(self, event_idem: str, block: str) -> str:
        """
        Roll back an event.
        
        Args:
            event_idem: Event identifier
            block: Block identifier
            
        Returns:
            Rollback response
        """
        return await self._engine._rollback(event_idem, block)
    
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


class EnSyncEngine:
    """
    Main client for interacting with EnSync service.
    
    Provides methods for connecting, publishing and subscribing to events.
    """
    
    def __init__(self, url: str, options: Dict[str, Any] = None):
        """
        Initialize EnSync client.
        
        Args:
            url: WebSocket URL for EnSync service
            options: Configuration options
        """
        options = options or {}
        
        # Configuration (private, internal use only)
        self.__config = {
            "url": url.replace("http", "ws") + "/message",
            "accessKey": None,
            "clientId": None,
            "clientHash": None,
            "appSecretKey": None,
            "pingInterval": options.get("pingInterval", 30000),
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
        
        # WebSocket and tasks
        self._ws = None
        self._ping_task = None
        self._message_listener_task = None
        
        # Subscriptions: event_name -> Set[SubscriptionHandler]
        self._subscriptions = {}
        
        # Pending callbacks FIFO (server does not echo a message ID)
        self._message_callbacks = deque()
    
    async def create_client(self, access_key: str, options: Dict[str, Any] = None) -> "EnSyncEngine":
        """
        Create and authenticate an EnSync client.
        
        Args:
            access_key: Access key for authentication
            options: Additional options
            
        Returns:
            Authenticated EnSyncEngine instance
            
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
        """Connect to the EnSync WebSocket server."""
        logger.info(f"{SERVICE_NAME} Connecting to {self.__config['url']}...")
        
        try:
            self._ws = await websockets.connect(self.__config["url"])
            logger.info(f"{SERVICE_NAME} WebSocket connection established")
            self._state["isConnected"] = True
            self._state["reconnectAttempts"] = 0
            
            # Start message listener
            self._message_listener_task = asyncio.create_task(self._listen_for_messages())
            
            # Start ping interval
            self._ping_task = asyncio.create_task(self._start_ping_interval())
            
            # Authenticate
            logger.info(f"{SERVICE_NAME} Attempting authentication...")
            await self._authenticate()
            
        except Exception as error:
            ws_error = EnSyncError(str(error), "EnSyncConnectionError")
            logger.error(f"{SERVICE_NAME} Connection error - {error}")
            raise ws_error
    
    def _convert_key_value_to_object(self, data: str) -> Dict[str, str]:
        """Convert key=value pairs to dict, handling curly braces."""
        converted_records = {}
        # Remove the curly braces wrapping the data
        if data.startswith("{") and data.endswith("}"):
            items = data[1:-1].split(",")
        else:
            items = data.split(",")
        
        for item in items:
            if "=" in item:
                key, value = item.split("=", 1)
                converted_records[key.strip()] = value.strip()
        
        return converted_records
    
    async def _authenticate(self):
        """
        Authenticate with the EnSync server.
        
        Raises:
            EnSyncError: If authentication fails
        """
        logger.info(f"{SERVICE_NAME} Sending authentication message...")
        auth_message = f"CONN;ACCESS_KEY=:{self.__config['accessKey']}"
        response = await self._send_message(auth_message)
        
        if response.startswith("+PASS:"):
            logger.info(f"{SERVICE_NAME} Authentication successful")
            content = response.replace("+PASS:", "")
            resp = self._convert_key_value_to_object(content)
            self.__config["clientId"] = resp.get("clientId")
            self.__config["clientHash"] = resp.get("clientHash")
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
            raise EnSyncError(f"Authentication failed: {response}", "EnSyncAuthError")
    
    async def _listen_for_messages(self):
        """Listen for incoming WebSocket messages."""
        try:
            async for message in self._ws:
                await self._handle_message(message)
        except websockets.exceptions.ConnectionClosed as e:
            logger.warning(f"{SERVICE_NAME} WebSocket closed with code {e.code}: {e.reason}")
            await self._handle_close(e.code, e.reason)
        except Exception as e:
            logger.error(f"{SERVICE_NAME} Error in message listener: {str(e)}")
    
    async def _handle_message(self, data: str):
        """Handle incoming WebSocket messages."""
        message = data if isinstance(data, str) else data.decode('utf-8')
        
        # Handle PING from server
        if message == "PING":
            if self._ws:
                await self._ws.send("PONG")
            return
        
        # Handle event messages
        if message.startswith("+RECORD:"):
            raw_event_data = self._parse_event_message(message)
            
            if raw_event_data and raw_event_data.get("eventName") in self._subscriptions:
                handlers = self._subscriptions[raw_event_data["eventName"]]
                
                # Process handlers sequentially
                for handler_obj in handlers:
                    try:
                        # Process the event with the handler-specific key
                        processed_event = self._parse_and_decrypt_event(message, handler_obj.app_secret_key)
                        
                        if not processed_event or not processed_event.get("payload"):
                            logger.error(f"{SERVICE_NAME} Failed to process event for handler")
                            continue
                        
                        # Call handler
                        result = handler_obj.handler(processed_event)
                        if asyncio.iscoroutine(result):
                            await result
                        
                        # Auto-acknowledge if enabled
                        if handler_obj.auto_ack and processed_event.get("idem") and processed_event.get("block"):
                            try:
                                await self._ack(processed_event["idem"], processed_event["block"], processed_event["eventName"])
                            except Exception as err:
                                logger.error(f"{SERVICE_NAME} Auto-acknowledge error: {err}")
                    except Exception as e:
                        logger.error(f"{SERVICE_NAME} Event handler error - {e}")
            return
        
        # Process response
        if message.startswith("+PASS:") or message.startswith("+REPLAY:") or message.startswith("-FAIL:"):
            if self._message_callbacks:
                callback = self._message_callbacks.popleft()
                if message.startswith("+PASS:") or message.startswith("+REPLAY:"):
                    callback["resolve"](message)
                else:
                    callback["reject"](EnSyncError(message[6:], "EnSyncError"))
                if "timeout" in callback:
                    callback["timeout"].cancel()
            else:
                logger.warning(f"{SERVICE_NAME} Received response but no callbacks in queue: {message[:80]}...")
    
    def _parse_event_message(self, message: str) -> Optional[Dict[str, Any]]:
        """Parse an event message."""
        try:
            if message.startswith("-FAIL:"):
                raise EnSyncError(message, "EnSyncGenericError")
            if not message.startswith("+RECORD:") and not message.startswith("+REPLAY:"):
                return None
            
            content = message.replace("+RECORD:", "").replace("+REPLAY:", "")
            record = json.loads(content)
            
            if record and isinstance(record, dict):
                if record.get("payload"):
                    try:
                        decoded_payload_json = base64.b64decode(record["payload"]).decode('utf-8')
                        encrypted_payload = json.loads(decoded_payload_json)
                        record["encryptedPayload"] = encrypted_payload
                        record["payload"] = None
                    except Exception as e:
                        logger.error(f"{SERVICE_NAME} Failed to process event payload: {e}")
                        return None
                
                return {
                    "eventName": record.get("name"),
                    "idem": record.get("idem") or record.get("id"),
                    "block": record.get("block"),
                    "timestamp": record.get("loggedAt"),
                    "payload": record.get("payload"),
                    "encryptedPayload": record.get("encryptedPayload"),
                    "metadata": record.get("metadata", {})
                }
            return None
        except Exception as e:
            logger.error(f"{SERVICE_NAME} Failed to parse event message: {e}")
            return None
    
    def _parse_and_decrypt_event(self, message: str, app_secret_key: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Parse and decrypt an event message."""
        event_data = self._parse_event_message(message)
        if not event_data:
            return None
        
        if event_data.get("encryptedPayload"):
            decryption_key = app_secret_key or self.__config.get("appSecretKey")
            decryption_result = self._decrypt_payload(event_data, decryption_key)
            if decryption_result.get("success"):
                event_data["payload"] = decryption_result["payload"]
            else:
                logger.warning(f"{SERVICE_NAME} Could not decrypt event payload")
        
        return event_data
    
    async def _handle_close(self, code: int, reason: str):
        """Handle WebSocket close events."""
        self._state["isConnected"] = False
        self._state["isAuthenticated"] = False
        self._clear_timers()
        
        logger.info(f"{SERVICE_NAME} WebSocket closed with code {code or 'unknown'}, reason: {reason or 'none provided'}")
        
        # Clear any pending message callbacks
        while self._message_callbacks:
            callback = self._message_callbacks.popleft()
            callback["reject"](EnSyncError("Connection closed", "EnSyncConnectionError"))
            if "timeout" in callback:
                callback["timeout"].cancel()
        
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
    
    def _decrypt_payload(self, event_data: Dict[str, Any], app_secret_key: Optional[str] = None) -> Dict[str, Any]:
        """Decrypt an encrypted payload."""
        try:
            decryption_key = app_secret_key or self.__config.get("appSecretKey") or self.__config.get("clientHash")
            
            if not decryption_key:
                logger.error(f"{SERVICE_NAME} No decryption key available")
                return {"success": False}
            
            encrypted_data = event_data.get("encryptedPayload")
            
            # Check if this is a hybrid encrypted message
            if encrypted_data and encrypted_data.get("type") == "hybrid":
                encrypted_payload = encrypted_data["payload"]
                keys = encrypted_data["keys"]
                
                decrypted = False
                recipient_ids = list(keys.keys())
                
                for recipient_id in recipient_ids:
                    try:
                        encrypted_key = keys[recipient_id]
                        message_key = decrypt_message_key(encrypted_key, decryption_key)
                        decrypted_str = decrypt_with_message_key(encrypted_payload, message_key)
                        payload = json.loads(decrypted_str)
                        decrypted = True
                        break
                    except Exception as error:
                        logger.debug(f"{SERVICE_NAME} Couldn't decrypt for recipient ID {recipient_id}: {str(error)}")
                
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
    
    async def _start_ping_interval(self):
        """Start the ping interval."""
        while self._state["shouldReconnect"]:
            try:
                await asyncio.sleep(self.__config["pingInterval"] / 1000)
                if self._ws:
                    await self._ws.ping()
            except Exception as e:
                logger.error(f"{SERVICE_NAME} Error in ping interval: {str(e)}")
                break
    
    def _clear_timers(self):
        """Clear all timers."""
        if self._ping_task:
            self._ping_task.cancel()
            self._ping_task = None
        if self._message_listener_task:
            self._message_listener_task.cancel()
            self._message_listener_task = None
    
    async def _send_message(self, message: str) -> str:
        """Send a message and wait for response."""
        future = asyncio.Future()
        
        async def timeout_handler():
            await asyncio.sleep(30)
            if not future.done():
                logger.error(f"{SERVICE_NAME} Message timeout for: {message[:50]}...")
                future.set_exception(EnSyncError("Message timeout", "EnSyncTimeoutError"))
        
        timeout_task = asyncio.create_task(timeout_handler())
        
        callback = {
            "resolve": lambda msg: future.set_result(msg) if not future.done() else None,
            "reject": lambda err: future.set_exception(err) if not future.done() else None,
            "timeout": timeout_task
        }
        
        self._message_callbacks.append(callback)
        
        if self._ws:
            await self._ws.send(message)
        else:
            timeout_task.cancel()
            raise EnSyncError("WebSocket not connected", "EnSyncConnectionError")
        
        try:
            response = await future
            timeout_task.cancel()
            return response
        except Exception as e:
            timeout_task.cancel()
            raise e
    
    async def publish(self, event_name: str, recipients: List[str] = None, payload: Dict[str, Any] = None,
                    metadata: Dict[str, Any] = None, options: Dict[str, Any] = None) -> str:
        """Publish an event to the EnSync system."""
        if not self._state["isAuthenticated"]:
            raise EnSyncError("Not authenticated", "EnSyncAuthError")
        
        if not isinstance(recipients, list):
            raise EnSyncError("recipients must be an array", "EnSyncAuthError")
        
        if len(recipients) == 0:
            raise EnSyncError("recipients array cannot be empty", "EnSyncAuthError")
        
        use_hybrid_encryption = options.get("useHybridEncryption", True) if options else True
        metadata = metadata or {"persist": True, "headers": {}}
        
        try:
            responses = []
            encrypted_payloads = []
            
            # Only use hybrid encryption when there are multiple recipients
            if use_hybrid_encryption and len(recipients) > 1:
                # Use hybrid encryption (one encryption for all recipients)
                payload_bytes = json.dumps(payload).encode('utf-8')
                # Decode recipient keys from base64 to bytes for hybrid_encrypt
                recipient_keys_bytes = [base64.b64decode(r) for r in recipients]
                encrypted_data = hybrid_encrypt(payload_bytes, recipient_keys_bytes)
                
                # Format for transmission - encryptedPayload is already a dict with nonce/ciphertext
                hybrid_message = {
                    "type": "hybrid",
                    "payload": encrypted_data["encryptedPayload"],  # This is a dict, not bytes
                    "keys": encrypted_data["encryptedKeys"]
                }
                
                # Serialize the hybrid message to JSON, then base64 encode it
                encrypted_base64 = base64.b64encode(json.dumps(hybrid_message).encode('utf-8')).decode('utf-8')
                
                # Create one encrypted payload for all recipients
                encrypted_payloads = [(recipient, encrypted_base64) for recipient in recipients]
            else:
                # Use traditional encryption (separate encryption for each recipient)
                payload_bytes = json.dumps(payload).encode('utf-8')
                for recipient in recipients:
                    recipient_bytes = base64.b64decode(recipient)
                    encrypted = encrypt_ed25519(payload_bytes, recipient_bytes)
                    encrypted_base64 = base64.b64encode(json.dumps(encrypted).encode('utf-8')).decode('utf-8')
                    encrypted_payloads.append((recipient, encrypted_base64))
            
            # Send messages to all recipients
            for recipient, encrypted_base64 in encrypted_payloads:
                message = f"PUB;CLIENT_ID=:{self.__config['clientId']};EVENT_NAME=:{event_name};PAYLOAD=:{encrypted_base64};DELIVERY_TO=:{recipient};METADATA=:{json.dumps(metadata)}"
                response = await self._send_message(message)
                responses.append(response)
            
            return ",".join(responses)
        except Exception as error:
            raise EnSyncError(str(error), "EnSyncPublishError")
    
    async def subscribe(self, event_name: str, options: Dict[str, Any] = None):
        """Subscribe to an event."""
        if not self._state["isAuthenticated"]:
            raise EnSyncError("Not authenticated", "EnSyncAuthError")
        
        options = options or {"autoAck": True, "appSecretKey": None}
        
        message = f"SUB;CLIENT_ID=:{self.__config['clientId']};EVENT_NAME=:{event_name}"
        response = await self._send_message(message)
        
        if response.startswith("+PASS:"):
            if event_name not in self._subscriptions:
                self._subscriptions[event_name] = set()
            logger.info(f"{SERVICE_NAME} Successfully subscribed to {event_name}")
            
            # Return subscription object
            return WebSocketSubscription(
                event_name,
                self,
                options.get("appSecretKey"),
                options.get("autoAck", True)
            )
        else:
            raise EnSyncError(f"Subscription failed: {response}", "EnSyncSubscriptionError")
    
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
        
        message = f"UNSUB;CLIENT_ID=:{self.__config['clientId']};EVENT_NAME=:{event_name}"
        response = await self._send_message(message)
        
        if response.startswith("+PASS:"):
            if event_name in self._subscriptions:
                del self._subscriptions[event_name]
            logger.info(f"{SERVICE_NAME} Successfully unsubscribed from {event_name}")
        else:
            raise EnSyncError(f"Unsubscribe failed: {response}", "EnSyncSubscriptionError")
    
    async def _ack(self, event_idem: str, block: str, event_name: str) -> str:
        """Acknowledge a record."""
        if not self._state["isAuthenticated"]:
            raise EnSyncError("Not authenticated", "EnSyncAuthError")
        
        try:
            payload = f"ACK;CLIENT_ID=:{self.__config['clientId']};EVENT_IDEM=:{event_idem};BLOCK=:{block};EVENT_NAME=:{event_name}"
            return await self._send_message(payload)
        except Exception as e:
            raise EnSyncError(f"Failed to acknowledge event. {str(e)}", "EnSyncGenericError")
    
    async def _rollback(self, event_idem: str, block: str) -> str:
        """Roll back a record."""
        if not self._state["isAuthenticated"]:
            raise EnSyncError("Not authenticated", "EnSyncAuthError")
        
        try:
            payload = f"ROLLBACK;CLIENT_ID=:{self.__config['clientId']};EVENT_IDEM=:{event_idem};BLOCK=:{block}"
            return await self._send_message(payload)
        except Exception as e:
            raise EnSyncError(f"Failed to trigger rollback. {str(e)}", "EnSyncGenericError")
    
    async def _discard_event(self, event_id: str, event_name: str, reason: str = "") -> Dict[str, Any]:
        """Permanently discard an event."""
        if not self._state["isAuthenticated"]:
            raise EnSyncError("Not authenticated", "EnSyncAuthError")
        
        try:
            message = f"DISCARD;CLIENT_ID=:{self.__config['clientId']};EVENT_IDEM=:{event_id};EVENT_NAME=:{event_name};REASON=:{reason}"
            response = await self._send_message(message)
            
            if response.startswith("-FAIL:"):
                raise EnSyncError(response[6:], "EnSyncEventError")
            
            return {
                "status": "success",
                "action": "discarded",
                "eventId": event_id,
                "timestamp": int(asyncio.get_event_loop().time() * 1000)
            }
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
            message = f"DEFER;CLIENT_ID=:{self.__config['clientId']};EVENT_IDEM=:{event_id};EVENT_NAME=:{event_name};DELAY=:{delay_ms};REASON=:{reason}"
            response = await self._send_message(message)
            
            if response.startswith("-FAIL"):
                raise EnSyncError(response[6:], "EnSyncEventError")
            
            now = int(asyncio.get_event_loop().time() * 1000)
            return {
                "status": "success",
                "action": "deferred",
                "eventId": event_id,
                "delayMs": delay_ms,
                "scheduledDelivery": now + delay_ms,
                "timestamp": now
            }
        except Exception as error:
            if isinstance(error, EnSyncError):
                raise error
            raise EnSyncError(str(error), "EnSyncDeferError")
    
    async def _continue_processing(self, event_name: str) -> Dict[str, Any]:
        """Resume event processing."""
        if not self._state["isAuthenticated"]:
            raise EnSyncError("Not authenticated", "EnSyncAuthError")
        
        try:
            message = f"CONTINUE;CLIENT_ID=:{self.__config['clientId']};EVENT_NAME=:{event_name}"
            response = await self._send_message(message)
            
            if response.startswith("-FAIL:"):
                raise EnSyncError(response[6:], "EnSyncContinueError")
            
            return {
                "status": "success",
                "action": "continued",
                "eventName": event_name
            }
        except Exception as error:
            if isinstance(error, EnSyncError):
                raise error
            raise EnSyncError(str(error), "EnSyncContinueError")
    
    async def _pause_processing(self, event_name: str, reason: str = "") -> Dict[str, Any]:
        """Pause event processing."""
        if not self._state["isAuthenticated"]:
            raise EnSyncError("Not authenticated", "EnSyncAuthError")
        
        try:
            message = f"PAUSE;CLIENT_ID=:{self.__config['clientId']};EVENT_NAME=:{event_name};REASON=:{reason}"
            response = await self._send_message(message)
            
            if response.startswith("-FAIL:"):
                raise EnSyncError(response[6:], "EnSyncPauseError")
            
            return {
                "status": "success",
                "action": "paused",
                "eventName": event_name,
                "reason": reason or None
            }
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
            message = f"REPLAY;CLIENT_ID=:{self.__config['clientId']};EVENT_IDEM=:{event_idem};EVENT_NAME=:{event_name}"
            response = await self._send_message(message)
            
            if response.startswith("-FAIL:"):
                raise EnSyncError(response[6:], "EnSyncReplayError")
            
            return self._parse_and_decrypt_event(response, app_secret_key)
        except Exception as error:
            if isinstance(error, EnSyncError):
                raise error
            raise EnSyncError(str(error), "EnSyncReplayError")
    
    def get_client_public_key(self) -> str:
        """Get the client's public key (client hash)."""
        return self.__config.get("clientHash")
    
    async def close(self):
        """Close the WebSocket connection."""
        self._state["shouldReconnect"] = False
        self._clear_timers()
        
        if self._ws:
            await self._ws.close()