

"""
Aevo Perpetual User Stream Data Source

This module implements the user stream data source for the Aevo Perpetual connector.
It handles authenticated WebSocket connections for 'orders' and 'fills' channels.
"""

import asyncio
import logging
import time
from typing import Any, Dict, List, Optional

import aiohttp
import ujson

from hummingbot.connector.derivative.aevo_perpetual import (
    aevo_perpetual_constants as CONSTANTS,
    aevo_perpetual_web_utils as web_utils,
)
from hummingbot.connector.derivative.aevo_perpetual.aevo_perpetual_auth import AevoPerpetualAuth
from hummingbot.core.data_type.user_stream_tracker_data_source import UserStreamTrackerDataSource
from hummingbot.core.web_assistant.connections.data_types import WSJSONRequest, WSResponse
from hummingbot.core.web_assistant.web_assistants_factory import WebAssistantsFactory
from hummingbot.core.web_assistant.ws_assistant import WSAssistant
from hummingbot.logger import HummingbotLogger


class AevoPerpetualUserStreamDataSource(UserStreamTrackerDataSource):
    """
    Data source for Aevo Perpetual user stream (authenticated WebSocket).

    Handles subscription to:
    - orders: Real-time order updates (new, partial fill, filled, cancelled, etc.)
    - fills: Real-time trade fill notifications

    Uses AevoPerpetualAuth for WebSocket authentication via signing.
    """

    _logger: Optional[HummingbotLogger] = None
    _HEARTBEAT_INTERVAL = 15.0  # seconds between pings
    _RECONNECT_DELAY = 5.0  # seconds to wait before reconnecting

    def __init__(
        self,
        auth: AevoPerpetualAuth,
        trading_pairs: Optional[List[str]] = None,
        connector: Optional[Any] = None,
        api_factory: Optional[WebAssistantsFactory] = None,
        domain: str = CONSTANTS.DEFAULT_DOMAIN,
    ):
        """
        Initialize the user stream data source.

        :param auth: AevoPerpetualAuth instance for signing WebSocket messages
        :param trading_pairs: List of trading pairs to subscribe to
        :param connector: The parent connector instance
        :param api_factory: WebAssistantsFactory for creating web assistants
        :param domain: The domain to use (mainnet or testnet)
        """
        super().__init__()
        self._auth: AevoPerpetualAuth = auth
        self._trading_pairs = trading_pairs or []
        self._connector = connector
        self._api_factory = api_factory
        self._domain = domain
        self._ws_assistant: Optional[WSAssistant] = None
        self._last_recv_time: float = 0.0
        self._ping_task: Optional[asyncio.Task] = None
        self._subscription_channels = [
            CONSTANTS.WS_CHANNEL_ORDERS,
            CONSTANTS.WS_CHANNEL_FILLS,
        ]

    @classmethod
    def logger(cls) -> HummingbotLogger:
        if cls._logger is None:
            cls._logger = logging.getLogger(__name__)
        return cls._logger

    @property
    def last_recv_time(self) -> float:
        """
        Returns the time of the last received message.
        Used by the health monitor to determine if the connection is alive.
        """
        return self._last_recv_time

    async def _connected_websocket_assistant(self) -> WSAssistant:
        """
        Creates and returns an authenticated WebSocket assistant connected to Aevo's WS endpoint.

        The authentication flow for Aevo:
        1. Connect to the WebSocket endpoint
        2. Send an AUTH operation with API key, timestamp, and signature
        3. Wait for auth confirmation
        4. Subscribe to user-specific channels

        :return: An authenticated WSAssistant instance
        """
        ws_url = web_utils.wss_url(domain=self._domain)

        if self._api_factory is not None:
            ws: WSAssistant = await self._api_factory.get_ws_assistant()
        else:
            ws = WSAssistant(
                connection=None,
                throttler=None,
                ws_pre_processors=[],
                ws_post_processors=[],
            )

        await ws.connect(ws_url=ws_url, ping_timeout=self._HEARTBEAT_INTERVAL * 2)
        self.logger().info(f"Connected to Aevo WebSocket at {ws_url}")

        # Authenticate the WebSocket connection
        await self._authenticate(ws)

        return ws

    async def _authenticate(self, ws: WSAssistant):
        """
        Authenticates the WebSocket connection using the AevoPerpetualAuth instance.

        Aevo authentication requires sending:
        {
            "op": "auth",
            "data": {
                "key": "<api_key>",
                "secret": "<api_secret>",  // or signature-based
                "timestamp": <unix_timestamp>,
                "signature": "<signature>"
            }
        }

        :param ws: The WebSocket assistant to authenticate
        """
        try:
            auth_payload = self._auth.get_ws_auth_payload()

            auth_request = WSJSONRequest(
                payload=auth_payload,
                is_auth_required=False,  # The payload itself contains auth data
            )

            await ws.send(auth_request)
            self.logger().info("Sent authentication request to Aevo WebSocket")

            # Wait for auth response
            auth_response: WSResponse = await ws.receive()
            auth_data = auth_response.data if isinstance(auth_response.data, dict) else ujson.loads(auth_response.data)

            if self._is_auth_success(auth_data):
                self.logger().info("Successfully authenticated Aevo WebSocket connection")
                self._last_recv_time = time.time()
            else:
                error_msg = auth_data.get("data", {}).get("error", "Unknown error")
                raise IOError(
                    f"Failed to authenticate Aevo WebSocket connection. "
                    f"Error: {error_msg}. Response: {auth_data}"
                )

        except asyncio.TimeoutError:
            raise IOError("Timeout waiting for Aevo WebSocket authentication response")
        except Exception as e:
            self.logger().error(f"Error during Aevo WebSocket authentication: {e}", exc_info=True)
            raise

    def _is_auth_success(self, response: Dict[str, Any]) -> bool:
        """
        Checks if the authentication response indicates success.

        :param response: The parsed auth response from Aevo
        :return: True if authentication was successful
        """
        # Aevo returns {"id": ..., "data": "auth success"} or similar
        if isinstance(response, dict):
            # Check for explicit success
            data = response.get("data", "")
            if isinstance(data, str) and "success" in data.lower():
                return True
            # Check status field
            status = response.get("status", "")
            if status == "ok" or status == "success":
                return True
            # Check if no error is present (some implementations)
            if "error" not in response and response.get("op") == "auth":
                return True
            # Direct check for id-based auth confirmation
            if response.get("id") is not None and "error" not in str(response.get("data", "")):
                return True
        return False

    async def _subscribe_channels(self, ws: WSAssistant):
        """
        Subscribes to the user-specific channels (orders and fills) on the authenticated WebSocket.

        Aevo subscription format:
        {
            "op": "subscribe",
            "data": ["orders:<address>", "fills:<address>"]
        }

        :param ws: The authenticated WebSocket assistant
        """
        try:
            channels_to_subscribe = []

            for channel in self._subscription_channels:
                # Aevo uses channel names that may include the user's address
                # The auth object holds the necessary account info
                channel_name = self._auth.get_user_channel_name(channel)
                channels_to_subscribe.append(channel_name)

            subscribe_payload = {
                "op": "subscribe",
                "data": channels_to_subscribe,
            }

            subscribe_request = WSJSONRequest(payload=subscribe_payload)
            await ws.send(subscribe_request)

            self.logger().info(
                f"Subscribed to Aevo user stream channels: {channels_to_subscribe}"
            )

            # Wait for subscription confirmations
            for _ in range(len(channels_to_subscribe)):
                try:
                    response: WSResponse = await asyncio.wait_for(ws.receive(), timeout=10.0)
                    response_data = (
                        response.data if isinstance(response.data, dict) else ujson.loads(response.data)
                    )
                    self._last_recv_time = time.time()

                    if "error" in str(response_data.get("data", "")):
                        self.logger().warning(
                            f"Subscription warning from Aevo: {response_data}"
                        )
                    else:
                        self.logger().debug(
                            f"Subscription confirmation from Aevo: {response_data}"
                        )
                except asyncio.TimeoutError:
                    self.logger().warning(
                        "Timeout waiting for Aevo subscription confirmation. "
                        "Will continue - messages may still arrive."
                    )
                    break

        except asyncio.CancelledError:
            raise
        except Exception as e:
            self.logger().error(
                f"Error subscribing to Aevo user stream channels: {e}",
                exc_info=True,
            )
            raise

    async def _process_websocket_messages(self, websocket_assistant: WSAssistant, queue: asyncio.Queue):
        """
        Processes incoming WebSocket messages and puts relevant ones into the output queue.

        Handles:
        - Order updates from the 'orders' channel
        - Fill notifications from the 'fills' channel
        - Ping/pong for keepalive
        - Error messages

        :param websocket_assistant: The authenticated WebSocket assistant
        :param queue: The output queue for processed messages
        """
        while True:
            try:
                response: WSResponse = await websocket_assistant.receive()
                self._last_recv_time = time.time()

                if response.data is None:
                    continue

                data = (
                    response.data
                    if isinstance(response.data, dict)
                    else ujson.loads(response.data)
                )

                # Handle ping/pong keepalive
                if self._is_ping_message(data):
                    await self._send_pong(websocket_assistant, data)
                    continue

                # Filter for relevant channel messages
                channel = data.get("channel", "")

                if self._is_user_stream_message(channel, data):
                    queue.put_nowait(data)
                    self.logger().debug(f"Received user stream message on channel '{channel}'")
                elif "error" in str(data.get("data", "")):
                    self.logger().warning(f"Error message from Aevo WebSocket: {data}")
                else:
                    self.logger().debug(f"Ignoring non-user-stream message: {data}")

            except asyncio.TimeoutError:
                # Send a ping to keep the connection alive
                await self._send_ping(websocket_assistant)
            except asyncio.CancelledError:
                raise
            except ConnectionError as e:
                self.logger().warning(f"WebSocket connection error: {e}")
                raise
            except Exception as e:
                self.logger().error(
                    f"Unexpected error processing Aevo WebSocket message: {e}",
                    exc_info=True,
                )
                raise

    def _is_ping_message(self, data: Dict[str, Any]) -> bool:
        """
        Checks if the message is a ping from the server.

        :param data: The parsed message data
        :return: True if this is a ping message
        """
        return data.get("op") == "ping" or data.get("type") == "ping"

    def _is_user_stream_message(self, channel: str, data: Dict[str, Any]) -> bool:
        """
        Determines if a message is a relevant user stream update.

        :param channel: The channel name from the message
        :param data: The full message data
        :return: True if this is a user stream message
        """
        if not channel:
            return False

        # Check if the channel matches any of our subscribed channels
        for sub_channel in self._subscription_channels:
            if channel.startswith(sub_channel) or sub_channel in channel:
                return True

        # Also check for position updates that might come through
        if channel.startswith(CONSTANTS.WS_CHANNEL_POSITIONS):
            return True

        return False

    async def _send_ping(self, ws: WSAssistant):
        """
        Sends a ping message to keep the WebSocket connection alive.

        :param ws: The WebSocket assistant
        """
        try:
            ping_payload = {
                "op": "ping",
            }
            ping_request = WSJSONRequest(payload=ping_payload)
            await ws.send(ping_request)
            self.logger().debug("Sent ping to Aevo WebSocket")
        except Exception as e:
            self.logger().warning(f"Error sending ping to Aevo WebSocket: {e}")
            raise

    async def _send_pong(self, ws: WSAssistant, ping_data: Dict[str, Any]):
        """
        Sends a pong response to a server ping.

        :param ws: The WebSocket assistant
        :param ping_data: The original ping message data
        """
        try:
            pong_payload = {
                "op": "pong",
            }
            # Include any ID from the ping if present
            if "id" in ping_data:
                pong_payload["id"] = ping_data["id"]

            pong_request = WSJSONRequest(payload=pong_payload)
            await ws.send(pong_request)
            self.logger().debug("Sent pong to Aevo WebSocket")
        except Exception as e:
            self.logger().warning(f"Error sending pong to Aevo WebSocket: {e}")

    async def _on_user_stream_interruption(self, websocket_assistant: Optional[WSAssistant]):
        """
        Called when the user stream is interrupted. Handles cleanup.

        :param websocket_assistant: The WebSocket assistant that was interrupted
        """
        if self._ping_task is not None and not self._ping_task.done():
            self._ping_task.cancel()
            self._ping_task = None

        if websocket_assistant is not None:
            await websocket_assistant.disconnect()

        self._ws_assistant = None

    async def listen_for_user_stream(self, output: asyncio.Queue):
        """
        Main loop that listens for user stream events from Aevo.

        Manages the WebSocket lifecycle:
        1. Connect and authenticate
        2. Subscribe to channels
        3. Process messages
        4. Reconnect on failure

        :param output: The queue to put user stream messages into
        """
        ws: Optional[WSAssistant] = None

        while True:
            try:
                # Connect and authenticate
                ws = await self._connected_websocket_assistant()
                self._ws_assistant = ws

                # Subscribe to user channels
                await self._subscribe_channels(ws)

                # Start the heartbeat/ping task
                self._ping_task = asyncio.ensure_future(
                    self._periodic_ping(ws)
                )

                # Process messages
                await self._process_websocket_messages(
                    websocket_assistant=ws,
                    queue=output,
                )

            except asyncio.CancelledError:
                raise
            except ConnectionError as e:
                self.logger().warning(
                    f"Aevo user stream connection error: {e}. "
                    f"Reconnecting in {self._RECONNECT_DELAY}s..."
                )
            except IOError as e:
                self.logger().warning