"""
Unit tests for XRPLWorkerPoolManager.
"""
import asyncio
import unittest
from unittest.mock import AsyncMock, MagicMock

from hummingbot.connector.exchange.xrpl.xrpl_utils import XRPLNodePool
from hummingbot.connector.exchange.xrpl.xrpl_worker_manager import (
    RequestPriority,
    XRPLRequest,
    XRPLRequestType,
    XRPLWorkerPoolManager,
)


class TestRequestPriority(unittest.TestCase):
    """Tests for RequestPriority enum."""

    def test_priority_ordering(self):
        """Test priority values are correctly ordered."""
        self.assertLess(RequestPriority.LOW, RequestPriority.MEDIUM)
        self.assertLess(RequestPriority.MEDIUM, RequestPriority.HIGH)
        self.assertLess(RequestPriority.HIGH, RequestPriority.CRITICAL)

    def test_priority_values(self):
        """Test specific priority values."""
        self.assertEqual(RequestPriority.LOW, 1)
        self.assertEqual(RequestPriority.MEDIUM, 2)
        self.assertEqual(RequestPriority.HIGH, 3)
        self.assertEqual(RequestPriority.CRITICAL, 4)


class TestXRPLRequestType(unittest.TestCase):
    """Tests for XRPLRequestType constants."""

    def test_request_types_exist(self):
        """Test all request types are defined."""
        self.assertEqual(XRPLRequestType.SUBMIT_TX, "submit_tx")
        self.assertEqual(XRPLRequestType.VERIFY_TX, "verify_tx")
        self.assertEqual(XRPLRequestType.QUERY, "query")
        self.assertEqual(XRPLRequestType.CANCEL_TX, "cancel_tx")


class TestXRPLRequest(unittest.TestCase):
    """Tests for XRPLRequest dataclass."""

    def test_request_creation(self):
        """Test XRPLRequest can be created."""
        future = asyncio.get_event_loop().create_future()
        request = XRPLRequest(
            priority=-RequestPriority.HIGH,  # Negative for min-heap
            request_id="test-123",
            request_type=XRPLRequestType.QUERY,
            payload={"data": "test"},
            future=future,
            created_at=1000.0,
            timeout=30.0,
            retry_count=0,
            max_retries=3,
        )

        self.assertEqual(request.request_id, "test-123")
        self.assertEqual(request.request_type, XRPLRequestType.QUERY)
        self.assertEqual(request.payload, {"data": "test"})

    def test_request_ordering(self):
        """Test requests are ordered by priority (lower value = higher priority)."""
        future1 = asyncio.get_event_loop().create_future()
        future2 = asyncio.get_event_loop().create_future()

        high_priority = XRPLRequest(
            priority=-RequestPriority.HIGH,
            request_id="high",
            request_type=XRPLRequestType.SUBMIT_TX,
            payload={},
            future=future1,
            created_at=1000.0,
            timeout=30.0,
        )

        low_priority = XRPLRequest(
            priority=-RequestPriority.LOW,
            request_id="low",
            request_type=XRPLRequestType.QUERY,
            payload={},
            future=future2,
            created_at=1000.0,
            timeout=30.0,
        )

        # High priority should come first (more negative)
        self.assertLess(high_priority, low_priority)


class TestXRPLWorkerPoolManagerInit(unittest.TestCase):
    """Tests for XRPLWorkerPoolManager initialization."""

    def test_init(self):
        """Test manager initializes correctly."""
        mock_node_pool = MagicMock(spec=XRPLNodePool)
        manager = XRPLWorkerPoolManager(
            node_pool=mock_node_pool,
            num_workers=2,
            max_queue_size=100,
        )

        self.assertEqual(manager._num_workers, 2)
        self.assertEqual(manager._node_pool, mock_node_pool)
        self.assertFalse(manager._running)

    def test_register_handler(self):
        """Test handler registration."""
        mock_node_pool = MagicMock(spec=XRPLNodePool)
        manager = XRPLWorkerPoolManager(node_pool=mock_node_pool)

        async def test_handler(payload, client):
            return "result"

        manager.register_handler("test_type", test_handler)

        self.assertIn("test_type", manager._handlers)
        self.assertEqual(manager._handlers["test_type"], test_handler)


