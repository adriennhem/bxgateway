import typing

from bxgateway import btc_constants
from bxgateway.connections.abstract_blockchain_connection_protocol import AbstractBlockchainConnectionProtocol
from bxgateway.messages.btc.addr_btc_message import AddrBtcMessage
from bxgateway.messages.btc.btc_message_factory import btc_message_factory
from bxgateway.messages.btc.btc_message_type import BtcMessageType
from bxgateway.messages.btc.inventory_btc_message import InvBtcMessage, InventoryType
from bxgateway.messages.btc.ping_btc_message import PingBtcMessage
from bxgateway.messages.btc.pong_btc_message import PongBtcMessage
from bxgateway.messages.btc.version_btc_message import VersionBtcMessage
from bxutils import logging

logger = logging.get_logger(__name__)


class BtcBaseConnectionProtocol(AbstractBlockchainConnectionProtocol):
    def __init__(self, connection):
        super(BtcBaseConnectionProtocol, self).__init__(connection)
        self.node = typing.cast("bxgateway.connections.btc.btc_gateway_node.BtcGatewayNode", connection.node)
        self.magic = self.node.opts.blockchain_net_magic
        self.version = self.node.opts.blockchain_version

        connection.hello_messages = btc_constants.BTC_HELLO_MESSAGES
        connection.header_size = btc_constants.BTC_HDR_COMMON_OFF
        connection.message_factory = btc_message_factory
        connection.message_handlers = {
            BtcMessageType.PING: self.msg_ping,
            BtcMessageType.PONG: self.msg_pong,
            BtcMessageType.GET_ADDRESS: self.msg_getaddr
        }
        connection.ping_message = PingBtcMessage(self.magic)

        # Establish connection with blockchain node
        version_msg = VersionBtcMessage(self.magic, self.version, connection.peer_ip, connection.peer_port,
                                        self.node.opts.external_ip, self.node.opts.external_port,
                                        self.node.opts.blockchain_nonce, 0,
                                        str(self.node.opts.protocol_version).encode("utf-8"),
                                        self.node.opts.blockchain_services)
        connection.enqueue_msg(version_msg)

    def msg_block(self, msg):
        """
        Handle block message
        """
        block_hash = msg.block_hash()
        if self.node.block_cleanup_service.is_marked_for_cleanup(block_hash):
            self.connection.log_trace("Marked block for cleanup: {}", block_hash)
            self.node.block_cleanup_service.clean_block_transactions(
                transaction_service=self.node.get_tx_service(),
                block_msg=msg
            )
        else:
            super().msg_block(msg)

        # After receiving block message sending INV message for the same block to Bitcoin node
        # This is needed to update Synced Headers value of the gateway peer on the Bitcoin node
        # If Synced Headers is not up-to-date than Bitcoin node does not push compact blocks to the gateway
        inv_msg = InvBtcMessage(magic=self.node.opts.blockchain_net_magic,
                                inv_vects=[(InventoryType.MSG_BLOCK, msg.block_hash())])
        self.node.send_msg_to_node(inv_msg)

    def msg_ping(self, msg):
        """
        Handle ping messages. Respond with a pong.
        """
        reply = PongBtcMessage(self.magic, msg.nonce())
        self.connection.enqueue_msg(reply)

    def msg_pong(self, msg):
        """
        Handle pong messages. For now, don't do anything since we don't ping.
        """
        pass

    def msg_getaddr(self, _msg):
        """
        Handle a getaddr message. Return a blank address to preserve privacy.
        """
        reply = AddrBtcMessage(self.magic)
        self.connection.enqueue_msg(reply)
