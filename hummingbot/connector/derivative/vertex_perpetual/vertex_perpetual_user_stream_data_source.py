

"""
Vertex Perpetual User Stream Data Source

Handles authenticated WebSocket connections for user-specific updates including
fills, orders, and collateral changes on Vertex Protocol (Arbitrum).

Reference: https://docs.vertexprotocol.com/
"""

import asyncio
import json
import logging
import time
from typing import Any, Dict, List, Optional, Tuple

import aiohttp
from eth_account import Account
from eth_account.messages import encode_structured_data

from hummingbot.connector.derivative.vertex_perpetual import (
    vertex_perpetual_constants as CONSTANTS,
    vertex_perpetual_web_utils as web_utils,
)
from hummingbot.connector.derivative.vertex_perpetual.vertex_perpetual_auth import VertexPerpetualAuth
from hummingbot.core.data_type.user_stream_tracker_data_source import UserStreamTrackerDataSource
from hummingbot.core.web_assistant.connections.data_types import WSJSONRequest, WSResponse
from hummingbot.core.web_assistant.web_assistants_factory import WebAssistantsFactory
from hummingbot.core.web_assistant.ws_assistant import WSAssistant
from hummingbot.logger import HummingbotLogger


class VertexPerpetualUserStreamDataSource(UserStreamTrackerDataSource):
    """
    User stream data source for Vertex Perpetual connector.

    Connects to Vertex Protocol's WebSocket subscription endpoint and the Indexer
    to stream real-time user-specific data including:
    - Fill (trade execution) updates
    - Order status updates
    - Collateral (balance/position) updates

    Uses Arbitrum EIP-712 signing for authentication.
    """

    _logger: Optional[HummingbotLogger] = None
    HEARTBEAT_INTERVAL = 30.0
    ONE_HOUR = 3600

    @classmethod
    def logger(cls) -> HummingbotLogger:
        if cls._logger is None:
            cls._logger = logging.getLogger(__name__)
        return cls._logger

    def __init__(
        self,
        auth: VertexPerpetualAuth,
        trading_pairs: List[str],
        connector: Any,
        api_factory: WebAssistantsFactory,
        domain: str = CONSTANTS.DEFAULT_DOMAIN,
    ):
        """
        Initialize VertexPerpetualUserStreamDataSource.

        :param auth: Authentication handler with EIP-712 signing capabilities
        :param trading_pairs: List of trading pairs to track
        :param connector: Reference to the parent connector
        :param api_factory: Factory for creating web assistants
        :param domain: Domain for endpoint resolution (mainnet/testnet)
        """
        super().__init__()
        self._auth = auth
        self._trading_pairs = trading_pairs
        self._connector = connector
        self._api_factory = api_factory
        self._domain = domain
        self._ws_assistant: Optional[WSAssistant] = None
        self._last_recv_time: float = 0
        self._subscription_lock = asyncio.Lock()
        self._subscribed_channels: Dict[str, bool] = {
            "fills": False,
            "orders": False,
            "collateral": False,
        }
        self._ping_task: Optional[asyncio.Task] = None
        self._poll_task: Optional[asyncio.Task] = None

    @property
    def last_recv_time(self) -> float:
        """
        Returns the timestamp of the last received message.
        """
        return self._last_recv_time

    async def _connected_websocket_assistant(self) -> WSAssistant:
        """
        Creates and returns a connected WebSocket assistant for the user stream.

        Connects to the Vertex Protocol WebSocket subscription endpoint.

        :return: Connected WSAssistant instance
        """
        ws_url = web_utils.wss_url(CONSTANTS.WS_SUBSCRIPTION_ENDPOINT, self._domain)
        self.logger().info(f"Connecting to Vertex user stream WebSocket: {ws_url}")

        ws: WSAssistant = await self._api_factory.get_ws_assistant()
        await ws.connect(
            ws_url=ws_url,
            ping_timeout=CONSTANTS.WS_HEARTBEAT_TIME_INTERVAL,
        )

        self._last_recv_time = time.time()
        self.logger().info("Successfully connected to Vertex user stream WebSocket.")
        return ws

    async def _subscribe_channels(self, websocket_assistant: WSAssistant):
        """
        Subscribe to user-specific channels: fills, orders, and collateral.

        Uses EIP-712 signed authentication for the subscription requests.

        :param websocket_assistant: The connected WebSocket assistant
        """
        try:
            sender_address = self._auth.sender_address
            subaccount = self._get_subaccount()

            # Generate authentication signature for subscription
            auth_payload = await self._generate_auth_payload()

            # Subscribe to fill updates
            await self._subscribe_to_channel(
                websocket_assistant=websocket_assistant,
                channel="fills",
                subaccount=subaccount,
                auth_payload=auth_payload,
            )

            # Subscribe to order updates
            await self._subscribe_to_channel(
                websocket_assistant=websocket_assistant,
                channel="orders",
                subaccount=subaccount,
                auth_payload=auth_payload,
            )

            # Subscribe to collateral updates
            await self._subscribe_to_channel(
                websocket_assistant=websocket_assistant,
                channel="collateral",
                subaccount=subaccount,
                auth_payload=auth_payload,
            )

            self.logger().info(
                f"Successfully subscribed to Vertex user stream channels for subaccount: {subaccount}"
            )

        except asyncio.CancelledError:
            raise
        except Exception:
            self.logger().error(
                "Unexpected error occurred subscribing to Vertex user stream channels.",
                exc_info=True,
            )
            raise

    async def _subscribe_to_channel(
        self,
        websocket_assistant: WSAssistant,
        channel: str,
        subaccount: str,
        auth_payload: Dict[str, Any],
    ):
        """
        Subscribe to a specific channel on the Vertex WebSocket.

        :param websocket_assistant: Connected WebSocket assistant
        :param channel: Channel name (fills, orders, collateral)
        :param subaccount: Hex-encoded subaccount identifier
        :param auth_payload: EIP-712 authentication payload
        """
        subscribe_request = {
            "method": "subscribe",
            "stream": {
                "type": channel,
                "subaccount": subaccount,
            },
            "auth": auth_payload,
            "id": int(time.time() * 1000),
        }

        request = WSJSONRequest(payload=subscribe_request)
        await websocket_assistant.send(request)

        async with self._subscription_lock:
            self._subscribed_channels[channel] = True

        self.logger().info(f"Subscribed to Vertex '{channel}' channel.")

    async def _generate_auth_payload(self) -> Dict[str, Any]:
        """
        Generate an EIP-712 signed authentication payload for Vertex Protocol.

        Vertex uses Arbitrum (chain ID 42161 for mainnet, 421613 for testnet)
        EIP-712 structured data signing for WebSocket authentication.

        :return: Dictionary containing the authentication signature and related data
        """
        chain_id = CONSTANTS.CHAIN_IDS.get(self._domain, CONSTANTS.ARBITRUM_ONE_CHAIN_ID)
        verifying_contract = CONSTANTS.VERIFYING_CONTRACTS.get(self._domain, CONSTANTS.DEFAULT_VERIFYING_CONTRACT)

        expiration = int(time.time()) + self.ONE_HOUR
        sender = self._auth.sender_address
        subaccount = self._get_subaccount()

        # EIP-712 structured data for Vertex authentication
        structured_data = {
            "types": {
                "EIP712Domain": [
                    {"name": "name", "type": "string"},
                    {"name": "version", "type": "string"},
                    {"name": "chainId", "type": "uint256"},
                    {"name": "verifyingContract", "type": "address"},
                ],
                "StreamAuthentication": [
                    {"name": "sender", "type": "bytes32"},
                    {"name": "expiration", "type": "uint64"},
                ],
            },
            "primaryType": "StreamAuthentication",
            "domain": {
                "name": "Vertex",
                "version": "0.0.1",
                "chainId": chain_id,
                "verifyingContract": verifying_contract,
            },
            "message": {
                "sender": subaccount,
                "expiration": expiration,
            },
        }

        signature = self._auth.sign_eip712_message(structured_data)

        auth_payload = {
            "sender": subaccount,
            "expiration": expiration,
            "signature": signature,
        }

        return auth_payload

    def _get_subaccount(self) -> str:
        """
        Get the hex-encoded subaccount identifier for the authenticated user.

        Vertex uses a 32-byte subaccount which is the sender address padded
        with the subaccount name (default "default" subaccount = bytes12(0)).

        :return: Hex-encoded 32-byte subaccount string
        """
        sender_address = self._auth.sender_address
        # Default subaccount: address + 12 zero bytes
        subaccount_name = getattr(self._auth, '_subaccount_name', "default")

        if subaccount_name == "default":
            # Default subaccount: sender address (20 bytes) + 12 zero bytes
            subaccount_bytes = bytes.fromhex(sender_address[2:]) + b'\x00' * 12
        else:
            # Named subaccount: sender address + padded name
            name_bytes = subaccount_name.encode('utf-8')[:12].ljust(12, b'\x00')
            subaccount_bytes = bytes.fromhex(sender_address[2:]) + name_bytes

        return "0x" + subaccount_bytes.hex()

    async def _process_websocket_messages(self, websocket_assistant: WSAssistant, queue: asyncio.Queue):
        """
        Process incoming WebSocket messages and place them in the output queue.

        Handles the following message types:
        - fill: Trade execution updates
        - order: Order status changes
        - collateral: Balance and position updates
        - subscription_response: Confirmation of channel subscriptions
        - ping/pong: Connection keepalive

        :param websocket_assistant: Connected WebSocket assistant
        :param queue: Output queue for processed messages
        """
        while True:
            try:
                response: WSResponse = await websocket_assistant.receive()
                self._last_recv_time = time.time()

                if response is None:
                    continue

                data = response.data

                if isinstance(data, str):
                    try:
                        data = json.loads(data)
                    except json.JSONDecodeError:
                        self.logger().warning(f"Failed to decode WebSocket message: {data}")
                        continue

                if not isinstance(data, dict):
                    self.logger().debug(f"Unexpected message format: {data}")
                    continue

                # Handle different message types
                msg_type = data.get("type", "")

                if msg_type == "pong":
                    # Heartbeat response, no action needed
                    continue

                if msg_type == "subscription_response" or msg_type == "subscribed":
                    # Subscription confirmation
                    status = data.get("status", "unknown")
                    channel = data.get("stream", {}).get("type", "unknown")
                    self.logger().info(
                        f"Vertex subscription response for '{channel}': {status}"
                    )
                    continue

                if msg_type == "error":
                    error_msg = data.get("error", "Unknown error")
                    self.logger().error(f"Vertex WebSocket error: {error_msg}")
                    continue

                # Process user data messages
                if msg_type in ("fill", "fills"):
                    processed_msg = self._process_fill_message(data)
                    if processed_msg:
                        queue.put_nowait(processed_msg)

                elif msg_type in ("order", "orders", "order_update"):
                    processed_msg = self._process_order_message(data)
                    if processed_msg:
                        queue.put_nowait(processed_msg)

                elif msg_type in ("collateral", "collateral_update", "position_change"):
                    processed_msg = self._process_collateral_message(data)
                    if processed_msg:
                        queue.put_nowait(processed_msg)

                else:
                    # For any other message types, pass them through
                    # This handles potential future message types
                    if "data" in data or "result" in data:
                        queue.put_nowait(data)
                    else:
                        self.logger().debug(f"Unhandled Vertex message type: {msg_type}, data: {data}")

            except asyncio.TimeoutError:
                # Send ping to keep connection alive
                await self._send_ping(websocket_assistant)
            except asyncio.CancelledError:
                raise
            except ConnectionError:
                self.logger().warning("WebSocket connection lost in user stream.")
                raise
            except Exception:
                self.logger().error(
                    "Unexpected error processing Vertex user stream message.",
                    exc_info=True,
                )
                raise

    def _process_fill_message(self, raw_message: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Process a fill (trade execution) message from Vertex WebSocket.

        :param raw_message: Raw WebSocket message
        :return: Processed fill message or None if invalid
        """
        try:
            fill_data = raw_message.get("data", raw_message)

            processed = {
                "type": "fill",
                "data": fill_data,
                "timestamp": time.time(),
                "raw": raw_message,
            }

            # Extract key fill fields for logging
            product_id = fill_data.get("product_id", "unknown")
            order_digest = fill_data.get("order_digest", fill_data.get("digest", "unknown"))
            filled_qty = fill_data.get("filled_qty", fill_data.get("amount", "unknown"))
            price = fill_data.get("price", "unknown")

            self.logger().info(
                f"Vertex fill received - product: {product_id}, "
                f"digest: {order_digest}, qty: {filled_qty}, price: {price}"
            )

            return processed

        except Exception:
            self.logger().error(
                f"Error processing Vertex fill message: {raw_message}",
                exc_info=True,
            )
            return None

    def _process_order_message(self, raw_message: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Process an order status update message from Vertex WebSocket.

        :param raw_message: Raw WebSocket message
        :return: Processed order message or None if invalid
        """
        try:
            order_data = raw_message.get("data", raw_message)

            processed = {
                "type": "order",
                "data": order_data,
                "timestamp": time.time(),
                "raw": raw_message,
            }

            # Extract key order fields for logging
            order_digest = order_data.get("order_digest", order_data.get("digest", "unknown"))
            status = order_data.get("status", "unknown")
            product_id = order_data.get("product_id", "unknown")

            self.logger().info(
                f"Vertex order update - product: {product_id}, "
                f"digest: {order_digest}, status: {status}"
            )

            return processed

        except Exception:
            self.logger().error(
                f"Error processing Vertex order message: {raw_message