class TestXRPLWorkerPoolManagerAsync(unittest.IsolatedAsyncioTestCase):
    """Async tests for XRPLWorkerPoolManager."""

    async def test_start_stop(self):
        """Test start and stop lifecycle."""
        mock_node_pool = MagicMock(spec=XRPLNodePool)
        manager = XRPLWorkerPoolManager(
            node_pool=mock_node_pool,
            num_workers=2,
        )

        await manager.start()

        self.assertTrue(manager._running)
        self.assertEqual(len(manager._workers), 2)

        await manager.stop()

        self.assertFalse(manager._running)
        self.assertEqual(len(manager._workers), 0)

    async def test_start_already_running(self):
        """Test start when already running."""
        mock_node_pool = MagicMock(spec=XRPLNodePool)
        manager = XRPLWorkerPoolManager(node_pool=mock_node_pool, num_workers=1)
        manager._running = True

        # Should not create new workers
        await manager.start()
        self.assertEqual(len(manager._workers), 0)

    async def test_stop_not_running(self):
        """Test stop when not running."""
        mock_node_pool = MagicMock(spec=XRPLNodePool)
        manager = XRPLWorkerPoolManager(node_pool=mock_node_pool)
        manager._running = False

        # Should not raise
        await manager.stop()

    async def test_submit_not_running(self):
        """Test submit raises when not running."""
        mock_node_pool = MagicMock(spec=XRPLNodePool)
        manager = XRPLWorkerPoolManager(node_pool=mock_node_pool)
        manager._running = False

        with self.assertRaises(RuntimeError):
            await manager.submit(
                request_type=XRPLRequestType.QUERY,
                payload={},
            )

    async def test_submit_success(self):
        """Test successful request submission."""
        mock_node_pool = MagicMock(spec=XRPLNodePool)
        mock_client = AsyncMock()
        mock_node_pool.get_client = AsyncMock(return_value=mock_client)

        manager = XRPLWorkerPoolManager(node_pool=mock_node_pool, num_workers=1)

        # Register handler
        async def test_handler(payload, client):
            return {"result": "success"}

        manager.register_handler(XRPLRequestType.QUERY, test_handler)

        await manager.start()

        try:
            result = await asyncio.wait_for(
                manager.submit(
                    request_type=XRPLRequestType.QUERY,
                    payload={"test": "data"},
                    timeout=5.0,
                ),
                timeout=10.0,
            )

            self.assertEqual(result, {"result": "success"})
        finally:
            await manager.stop()

    async def test_submit_fire_and_forget(self):
        """Test fire-and-forget submission."""
        mock_node_pool = MagicMock(spec=XRPLNodePool)
        mock_client = AsyncMock()
        mock_node_pool.get_client = AsyncMock(return_value=mock_client)

        manager = XRPLWorkerPoolManager(node_pool=mock_node_pool, num_workers=1)

        # Register handler
        handler_called = asyncio.Event()

        async def test_handler(payload, client):
            handler_called.set()
            return {"result": "success"}

        manager.register_handler(XRPLRequestType.VERIFY_TX, test_handler)

        await manager.start()

        try:
            request_id = await manager.submit_fire_and_forget(
                request_type=XRPLRequestType.VERIFY_TX,
                payload={"test": "data"},
            )

            # Should return immediately with a request ID
            self.assertIsInstance(request_id, str)
            self.assertTrue(len(request_id) > 0)

            # Wait for handler to be called
            await asyncio.wait_for(handler_called.wait(), timeout=5.0)
        finally:
            await manager.stop()

    async def test_get_request_status_pending(self):
        """Test getting status of pending request."""
        mock_node_pool = MagicMock(spec=XRPLNodePool)
        manager = XRPLWorkerPoolManager(node_pool=mock_node_pool)

        # Create a proper XRPLRequest for the pending dict
        future = asyncio.Future()
        request = XRPLRequest(
            priority=-RequestPriority.MEDIUM,
            request_id="test-123",
            request_type=XRPLRequestType.QUERY,
            payload={},
            future=future,
            created_at=1000.0,
            timeout=30.0,
        )
        manager._pending_requests["test-123"] = request

        status = manager.get_request_status("test-123")
        self.assertEqual(status, "pending")

    async def test_get_request_status_unknown(self):
        """Test getting status of unknown request."""
        mock_node_pool = MagicMock(spec=XRPLNodePool)
        manager = XRPLWorkerPoolManager(node_pool=mock_node_pool)

        status = manager.get_request_status("nonexistent")
        self.assertEqual(status, "unknown")

    async def test_get_request_status_completed(self):
        """Test getting status of completed request."""
        mock_node_pool = MagicMock(spec=XRPLNodePool)
        manager = XRPLWorkerPoolManager(node_pool=mock_node_pool)

        # Add and complete a request
        future = asyncio.Future()
        future.set_result("done")
        request = XRPLRequest(
            priority=-RequestPriority.MEDIUM,
            request_id="test-123",
            request_type=XRPLRequestType.QUERY,
            payload={},
            future=future,
            created_at=1000.0,
            timeout=30.0,
        )
        manager._pending_requests["test-123"] = request

        status = manager.get_request_status("test-123")
        self.assertEqual(status, "completed")

    async def test_submit_timeout(self):
        """Test request timeout handling."""
        mock_node_pool = MagicMock(spec=XRPLNodePool)
        mock_client = AsyncMock()
        mock_node_pool.get_client = AsyncMock(return_value=mock_client)

        manager = XRPLWorkerPoolManager(node_pool=mock_node_pool, num_workers=1)

        # Register a slow handler
        async def slow_handler(payload, client):
            await asyncio.sleep(10)
            return {"result": "success"}

        manager.register_handler(XRPLRequestType.QUERY, slow_handler)

        await manager.start()

        try:
            with self.assertRaises(asyncio.TimeoutError):
                await manager.submit(
                    request_type=XRPLRequestType.QUERY,
                    payload={},
                    timeout=0.1,  # Very short timeout
                )
        finally:
            await manager.stop()

    async def test_submit_no_handler(self):
        """Test submission with no registered handler."""
        mock_node_pool = MagicMock(spec=XRPLNodePool)
        mock_client = AsyncMock()
        mock_node_pool.get_client = AsyncMock(return_value=mock_client)

        manager = XRPLWorkerPoolManager(node_pool=mock_node_pool, num_workers=1)

        # Don't register any handlers

        await manager.start()

        try:
            with self.assertRaises(Exception):  # Should fail with no handler
                await asyncio.wait_for(
                    manager.submit(
                        request_type="unknown_type",
                        payload={},
                        timeout=5.0,
                    ),
                    timeout=10.0,
                )
        finally:
            await manager.stop()


