"""
Unit tests for XRPLAPIUserStreamDataSource.
"""
import asyncio
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from hummingbot.connector.exchange.xrpl.xrpl_api_user_stream_data_source import XRPLAPIUserStreamDataSource
from hummingbot.connector.exchange.xrpl.xrpl_auth import XRPLAuth
from hummingbot.connector.exchange.xrpl.xrpl_worker_manager import (
    RequestPriority,
    XRPLRequestType,
    XRPLWorkerPoolManager,
)


class TestXRPLAPIUserStreamDataSourceInit(unittest.TestCase):
    """Tests for XRPLAPIUserStreamDataSource initialization."""

    def test_init(self):
        """Test polling data source initializes correctly."""
        mock_auth = MagicMock(spec=XRPLAuth)
        mock_auth.get_account.return_value = "rTestAccount123"
        mock_connector = MagicMock()
        mock_worker_manager = MagicMock(spec=XRPLWorkerPoolManager)

        source = XRPLAPIUserStreamDataSource(
            auth=mock_auth,
            connector=mock_connector,
            worker_manager=mock_worker_manager,
        )

        self.assertEqual(source._auth, mock_auth)
        self.assertEqual(source._connector, mock_connector)
        self.assertEqual(source._worker_manager, mock_worker_manager)
        self.assertIsNone(source._last_ledger_index)
        self.assertEqual(source._last_recv_time, 0)

    def test_last_recv_time_property(self):
        """Test last_recv_time property."""
        mock_auth = MagicMock(spec=XRPLAuth)
        mock_connector = MagicMock()

        source = XRPLAPIUserStreamDataSource(
            auth=mock_auth,
            connector=mock_connector,
        )

        source._last_recv_time = 1000.5
        self.assertEqual(source.last_recv_time, 1000.5)


