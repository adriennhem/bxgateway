import time

from mock import MagicMock

from bxcommon.constants import LOCALHOST
from bxcommon.test_utils import helpers
from bxcommon.test_utils.abstract_test_case import AbstractTestCase
from bxcommon.test_utils.mocks.mock_connection import MockConnection
from bxcommon.test_utils.mocks.mock_socket_connection import MockSocketConnection
from bxcommon.utils import crypto
from bxcommon.utils.alarm_queue import AlarmQueue
from bxcommon.utils.object_hash import Sha256ObjectHash
from bxcommon.messages.bloxroute.block_holding_message import BlockHoldingMessage
from bxgateway.services.block_processing_service import BlockProcessingService
from bxgateway.services.block_queuing_service import BlockQueuingService
from bxgateway.services.block_recovery_service import BlockRecoveryService
from bxgateway.services.neutrality_service import NeutralityService
from bxgateway.testing.mocks.mock_blockchain_connection import MockBlockchainConnection, MockBlockMessage
from bxgateway.testing.mocks.mock_gateway_node import MockGatewayNode


class BlockHoldingServiceTest(AbstractTestCase):

    def setUp(self):
        self.node = MockGatewayNode(helpers.get_gateway_opts(8000))
        self.sut = BlockProcessingService(self.node)

        self.node.block_processing_service = self.sut
        self.node.neutrality_service = MagicMock(spec=NeutralityService)
        self.node.block_recovery_service = MagicMock(spec=BlockRecoveryService)
        self.node.block_queuing_service = MagicMock(spec=BlockQueuingService)

        self.dummy_connection = MockConnection(0, (LOCALHOST, 9000), self.node)

    def test_place_hold(self):
        hash1 = Sha256ObjectHash(helpers.generate_bytearray(crypto.SHA256_HASH_LEN))
        hash2 = Sha256ObjectHash(helpers.generate_bytearray(crypto.SHA256_HASH_LEN))

        self.sut.place_hold(hash1, self.dummy_connection)
        self.sut.place_hold(hash2, self.dummy_connection)

        self.assertEqual(2, len(self.sut._holds.contents))
        self.assertEqual(2, len(self.node.broadcast_messages))
        self.assertEqual(BlockHoldingMessage(hash1, network_num=1), self.node.broadcast_messages[0][0])
        self.assertEqual(BlockHoldingMessage(hash2, network_num=1), self.node.broadcast_messages[1][0])

    def test_place_hold_block_seen(self):
        hash1 = Sha256ObjectHash(helpers.generate_bytearray(crypto.SHA256_HASH_LEN))
        self.node.blocks_seen.add(hash1)
        self.sut.place_hold(hash1, self.dummy_connection)
        self.assertEqual(0, len(self.sut._holds.contents))

    def test_place_hold_duplicates(self):
        hash1 = Sha256ObjectHash(helpers.generate_bytearray(crypto.SHA256_HASH_LEN))
        hash2 = Sha256ObjectHash(helpers.generate_bytearray(crypto.SHA256_HASH_LEN))

        self.sut.place_hold(hash1, self.dummy_connection)
        time.time = MagicMock(return_value=time.time() + 5)

        self.sut.place_hold(hash1, self.dummy_connection)
        self.sut.place_hold(hash1, self.dummy_connection)
        self.sut.place_hold(hash2, self.dummy_connection)

        self.assertEqual(2, len(self.sut._holds.contents))
        hold1 = self.sut._holds.contents[hash1]
        hold2 = self.sut._holds.contents[hash2]
        self.assertTrue(hold2.hold_message_time - hold1.hold_message_time >= 5)

    def test_queue_block_no_hold(self):
        block_hash = Sha256ObjectHash(helpers.generate_bytearray(crypto.SHA256_HASH_LEN))
        block_message = MockBlockMessage(block_hash)
        connection = MockBlockchainConnection(MockSocketConnection(), (LOCALHOST, 8000), self.node)

        self.sut.queue_block_for_processing(block_message, connection)
        self._assert_block_propagated(block_hash)

        broadcasted_messages = self.node.broadcast_messages
        self.assertEqual(1, len(broadcasted_messages))
        self.assertEqual(BlockHoldingMessage(block_hash, network_num=1), broadcasted_messages[0][0])

    def test_queue_block_hold_exists_until_cancelled(self):
        block_hash = Sha256ObjectHash(helpers.generate_bytearray(crypto.SHA256_HASH_LEN))
        block_message = MockBlockMessage(block_hash)
        connection = MockBlockchainConnection(MockSocketConnection(), (LOCALHOST, 8000), self.node)

        self.sut.place_hold(block_hash, self.dummy_connection)
        alarm_count = len(self.node.alarm_queue.alarms)
        self.sut.queue_block_for_processing(block_message, connection)

        self.node.neutrality_service.propagate_block_to_network.assert_not_called()
        self.assertIn(block_hash, self.sut._holds.contents)
        self.assertEqual(alarm_count + 1, len(self.node.alarm_queue.alarms))

        hold = self.sut._holds.contents[block_hash]
        self.sut.cancel_hold_timeout(block_hash, self.dummy_connection)
        self.assertNotIn(block_hash, self.sut._holds.contents)
        self.assertEqual(AlarmQueue.REMOVED, hold.alarm[-1])

    def test_queue_block_holds_exists_until_timeout(self):
        block_hash = Sha256ObjectHash(helpers.generate_bytearray(crypto.SHA256_HASH_LEN))
        block_message = MockBlockMessage(block_hash)
        connection = MockBlockchainConnection(MockSocketConnection(), (LOCALHOST, 8000), self.node)

        self.sut.place_hold(block_hash, self.dummy_connection)
        self.sut.queue_block_for_processing(block_message, connection)

        self.node.neutrality_service.propagate_block_to_network.assert_not_called()
        time.time = MagicMock(return_value=time.time() + self.sut._compute_hold_timeout(block_message))
        self.node.alarm_queue.fire_alarms()

        self._assert_block_propagated(block_hash)

    def test_cancel_hold_with_block_from_blockchain(self):
        block_hash = Sha256ObjectHash(helpers.generate_bytearray(crypto.SHA256_HASH_LEN))
        block_message = MockBlockMessage(block_hash)
        connection = MockBlockchainConnection(MockSocketConnection(), (LOCALHOST, 8000), self.node)

        self.sut.place_hold(block_hash, self.dummy_connection)
        self.sut.queue_block_for_processing(block_message, connection)
        self.sut.cancel_hold_timeout(block_hash, connection)

        self.assertEqual(0, len(self.sut._holds.contents))

    def test_cancel_hold_no_block_from_blockchain(self):
        block_hash = Sha256ObjectHash(helpers.generate_bytearray(crypto.SHA256_HASH_LEN))
        connection = MockBlockchainConnection(MockSocketConnection(), (LOCALHOST, 8000), self.node)

        self.sut.place_hold(block_hash, self.dummy_connection)
        self.sut.cancel_hold_timeout(block_hash, connection)

        self.assertEqual(0, len(self.sut._holds.contents))

    def _assert_block_propagated(self, block_hash):
        self.node.neutrality_service.propagate_block_to_network.assert_called_once()
        self.node.block_recovery_service.cancel_recovery_for_block.assert_called_once()
        self.node.block_queuing_service.remove.assert_called_once()
        self.assertIn(block_hash, self.node.blocks_seen.contents)