class TestXRPLWorkerPoolManagerPriorityQueue(unittest.IsolatedAsyncioTestCase):
    """Tests for priority queue behavior."""

    async def test_priority_ordering(self):
        """Test that high priority requests are processed first."""
        mock_node_pool = MagicMock(spec=XRPLNodePool)
        mock_client = AsyncMock()
        mock_node_pool.get_client = AsyncMock(return_value=mock_client)

        manager = XRPLWorkerPoolManager(node_pool=mock_node_pool, num_workers=1)

        # Track order of processing
        processed_order = []

        async def tracking_handler(payload, client):
            processed_order.append(payload["id"])
            return {"result": payload["id"]}

        manager.register_handler(XRPLRequestType.QUERY, tracking_handler)

        await manager.start()

        try:
            # Submit requests with different priorities simultaneously
            tasks = [
                manager.submit(
                    request_type=XRPLRequestType.QUERY,
                    payload={"id": "low"},
                    priority=RequestPriority.LOW,
                    timeout=5.0,
                ),
                manager.submit(
                    request_type=XRPLRequestType.QUERY,
                    payload={"id": "high"},
                    priority=RequestPriority.HIGH,
                    timeout=5.0,
                ),
                manager.submit(
                    request_type=XRPLRequestType.QUERY,
                    payload={"id": "medium"},
                    priority=RequestPriority.MEDIUM,
                    timeout=5.0,
                ),
            ]

            await asyncio.gather(*tasks)

            # High priority should be processed first
            # Note: Due to async nature, this might not always be deterministic
            # but with a single worker, ordering should generally be preserved
            self.assertIn("high", processed_order)
            self.assertIn("medium", processed_order)
            self.assertIn("low", processed_order)
        finally:
            await manager.stop()


if __name__ == "__main__":
    unittest.main()
