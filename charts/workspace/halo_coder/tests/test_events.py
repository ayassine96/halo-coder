"""Tests for the halo_coder.events module."""

from __future__ import annotations

import threading
import unittest

from halo_coder.events import EventBroker, create_event_bus
from halo_coder.protocols import DomainEvent, EventBus


class TestEventBroker(unittest.TestCase):
    def setUp(self) -> None:
        self.broker = EventBroker()

    def test_subscribe_returns_queue(self) -> None:
        q = self.broker.subscribe()
        self.assertIsNotNone(q)

    def test_subscriber_count_zero_initially(self) -> None:
        self.assertEqual(self.broker.subscriber_count(), 0)

    def test_subscriber_count_increments(self) -> None:
        self.broker.subscribe()
        self.assertEqual(self.broker.subscriber_count(), 1)

    def test_unsubscribe_removes_subscriber(self) -> None:
        q = self.broker.subscribe()
        self.broker.unsubscribe(q)
        self.assertEqual(self.broker.subscriber_count(), 0)

    def test_unsubscribe_nonexistent_no_error(self) -> None:
        import queue
        q = queue.Queue()
        self.broker.unsubscribe(q)  # should not raise

    def test_publish_without_data(self) -> None:
        evt = self.broker.publish("test.type")
        self.assertIsInstance(evt, DomainEvent)
        self.assertEqual(evt.type, "test.type")
        self.assertEqual(evt.data, {})
        self.assertGreater(evt.ts, 0)

    def test_publish_with_data(self) -> None:
        evt = self.broker.publish("task.status", {"task_id": "t1", "status": "ok"})
        self.assertEqual(evt.type, "task.status")
        self.assertEqual(evt.data["task_id"], "t1")
        self.assertEqual(evt.data["status"], "ok")

    def test_subscriber_receives_event(self) -> None:
        q = self.broker.subscribe()
        self.broker.publish("spec.update", {"spec_id": "s1"})
        evt = q.get_nowait()
        self.assertEqual(evt.type, "spec.update")
        self.assertEqual(evt.data["spec_id"], "s1")

    def test_event_contains_timestamp(self) -> None:
        q = self.broker.subscribe()
        self.broker.publish("x")
        evt = q.get_nowait()
        self.assertIsInstance(evt.ts, float)
        self.assertGreater(evt.ts, 0)

    def test_fan_out_to_multiple_subscribers(self) -> None:
        q1 = self.broker.subscribe()
        q2 = self.broker.subscribe()
        self.broker.publish("multi", {"idx": 1})
        self.assertEqual(q1.get_nowait().data["idx"], 1)
        self.assertEqual(q2.get_nowait().data["idx"], 1)

    def test_publish_never_raises_with_no_subscribers(self) -> None:
        self.broker.publish("solo", {"ok": True})  # should not raise

    def test_unsubscribed_queue_no_longer_receives(self) -> None:
        q = self.broker.subscribe()
        self.broker.unsubscribe(q)
        self.broker.publish("after", {"x": 1})
        import queue
        with self.assertRaises(queue.Empty):
            q.get_nowait()

    def test_queue_full_evicts_oldest(self) -> None:
        broker = EventBroker(queue_max=3)
        q = broker.subscribe()
        broker.publish("a", {"n": 1})
        broker.publish("b", {"n": 2})
        broker.publish("c", {"n": 3})
        # queue is now full
        broker.publish("d", {"n": 4})
        # oldest event ("a") should be evicted
        self.assertEqual(q.get_nowait().data["n"], 2)
        self.assertEqual(q.get_nowait().data["n"], 3)
        self.assertEqual(q.get_nowait().data["n"], 4)
        import queue
        with self.assertRaises(queue.Empty):
            q.get_nowait()

    def test_concurrent_publish(self) -> None:
        q = self.broker.subscribe()
        errors: list[Exception] = []

        def _publish(n: int) -> None:
            try:
                self.broker.publish(f"concurrent.{n}", {"n": n})
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=_publish, args=(i,)) for i in range(50)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(len(errors), 0)
        received = 0
        import queue
        while True:
            try:
                evt = q.get_nowait()
                received += 1
                self.assertTrue(evt.type.startswith("concurrent."))
            except queue.Empty:
                break
        self.assertGreaterEqual(received, 1)

    def test_unsubscribe_is_idempotent(self) -> None:
        q = self.broker.subscribe()
        self.broker.unsubscribe(q)
        self.broker.unsubscribe(q)  # should not raise
        self.assertEqual(self.broker.subscriber_count(), 0)

    def test_isinstance_eventbus(self) -> None:
        self.assertIsInstance(self.broker, EventBus)


class TestCreateEventBus(unittest.TestCase):
    def test_returns_eventbus(self) -> None:
        bus = create_event_bus()
        self.assertIsInstance(bus, EventBus)
        self.assertIsInstance(bus, EventBroker)

    def test_custom_queue_max(self) -> None:
        bus = create_event_bus(queue_max=50)
        q = bus.subscribe()
        self.assertEqual(q.maxsize, 50)
