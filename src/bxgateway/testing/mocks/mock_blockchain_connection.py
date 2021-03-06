# pyre-ignore-all-errors
import datetime
from typing import Tuple, Optional, List

from bxcommon.messages.abstract_message import AbstractMessage
from bxcommon.messages.bloxroute.block_hash_message import BlockHashMessage
from bxcommon.test_utils import helpers
from bxcommon.utils import crypto, convert
from bxcommon.utils.object_hash import Sha256Hash
from bxgateway.abstract_message_converter import AbstractMessageConverter
from bxgateway.connections.abstract_gateway_blockchain_connection import AbstractGatewayBlockchainConnection
from bxgateway.utils.block_info import BlockInfo


class MockBlockMessage(BlockHashMessage):
    MESSAGE_TYPE = b"mockblock"


class MockMessageConverter(AbstractMessageConverter):
    PREV_BLOCK = Sha256Hash(helpers.generate_bytearray(crypto.SHA256_HASH_LEN))

    def tx_to_bx_txs(self, tx_msg, network_num):
        return [(tx_msg, tx_msg.tx_hash(), tx_msg.tx_val())]

    def bx_tx_to_tx(self, bx_tx_msg):
        return bx_tx_msg

    def block_to_bx_block(self, block_msg, tx_service) -> Tuple[memoryview, BlockInfo]:
        return block_msg.rawbytes(), \
               BlockInfo(convert.bytes_to_hex(self.PREV_BLOCK.binary), [], datetime.datetime.utcnow(),
                         datetime.datetime.utcnow(), 0, 0, None, None, 0, 0, 0)

    def bx_block_to_block(self, bx_block_msg, tx_service) -> Tuple[Optional[AbstractMessage], BlockInfo, List[int],
                                                                   List[Sha256Hash]]:
        block_message = MockBlockMessage(buf=bx_block_msg)
        return block_message, block_message.block_hash(), [], []


class MockBlockchainConnection(AbstractGatewayBlockchainConnection):
    def __init__(self, sock, address, node):
        super(MockBlockchainConnection, self).__init__(sock, address, node)
