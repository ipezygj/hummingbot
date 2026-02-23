

"""Authentication module for Aevo Perpetual connector."""

import hashlib
import hmac
import time
from typing import Any, Dict, Optional

from hummingbot.connector.time_synchronizer import TimeSynchronizer
from hummingbot.core.web_assistant.auth import AuthBase
from hummingbot.core.web_assistant.connections.data_types import RESTRequest, WSRequest


class AevoPerpetualAuth(AuthBase):
    """
    Authentication class for Aevo Perpetual exchange.
    Implements HMAC-SHA256 signing for both REST and WebSocket requests.
    
    Headers used:
    - AEG-KEY: The API key
    - AEG-SIGN: The HMAC-SHA256 signature
    - AEG-TS: The timestamp of the request
    """

    def __init__(
        self,
        api_key: str,
        api_secret: str,
        time_provider: Optional[TimeSynchronizer] = None,
    ):
        """
        Initialize AevoPerpetualAuth.

        :param api_key: The API key for Aevo.
        :param api_secret: The API secret for Aevo.
        :param time_provider: Optional TimeSynchronizer instance for synchronized timestamps.
        """
        self._api_key: str = api_key
        self._api_secret: str = api_secret
        self._time_provider: Optional[TimeSynchronizer] = time_provider

    @property
    def api_key(self) -> str:
        """Return the API key."""
        return self._api_key

    @property
    def api_secret(self) -> str:
        """Return the API secret."""
        return self._api_secret

    def _get_timestamp(self) -> str:
        """
        Get the current timestamp as a string.
        Uses the time provider if available, otherwise falls back to system time.

        :return: Current timestamp in seconds as a string.
        """
        if self._time_provider is not None:
            try:
                timestamp = str(int(self._time_provider.time()))
            except Exception:
                timestamp = str(int(time.time()))
        else:
            timestamp = str(int(time.time()))
        return timestamp

    def _generate_signature(self, timestamp: str, method: str, request_path: str, body: str = "") -> str:
        """
        Generate HMAC-SHA256 signature for authentication.

        The signature is computed over: timestamp + method + request_path + body

        :param timestamp: The timestamp string.
        :param method: The HTTP method (GET, POST, DELETE, etc.) in uppercase.
        :param request_path: The request path (e.g., /api/v1/orders).
        :param body: The request body as a string (empty string if no body).
        :return: The hex-encoded HMAC-SHA256 signature.
        """
        message = f"{timestamp}{method}{request_path}{body}"
        signature = hmac.new(
            self._api_secret.encode("utf-8"),
            message.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        return signature

    def _get_auth_headers(self, timestamp: str, signature: str) -> Dict[str, str]:
        """
        Build the authentication headers dictionary.

        :param timestamp: The timestamp string.
        :param signature: The HMAC-SHA256 signature.
        :return: Dictionary containing authentication headers.
        """
        return {
            "AEG-KEY": self._api_key,
            "AEG-SIGN": signature,
            "AEG-TS": timestamp,
        }

    async def rest_authenticate(self, request: RESTRequest) -> RESTRequest:
        """
        Authenticate a REST request by adding authentication headers.

        Constructs the signature from the HTTP method, URL path, query parameters,
        and request body, then adds the required headers.

        :param request: The RESTRequest to authenticate.
        :return: The authenticated RESTRequest with auth headers added.
        """
        timestamp = self._get_timestamp()

        # Extract the path from the URL
        url_str = str(request.url) if request.url else ""
        request_path = self._extract_path(url_str)

        # Determine HTTP method
        method = request.method.name if request.method else "GET"
        method = method.upper()

        # Build the body string
        body = ""
        if request.data is not None:
            if isinstance(request.data, str):
                body = request.data
            elif isinstance(request.data, dict):
                import json
                body = json.dumps(request.data, separators=(",", ":"))
            else:
                body = str(request.data)

        # Generate signature
        signature = self._generate_signature(
            timestamp=timestamp,
            method=method,
            request_path=request_path,
            body=body,
        )

        # Add auth headers
        auth_headers = self._get_auth_headers(timestamp=timestamp, signature=signature)

        if request.headers is None:
            request.headers = {}
        request.headers.update(auth_headers)

        return request

    async def ws_authenticate(self, request: WSRequest) -> WSRequest:
        """
        Authenticate a WebSocket request by adding authentication payload.

        For WebSocket connections, the authentication data is typically sent as
        part of the initial message payload.

        :param request: The WSRequest to authenticate.
        :return: The authenticated WSRequest with auth data added.
        """
        timestamp = self._get_timestamp()

        # For WebSocket authentication, sign with empty path and body or
        # use a predefined auth channel path
        ws_auth_path = "/ws/auth"
        method = "GET"

        signature = self._generate_signature(
            timestamp=timestamp,
            method=method,
            request_path=ws_auth_path,
            body="",
        )

        # Add authentication headers to the WS request if headers are supported
        if request.headers is None:
            request.headers = {}
        auth_headers = self._get_auth_headers(timestamp=timestamp, signature=signature)
        request.headers.update(auth_headers)

        return request

    def get_ws_auth_payload(self) -> Dict[str, Any]:
        """
        Generate the authentication payload for WebSocket subscription.

        This payload is sent as a message after the WebSocket connection is
        established to authenticate the session.

        :return: Dictionary containing the WebSocket authentication message.
        """
        timestamp = self._get_timestamp()
        ws_auth_path = "/ws/auth"
        method = "GET"

        signature = self._generate_signature(
            timestamp=timestamp,
            method=method,
            request_path=ws_auth_path,
            body="",
        )

        return {
            "op": "auth",
            "data": {
                "key": self._api_key,
                "sign": signature,
                "timestamp": timestamp,
            },
        }

    def generate_ws_signature(self, timestamp: Optional[str] = None) -> Dict[str, str]:
        """
        Generate WebSocket authentication signature components.

        Useful for constructing custom WebSocket auth messages.

        :param timestamp: Optional timestamp override.
        :return: Dictionary with key, sign, and timestamp.
        """
        if timestamp is None:
            timestamp = self._get_timestamp()

        ws_auth_path = "/ws/auth"
        method = "GET"

        signature = self._generate_signature(
            timestamp=timestamp,
            method=method,
            request_path=ws_auth_path,
            body="",
        )

        return {
            "key": self._api_key,
            "sign": signature,
            "timestamp": timestamp,
        }

    @staticmethod
    def _extract_path(url: str) -> str:
        """
        Extract the path (including query string) from a full URL.

        :param url: The full URL string.
        :return: The path component of the URL including query parameters.
        """
        if not url:
            return "/"

        # Handle full URLs
        if "://" in url:
            from urllib.parse import urlparse
            parsed = urlparse(url)
            path = parsed.path
            if parsed.query:
                path = f"{path}?{parsed.query}"
            return path if path else "/"

        # Already a path
        return url if url.startswith("/") else f"/{url}"