class TestXRPLAPIUserStreamDataSourceAsync(unittest.IsolatedAsyncioTestCase):
    """Async tests for XRPLAPIUserStreamDataSource."""

    async def test_listen_for_user_stream_cancellation(self):
        """Test listen_for_user_stream handles cancellation gracefully."""
        mock_auth = MagicMock(spec=XRPLAuth)
        mock_auth.get_account.return_value = "rTestAccount123"
        mock_connector = MagicMock()
        mock_worker_manager = MagicMock(spec=XRPLWorkerPoolManager)

        source = XRPLAPIUserStreamDataSource(
            auth=mock_auth,
            connector=mock_connector,
            worker_manager=mock_worker_manager,
        )

        output_queue = asyncio.Queue()

        # Mock _poll_account_state to track calls
        poll_count = 0

        async def mock_poll():
            nonlocal poll_count
            poll_count += 1
            return []

        with patch.object(source, '_poll_account_state', side_effect=mock_poll):
            with patch.object(source, 'POLL_INTERVAL', 0.1):  # Short interval
                task = asyncio.create_task(
                    source.listen_for_user_stream(output_queue)
                )

                # Let it run briefly
                await asyncio.sleep(0.3)

                # Cancel
                task.cancel()

                try:
                    await task
                except asyncio.CancelledError:
                    pass

                # Should have polled at least once
                self.assertGreater(poll_count, 0)

    async def test_poll_account_state_with_worker_manager(self):
        """Test _poll_account_state uses worker manager."""
        mock_auth = MagicMock(spec=XRPLAuth)
        mock_auth.get_account.return_value = "rTestAccount123"
        mock_connector = MagicMock()
        mock_worker_manager = MagicMock(spec=XRPLWorkerPoolManager)

        # Mock worker manager response
        mock_response = MagicMock()
        mock_response.result = {
            "account": "rTestAccount123",
            "ledger_index_max": 12345,
            "transactions": [],
        }
        mock_worker_manager.submit = AsyncMock(return_value=mock_response)

        source = XRPLAPIUserStreamDataSource(
            auth=mock_auth,
            connector=mock_connector,
            worker_manager=mock_worker_manager,
        )

        _ = await source._poll_account_state()

        # Verify worker manager was called
        mock_worker_manager.submit.assert_called_once()
        call_kwargs = mock_worker_manager.submit.call_args[1]
        self.assertEqual(call_kwargs["request_type"], XRPLRequestType.QUERY)
        self.assertEqual(call_kwargs["priority"], RequestPriority.MEDIUM)

    async def test_poll_account_state_updates_ledger_index(self):
        """Test _poll_account_state updates last_ledger_index."""
        mock_auth = MagicMock(spec=XRPLAuth)
        mock_auth.get_account.return_value = "rTestAccount123"
        mock_connector = MagicMock()
        mock_worker_manager = MagicMock(spec=XRPLWorkerPoolManager)

        # Mock worker manager response
        mock_response = MagicMock()
        mock_response.result = {
            "account": "rTestAccount123",
            "ledger_index_max": 12345,
            "transactions": [],
        }
        mock_worker_manager.submit = AsyncMock(return_value=mock_response)

        source = XRPLAPIUserStreamDataSource(
            auth=mock_auth,
            connector=mock_connector,
            worker_manager=mock_worker_manager,
        )

        await source._poll_account_state()

        self.assertEqual(source._last_ledger_index, 12345)

    async def test_poll_account_state_deduplicates_transactions(self):
        """Test _poll_account_state deduplicates seen transactions."""
        mock_auth = MagicMock(spec=XRPLAuth)
        mock_auth.get_account.return_value = "rTestAccount123"
        mock_connector = MagicMock()
        mock_worker_manager = MagicMock(spec=XRPLWorkerPoolManager)

        # Mock worker manager response with a transaction
        mock_response = MagicMock()
        mock_response.result = {
            "account": "rTestAccount123",
            "ledger_index_max": 12345,
            "transactions": [
                {
                    "tx": {"hash": "TX_HASH_123"},
                    "meta": {},
                    "validated": True,
                }
            ],
        }
        mock_worker_manager.submit = AsyncMock(return_value=mock_response)

        source = XRPLAPIUserStreamDataSource(
            auth=mock_auth,
            connector=mock_connector,
            worker_manager=mock_worker_manager,
        )

        # First poll - should return the transaction
        await source._poll_account_state()

        # Second poll - same transaction should be deduplicated
        await source._poll_account_state()

        # Transaction should be in seen set
        self.assertIn("TX_HASH_123", source._seen_tx_hashes_set)

    async def test_transform_to_event_offer_create(self):
        """Test _transform_to_event for OfferCreate transaction."""
        mock_auth = MagicMock(spec=XRPLAuth)
        mock_auth.get_account.return_value = "rTestAccount123"
        mock_connector = MagicMock()

        source = XRPLAPIUserStreamDataSource(
            auth=mock_auth,
            connector=mock_connector,
        )

        tx = {
            "hash": "TX_HASH_123",
            "TransactionType": "OfferCreate",
            "Account": "rTestAccount123",
            "Sequence": 12345,
            "TakerGets": {"currency": "USD", "value": "100", "issuer": "rIssuer"},
            "TakerPays": "50000000",  # 50 XRP in drops
        }
        meta = {
            "AffectedNodes": [],
            "TransactionResult": "tesSUCCESS",
        }
        tx_data = {
            "hash": "TX_HASH_123",
            "validated": True,
        }

        event = source._transform_to_event(tx, meta, tx_data)

        self.assertIsNotNone(event)
        self.assertEqual(event["hash"], "TX_HASH_123")

    async def test_transform_to_event_offer_cancel(self):
        """Test _transform_to_event for OfferCancel transaction."""
        mock_auth = MagicMock(spec=XRPLAuth)
        mock_auth.get_account.return_value = "rTestAccount123"
        mock_connector = MagicMock()

        source = XRPLAPIUserStreamDataSource(
            auth=mock_auth,
            connector=mock_connector,
        )

        tx = {
            "hash": "TX_HASH_456",
            "TransactionType": "OfferCancel",
            "Account": "rTestAccount123",
            "OfferSequence": 12344,
        }
        meta = {
            "AffectedNodes": [],
            "TransactionResult": "tesSUCCESS",
        }
        tx_data = {
            "hash": "TX_HASH_456",
            "validated": True,
        }

        event = source._transform_to_event(tx, meta, tx_data)

        self.assertIsNotNone(event)
        self.assertEqual(event["hash"], "TX_HASH_456")

    async def test_transform_to_event_payment(self):
        """Test _transform_to_event for Payment transaction."""
        mock_auth = MagicMock(spec=XRPLAuth)
        mock_auth.get_account.return_value = "rTestAccount123"
        mock_connector = MagicMock()

        source = XRPLAPIUserStreamDataSource(
            auth=mock_auth,
            connector=mock_connector,
        )

        tx = {
            "hash": "TX_HASH_789",
            "TransactionType": "Payment",
            "Account": "rOtherAccount",
            "Destination": "rTestAccount123",
            "Amount": "1000000",  # 1 XRP
        }
        meta = {
            "AffectedNodes": [],
            "TransactionResult": "tesSUCCESS",
        }
        tx_data = {
            "hash": "TX_HASH_789",
            "validated": True,
        }

        event = source._transform_to_event(tx, meta, tx_data)

        self.assertIsNotNone(event)
        self.assertEqual(event["hash"], "TX_HASH_789")

    async def test_seen_tx_hashes_cleanup(self):
        """Test that seen_tx_hashes is cleaned up when it gets too large."""
        mock_auth = MagicMock(spec=XRPLAuth)
        mock_auth.get_account.return_value = "rTestAccount123"
        mock_connector = MagicMock()

        source = XRPLAPIUserStreamDataSource(
            auth=mock_auth,
            connector=mock_connector,
        )

        # Set a small max size for testing
        source._seen_tx_hashes_max_size = 10

        # Add many hashes using the _is_duplicate method (which manages both queue and set)
        for i in range(15):
            source._is_duplicate(f"hash_{i}")

        # Verify the set was pruned to max size
        self.assertLessEqual(len(source._seen_tx_hashes_set), source._seen_tx_hashes_max_size)
        self.assertLessEqual(len(source._seen_tx_hashes_queue), source._seen_tx_hashes_max_size)

        # The oldest hashes should have been removed
        self.assertNotIn("hash_0", source._seen_tx_hashes_set)

        # The cleanup should keep the most recent hashes
        self.assertEqual(source._seen_tx_hashes_max_size, 10)


class TestXRPLAPIUserStreamDataSourceFallback(unittest.IsolatedAsyncioTestCase):
    """Tests for fallback behavior without worker manager."""

    async def test_poll_without_worker_manager(self):
        """Test _poll_account_state works without worker manager."""
        mock_auth = MagicMock(spec=XRPLAuth)
        mock_auth.get_account.return_value = "rTestAccount123"
        mock_connector = MagicMock()

        # Mock connector's _query_xrpl method
        mock_response = MagicMock()
        mock_response.result = {
            "account": "rTestAccount123",
            "ledger_index_max": 12345,
            "transactions": [],
        }
        mock_connector._query_xrpl = AsyncMock(return_value=mock_response)

        source = XRPLAPIUserStreamDataSource(
            auth=mock_auth,
            connector=mock_connector,
            worker_manager=None,  # No worker manager
        )

        await source._poll_account_state()

        # Should have used connector's _query_xrpl
        mock_connector._query_xrpl.assert_called_once()


if __name__ == "__main__":
    unittest.main()
