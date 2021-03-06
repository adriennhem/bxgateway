from abc import ABCMeta
from typing import TYPE_CHECKING

from bxcommon import constants
from bxcommon.connections.connection_type import ConnectionType
from bxcommon.connections.internal_node_connection import InternalNodeConnection
from bxcommon.messages.bloxroute.abstract_cleanup_message import AbstractCleanupMessage
from bxcommon.messages.bloxroute.bloxroute_message_type import BloxrouteMessageType
from bxcommon.messages.bloxroute.bloxroute_message_validator import BloxrouteMessageValidator
from bxcommon.messages.bloxroute.disconnect_relay_peer_message import DisconnectRelayPeerMessage
from bxcommon.messages.bloxroute.hello_message import HelloMessage
from bxcommon.messages.bloxroute.tx_message import TxMessage
from bxcommon.messages.bloxroute.txs_message import TxsMessage
from bxcommon.messages.validation.message_size_validation_settings import MessageSizeValidationSettings
from bxcommon.utils import convert
from bxcommon.utils import memory_utils
from bxcommon.utils.stats import hooks
from bxcommon.utils.stats.transaction_stat_event_type import TransactionStatEventType
from bxcommon.utils.stats.transaction_statistics_service import tx_stats
from bxgateway.utils.stats.gateway_transaction_stats_service import gateway_transaction_stats_service

if TYPE_CHECKING:
    # noinspection PyUnresolvedReferences
    from bxgateway.connections.abstract_gateway_node import AbstractGatewayNode


