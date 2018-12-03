import socket

from mock import MagicMock

from bxcommon.connections.connection_pool import ConnectionPool
from bxcommon.constants import LOCALHOST
from bxcommon.network.socket_connection import SocketConnection
from bxcommon.test_utils.abstract_test_case import AbstractTestCase
from bxcommon.test_utils.mocks.mock_node import MockOpts
from bxgateway.connections.abstract_gateway_node import AbstractGatewayNode
from bxgateway.connections.gateway_connection import GatewayConnection
from bxgateway.messages.gateway.gateway_hello_message import GatewayHelloMessage


def create_node(ip, port):
    node = MagicMock(spec=AbstractGatewayNode)
    node.opts = MockOpts(external_ip=ip, external_port=port)
    node.connection_pool = ConnectionPool()
    node.connection_exists = node.connection_pool.has_connection
    node.enqueue_disconnect = MagicMock()
    node.network_num = node.opts.network_num
    return node


class GatewayConnectionTest(AbstractTestCase):
    def setUp(self):
        self.node = create_node(LOCALHOST, 8000)

    def _create_connection(self, fileno, ip, port, from_me, node=None):
        if node is None:
            node = self.node
        sock = MagicMock(spec=socket.socket)
        sock.fileno = lambda: fileno
        connection = GatewayConnection(SocketConnection(sock, node), (ip, port), node, from_me)

        node.connection_pool.add(fileno, ip, port, connection)
        return connection

    def test_msg_hello_updating_port_reference(self):
        fileno = 1

        inbound_connection = self._create_connection(fileno, LOCALHOST, 40000, False)
        self.assertTrue(self.node.connection_pool.has_connection(LOCALHOST, 40000))

        inbound_connection.msg_hello(GatewayHelloMessage(LOCALHOST, 8001, 1))
        self.assertTrue(self.node.connection_pool.has_connection(LOCALHOST, 40000))
        self.assertTrue(self.node.connection_pool.has_connection(LOCALHOST, 8001))
        self.assertEqual(self.node.connection_pool.get_byipport(LOCALHOST, 8001),
                         self.node.connection_pool.get_byipport(LOCALHOST, 40000))

    def test_msg_hello_reject_mismatched_ip(self):
        fileno = 1

        inbound_connection = self._create_connection(fileno, LOCALHOST, 40000, False)
        self.assertTrue(self.node.connection_pool.has_connection(LOCALHOST, 40000))

        inbound_connection.msg_hello(GatewayHelloMessage("192.168.1.1", 8001, 1))

        self.node.enqueue_disconnect.assert_called_with(fileno)

    def test_msg_hello_replace_other_connection(self):
        inbound_fileno = 1
        inbound_connection = self._create_connection(inbound_fileno, LOCALHOST, 40000, False)
        self.assertTrue(self.node.connection_pool.has_connection(LOCALHOST, 40000))

        outbound_fileno = 2
        outbound_connection = self._create_connection(outbound_fileno, LOCALHOST, 8001, True)
        outbound_connection.ordering = 1
        self.assertTrue(self.node.connection_pool.has_connection(LOCALHOST, 8001))

        inbound_connection.msg_hello(GatewayHelloMessage(LOCALHOST, 8001, 10))

        self.node.enqueue_disconnect.assert_called_with(outbound_fileno)
        self.assertTrue(self.node.connection_pool.has_connection(LOCALHOST, 40000))
        self.assertTrue(self.node.connection_pool.has_connection(LOCALHOST, 8001))
        self.assertEqual(self.node.connection_pool.get_byipport(LOCALHOST, 8001),
                         self.node.connection_pool.get_byipport(LOCALHOST, 40000))

    def test_msg_hello_replace_self(self):
        inbound_fileno = 1
        inbound_connection = self._create_connection(inbound_fileno, LOCALHOST, 40000, False)
        self.assertTrue(self.node.connection_pool.has_connection(LOCALHOST, 40000))

        outbound_fileno = 2
        outbound_connection = self._create_connection(outbound_fileno, LOCALHOST, 8001, True)
        outbound_connection.ordering = 10
        self.assertTrue(self.node.connection_pool.has_connection(LOCALHOST, 8001))

        inbound_connection.msg_hello(GatewayHelloMessage(LOCALHOST, 8001, 1))

        self.node.enqueue_disconnect.assert_called_with(inbound_fileno)
        self.assertTrue(self.node.connection_pool.has_connection(LOCALHOST, 8001))
        self.assertEqual(outbound_connection, self.node.connection_pool.get_byipport(LOCALHOST, 8001))

    def test_msg_hello_calls_on_two_nodes_resolve(self):
        main_port = 8000
        peer_port = 8001

        main_inbound_fileno = 1
        main_inbound_port = 40000
        main_inbound_connection = self._create_connection(main_inbound_fileno, LOCALHOST, main_inbound_port, False)
        self.assertEquals(GatewayConnection.NULL_ORDERING, main_inbound_connection.ordering)
        self.assertTrue(self.node.connection_pool.has_connection(LOCALHOST, main_inbound_port))

        main_outbound_fileno = 2
        main_outbound_ordering = 11
        main_outbound_connection = self._create_connection(main_outbound_fileno, LOCALHOST, peer_port, True)
        main_outbound_connection.ordering = main_outbound_ordering
        self.assertNotEqual(GatewayConnection.NULL_ORDERING, main_outbound_connection.ordering)
        self.assertTrue(self.node.connection_pool.has_connection(LOCALHOST, peer_port))

        peer_node = create_node(LOCALHOST, peer_port)

        peer_inbound_fileno = 1
        peer_inbound_port = 40001
        peer_inbound_connection = self._create_connection(peer_inbound_fileno, LOCALHOST, peer_inbound_port, False,
                                                          node=peer_node)
        self.assertEquals(GatewayConnection.NULL_ORDERING, peer_inbound_connection.ordering)
        self.assertTrue(peer_node.connection_pool.has_connection(LOCALHOST, peer_inbound_port))

        peer_outbound_fileno = 2
        peer_outbound_ordering = 10
        peer_outbound_connection = self._create_connection(peer_outbound_fileno, LOCALHOST, main_port, True,
                                                           node=peer_node)
        peer_outbound_connection.ordering = peer_outbound_ordering
        self.assertNotEqual(GatewayConnection.NULL_ORDERING, peer_outbound_connection.ordering)
        self.assertTrue(peer_node.connection_pool.has_connection(LOCALHOST, main_port))

        main_inbound_connection.msg_hello(GatewayHelloMessage(LOCALHOST, peer_port, peer_outbound_ordering))
        peer_inbound_connection.msg_hello(GatewayHelloMessage(LOCALHOST, main_port, main_outbound_ordering))

        self.node.enqueue_disconnect.assert_called_with(main_inbound_fileno)
        peer_node.enqueue_disconnect.assert_called_with(peer_outbound_fileno)

    def test_msg_hello_calls_on_two_nodes_retry(self):
        main_port = 8000
        peer_port = 8001

        main_inbound_fileno = 1
        main_inbound_port = 40000
        main_inbound_connection = self._create_connection(main_inbound_fileno, LOCALHOST, main_inbound_port, False)
        main_inbound_connection.enqueue_msg = MagicMock()
        self.assertEquals(GatewayConnection.NULL_ORDERING, main_inbound_connection.ordering)
        self.assertTrue(self.node.connection_pool.has_connection(LOCALHOST, main_inbound_port))

        main_outbound_fileno = 2
        main_outbound_ordering = 10
        main_outbound_connection = self._create_connection(main_outbound_fileno, LOCALHOST, peer_port, True)
        main_outbound_connection.ordering = main_outbound_ordering
        self.assertNotEqual(GatewayConnection.NULL_ORDERING, main_outbound_connection.ordering)
        self.assertTrue(self.node.connection_pool.has_connection(LOCALHOST, peer_port))

        peer_node = create_node(LOCALHOST, peer_port)

        peer_inbound_fileno = 1
        peer_inbound_port = 40001
        peer_inbound_connection = self._create_connection(peer_inbound_fileno, LOCALHOST, peer_inbound_port, False,
                                                          node=peer_node)
        peer_inbound_connection.enqueue_msg = MagicMock()
        self.assertEquals(GatewayConnection.NULL_ORDERING, peer_inbound_connection.ordering)
        self.assertTrue(peer_node.connection_pool.has_connection(LOCALHOST, peer_inbound_port))

        peer_outbound_fileno = 2
        peer_outbound_ordering = 10
        peer_outbound_connection = self._create_connection(peer_outbound_fileno, LOCALHOST, main_port, True,
                                                           node=peer_node)
        peer_outbound_connection.ordering = peer_outbound_ordering
        self.assertNotEqual(GatewayConnection.NULL_ORDERING, peer_outbound_connection.ordering)
        self.assertTrue(peer_node.connection_pool.has_connection(LOCALHOST, main_port))

        main_inbound_connection.msg_hello(GatewayHelloMessage(LOCALHOST, peer_port, peer_outbound_ordering))
        peer_inbound_connection.msg_hello(GatewayHelloMessage(LOCALHOST, main_port, main_outbound_ordering))

        self.node.enqueue_disconnect.assert_not_called()
        peer_node.enqueue_disconnect.assert_not_called()

        main_inbound_connection.enqueue_msg.assert_called_once()
        peer_inbound_connection.enqueue_msg.assert_called_once()

        main_inbound_connection.ordering = 11
        peer_inbound_connection.ordering = 12

        main_outbound_connection.msg_hello(GatewayHelloMessage(LOCALHOST, peer_port, peer_inbound_connection.ordering))
        peer_outbound_connection.msg_hello(GatewayHelloMessage(LOCALHOST, main_port, main_inbound_connection.ordering))

        self.node.enqueue_disconnect.assert_called_with(main_inbound_fileno)
        peer_node.enqueue_disconnect.assert_called_with(peer_outbound_fileno)