class AbstractRelayConnection(InternalNodeConnection["AbstractGatewayNode"]):
    __metaclass__ = ABCMeta

    CONNECTION_TYPE = ConnectionType.RELAY_ALL

    def __init__(self, sock, address, node, from_me=False):
        super(AbstractRelayConnection, self).__init__(sock, address, node, from_me=from_me)

        hello_msg = HelloMessage(protocol_version=self.protocol_version, network_num=self.network_num,
                                 node_id=self.node.opts.node_id)
        self.enqueue_msg(hello_msg)

        self.hello_messages = constants.BLOXROUTE_HELLO_MESSAGES
        self.header_size = constants.STARTING_SEQUENCE_BYTES_LEN + constants.BX_HDR_COMMON_OFF
        self.message_handlers = {
            BloxrouteMessageType.HELLO: self.msg_hello,
            BloxrouteMessageType.PING: self.msg_ping,
            BloxrouteMessageType.PONG: self.msg_pong,
            BloxrouteMessageType.ACK: self.msg_ack,
            BloxrouteMessageType.BROADCAST: self.msg_broadcast,
            BloxrouteMessageType.KEY: self.msg_key,
            BloxrouteMessageType.TRANSACTION: self.msg_tx,
            BloxrouteMessageType.TRANSACTIONS: self.msg_txs,
            BloxrouteMessageType.BLOCK_HOLDING: self.msg_block_holding,
            BloxrouteMessageType.DISCONNECT_RELAY_PEER: self.msg_disconnect_relay_peer,
            BloxrouteMessageType.TX_SERVICE_SYNC_TXS: self.msg_tx_service_sync_txs,
            BloxrouteMessageType.TX_SERVICE_SYNC_COMPLETE: self.msg_tx_service_sync_complete,
            BloxrouteMessageType.BLOCK_CONFIRMATION: self.msg_cleanup,
            BloxrouteMessageType.TRANSACTION_CLEANUP: self.msg_cleanup,
        }

        msg_size_validation_settings = MessageSizeValidationSettings(self.node.network.max_block_size_bytes,
                                                                self.node.network.max_tx_size_bytes)
        self.message_validator = BloxrouteMessageValidator(msg_size_validation_settings, self.protocol_version)

    def msg_hello(self, msg):
        super(AbstractRelayConnection, self).msg_hello(msg)
        self.node.on_relay_connection_ready()

    def msg_broadcast(self, msg):
        """
        Handle broadcast message receive from bloXroute.
        This is typically an encrypted block.
        """
        if self.CONNECTION_TYPE & ConnectionType.RELAY_BLOCK:
            self.node.block_processing_service.process_block_broadcast(msg, self)
        else:
            self.log_error("Received unexpected block message on non-block relay connection: {}", msg)

    def msg_key(self, msg):
        """
        Handles key message receive from bloXroute.
        Looks for the encrypted block and decrypts; otherwise stores for later.
        """
        if self.CONNECTION_TYPE & ConnectionType.RELAY_BLOCK:
            self.node.block_processing_service.process_block_key(msg, self)
        else:
            self.log_error("Received unexpected key message on non-block relay connection: {}", msg)

    def msg_tx(self, msg):
        """
        Handle transactions receive from bloXroute network.
        """
        if not self.CONNECTION_TYPE & ConnectionType.RELAY_TRANSACTION:
            self.log_error("Received unexpected tx message on non-tx relay connection: {}", msg)
            return

        tx_service = self.node.get_tx_service()

        short_id = msg.short_id()
        tx_hash = msg.tx_hash()
        network_num = msg.network_num()
        tx_val = msg.tx_val()

        attempt_recovery = False

        if not short_id and tx_service.has_transaction_short_id(tx_hash) and \
                tx_service.has_transaction_contents(tx_hash):
            gateway_transaction_stats_service.log_duplicate_transaction_from_relay()
            tx_stats.add_tx_by_hash_event(tx_hash,
                                          TransactionStatEventType.TX_RECEIVED_BY_GATEWAY_FROM_PEER_IGNORE_SEEN,
                                          network_num, short_id, peer=self.peer_desc)
            self.log_trace("Transaction has already been seen: {}", tx_hash)
            return

        tx_stats.add_tx_by_hash_event(tx_hash, TransactionStatEventType.TX_RECEIVED_BY_GATEWAY_FROM_PEER,
                                      network_num, short_id, peer=self.peer_desc,
                                      is_compact_transaction=(tx_val == TxMessage.EMPTY_TX_VAL))
        gateway_transaction_stats_service.log_transaction_from_relay(tx_hash,
                                                                     short_id is not None,
                                                                     tx_val == TxMessage.EMPTY_TX_VAL)
        if short_id:
            tx_service.assign_short_id(tx_hash, short_id)
            was_missing = self.node.block_recovery_service.check_missing_sid(short_id)
            attempt_recovery |= was_missing
            tx_stats.add_tx_by_hash_event(tx_hash, TransactionStatEventType.TX_SHORT_ID_STORED_BY_GATEWAY,
                                          network_num, short_id, was_missing=was_missing)

        else:
            tx_stats.add_tx_by_hash_event(tx_hash, TransactionStatEventType.TX_SHORT_ID_EMPTY_IN_MSG_FROM_RELAY,
                                          network_num, short_id, peer=self.peer_desc)

        if tx_service.has_transaction_contents(tx_hash):
            self.log_trace("Transaction has been seen, but short id newly assigned.")
            if tx_val != TxMessage.EMPTY_TX_VAL:
                tx_stats.add_tx_by_hash_event(tx_hash,
                                              TransactionStatEventType.TX_RECEIVED_BY_GATEWAY_FROM_PEER_IGNORE_SEEN,
                                              network_num, short_id, peer=self.peer_desc)
                gateway_transaction_stats_service.log_redundant_transaction_content()

            if attempt_recovery:
                self.node.block_processing_service.retry_broadcast_recovered_blocks(self)
            return

        if tx_val != TxMessage.EMPTY_TX_VAL:
            self.log_trace("Adding hash value to tx service and forwarding it to node")
            tx_service.set_transaction_contents(tx_hash, msg.tx_val())
            attempt_recovery |= self.node.block_recovery_service.check_missing_tx_hash(tx_hash)

            if self.node.node_conn is not None:
                btc_tx_msg = self.node.message_converter.bx_tx_to_tx(msg)
                self.node.send_msg_to_node(btc_tx_msg)

            tx_stats.add_tx_by_hash_event(tx_hash, TransactionStatEventType.TX_SENT_FROM_GATEWAY_TO_BLOCKCHAIN_NODE,
                                          network_num, short_id)

        if attempt_recovery:
            self.node.block_processing_service.retry_broadcast_recovered_blocks(self)

    def msg_txs(self, msg: TxsMessage):
        if not self.CONNECTION_TYPE & ConnectionType.RELAY_TRANSACTION:
            self.log_error("Received unexpected txs message on non-tx relay connection: {}", msg)
            return

        transactions = msg.get_txs()
        tx_service = self.node.get_tx_service()

        tx_stats.add_txs_by_short_ids_event(map(lambda x: x.short_id, transactions),
                                            TransactionStatEventType.TX_UNKNOWN_SHORT_IDS_REPLY_RECEIVED_BY_GATEWAY_FROM_RELAY,
                                            network_num=self.node.network_num,
                                            peer=self.peer_desc,
                                            found_tx_hashes=map(lambda x: convert.bytes_to_hex(x.hash.binary),
                                                                transactions))

        for transaction in transactions:
            tx_hash, transaction_contents, short_id = transaction

            self.node.block_recovery_service.check_missing_sid(short_id)

            if not tx_service.has_short_id(short_id):
                tx_service.assign_short_id(tx_hash, short_id)

            self.node.block_recovery_service.check_missing_tx_hash(tx_hash)

            if not tx_service.has_transaction_contents(tx_hash):
                tx_service.set_transaction_contents(tx_hash, transaction_contents)

            tx_stats.add_tx_by_hash_event(tx_hash,
                                          TransactionStatEventType.TX_UNKNOWN_TRANSACTION_RECEIVED_BY_GATEWAY_FROM_RELAY,
                                          self.node.network_num, short_id, peer=self.peer_desc)

        self.node.block_processing_service.retry_broadcast_recovered_blocks(self)

        for block_awaiting_recovery in self.node.block_recovery_service.get_blocks_awaiting_recovery():
            self.node.block_processing_service.schedule_recovery_retry(block_awaiting_recovery)

    def msg_block_holding(self, msg):
        """
        Block holding request message handler. Places block on hold and broadcasts message to relay and gateway peers.
        :param msg: Message of type BlockHoldingMessage
        """
        block_hash = msg.block_hash()
        self.node.block_processing_service.place_hold(block_hash, self)

    def msg_disconnect_relay_peer(self, _msg: DisconnectRelayPeerMessage) -> None:
        """
        Drop relay peer request handler. Forces a gateway to drop its relay connection and request a new one
        :return: None
        """
        self.log_info("Received disconnect request. Dropping.")
        self.mark_for_close()

    def log_connection_mem_stats(self) -> None:
        """
        logs the connection's memory stats
        """
        super(AbstractRelayConnection, self).log_connection_mem_stats()

        class_name = self.__class__.__name__
        if self.node.message_converter is not None:
            hooks.add_obj_mem_stats(
                class_name,
                self.network_num,
                self.node.message_converter,
                "message_converter",
                memory_utils.ObjectSize(
                    "message_converter", memory_utils.get_special_size(self.node.message_converter).size, is_actual_size=True
                ),
                object_item_count=1,
                object_type=memory_utils.ObjectType.META,
                size_type=memory_utils.SizeType.SPECIAL
            )

    def msg_cleanup(self, msg: AbstractCleanupMessage):
        self.node.block_cleanup_service.process_cleanup_message(msg, self.node)
