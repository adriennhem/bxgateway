import struct
import time
import hashlib
from datetime import datetime

from csiphash import siphash24
from collections import deque
from typing import Tuple, Optional, List, Deque, Union, NamedTuple

from bxutils import logging

from bxcommon import constants
from bxcommon.messages.bloxroute import compact_block_short_ids_serializer
from bxcommon.messages.abstract_message import AbstractMessage
from bxcommon.utils import crypto, convert
from bxcommon.messages.bloxroute.compact_block_short_ids_serializer import BlockOffsets
from bxcommon.services.transaction_service import TransactionService
from bxcommon.utils.object_hash import Sha256Hash

from bxgateway import btc_constants
from bxgateway.utils.errors import message_conversion_error
from bxgateway.messages.btc.abstract_btc_message_converter import AbstractBtcMessageConverter, get_block_info, \
    CompactBlockCompressionResult
from bxgateway.messages.btc.btc_message_type import BtcMessageType
from bxgateway.messages.btc.compact_block_btc_message import CompactBlockBtcMessage
from bxgateway.utils.block_info import BlockInfo
from bxgateway.utils.btc.btc_object_hash import BtcObjectHash
from bxgateway.messages.btc.block_btc_message import BlockBtcMessage
from bxgateway.utils.block_header_info import BlockHeaderInfo
from bxgateway.messages.btc import btc_messages_util

logger = logging.get_logger(__name__)


class CompactBlockRecoveryData(NamedTuple):
    block_transactions: List[Optional[Union[memoryview, int]]]
    block_header: memoryview
    magic: int
    tx_service: TransactionService


def parse_bx_block_header(
        bx_block: memoryview, block_pieces: Deque[Union[bytearray, memoryview]]
) -> BlockHeaderInfo:
    block_offsets = compact_block_short_ids_serializer.get_bx_block_offsets(bx_block)
    short_ids, short_ids_len = compact_block_short_ids_serializer.deserialize_short_ids_from_buffer(
        bx_block,
        block_offsets.short_id_offset
    )

    # Compute block header hash
    block_header_size = \
        block_offsets.block_begin_offset + \
        btc_constants.BTC_HDR_COMMON_OFF + \
        btc_constants.BTC_BLOCK_HDR_SIZE
    block_hash = BtcObjectHash(
        buf=crypto.bitcoin_hash(
            bx_block[
                block_offsets.block_begin_offset + btc_constants.BTC_HDR_COMMON_OFF:
                block_header_size
            ]
        ),
        length=btc_constants.BTC_SHA_HASH_LEN
    )
    offset = block_header_size

    # Add header piece
    txn_count, txn_count_size = btc_messages_util.btc_varint_to_int(bx_block, block_header_size)
    offset += txn_count_size
    block_pieces.append(bx_block[block_offsets.block_begin_offset:offset])
    return BlockHeaderInfo(block_offsets, short_ids, short_ids_len, block_hash, offset, txn_count)


def parse_bx_block_transactions(
        block_hash: Sha256Hash,
        bx_block: memoryview,
        offset: int,
        short_ids: List[int],
        block_offsets: BlockOffsets,
        tx_service: TransactionService,
        block_pieces: Deque[Union[bytearray, memoryview]]
) -> Tuple[List[int], List[Sha256Hash], int]:
    has_missing, unknown_tx_sids, unknown_tx_hashes = \
        tx_service.get_missing_transactions(short_ids)
    if has_missing:
        return unknown_tx_sids, unknown_tx_hashes, offset
    short_tx_index = 0
    output_offset = offset
    while offset < block_offsets.short_id_offset:
        if bx_block[offset] == btc_constants.BTC_SHORT_ID_INDICATOR:
            try:
                sid = short_ids[short_tx_index]
            except IndexError:
                raise message_conversion_error.btc_block_decompression_error(
                    block_hash,
                    f"Message is improperly formatted, short id index ({short_tx_index}) "
                    f"exceeded its array bounds (size: {len(short_ids)})"
                )
            tx_hash, tx, _ = tx_service.get_transaction(sid)
            offset += btc_constants.BTC_SHORT_ID_INDICATOR_LENGTH
            short_tx_index += 1
        else:
            tx_size = btc_messages_util.get_next_tx_size(bx_block, offset)
            tx = bx_block[offset:offset + tx_size]
            offset += tx_size

        block_pieces.append(tx)
        output_offset += len(tx)

    return unknown_tx_sids, unknown_tx_hashes, output_offset


def build_btc_block(
        block_pieces: Deque[Union[bytearray, memoryview]], size: int
) -> Tuple[BlockBtcMessage, int]:
    btc_block = bytearray(size)
    offset = 0
    for piece in block_pieces:
        next_offset = offset + len(piece)
        btc_block[offset:next_offset] = piece
        offset = next_offset
    return BlockBtcMessage(buf=btc_block), offset


def compute_short_id(key: bytes, tx_hash_binary: Union[bytearray, memoryview]) -> bytes:
    return siphash24(key, bytes(tx_hash_binary))[0:6]


class BtcNormalMessageConverter(AbstractBtcMessageConverter):

    def block_to_bx_block(
            self, block_msg, tx_service
    ) -> Tuple[memoryview, BlockInfo]:
        """
        Compresses a Bitcoin block's transactions and packs it into a bloXroute block.
        """
        compress_start_datetime = datetime.utcnow()
        compress_start_timestamp = time.time()
        size = 0
        buf = deque()
        short_ids = []
        header = block_msg.header()
        size += len(header)
        buf.append(header)

        for tx in block_msg.txns():

            tx_hash = btc_messages_util.get_txid(tx)
            short_id = tx_service.get_short_id(tx_hash)
            if short_id == constants.NULL_TX_SID:
                buf.append(tx)
                size += len(tx)
            else:
                short_ids.append(short_id)
                buf.append(btc_constants.BTC_SHORT_ID_INDICATOR_AS_BYTEARRAY)
                size += 1

        serialized_short_ids = compact_block_short_ids_serializer.serialize_short_ids_into_bytes(short_ids)
        buf.append(serialized_short_ids)
        size += constants.UL_ULL_SIZE_IN_BYTES
        offset_buf = struct.pack("<Q", size)
        buf.appendleft(offset_buf)
        size += len(serialized_short_ids)

        block = bytearray(size)
        off = 0
        for blob in buf:
            next_off = off + len(blob)
            block[off:next_off] = blob
            off = next_off

        prev_block_hash = convert.bytes_to_hex(block_msg.prev_block_hash().binary)
        bx_block_hash = convert.bytes_to_hex(crypto.double_sha256(block))
        original_size = len(block_msg.rawbytes())

        block_info = BlockInfo(
            block_msg.block_hash(),
            short_ids,
            compress_start_datetime,
            datetime.utcnow(),
            (time.time() - compress_start_timestamp) * 1000,
            block_msg.txn_count(),
            bx_block_hash,
            prev_block_hash,
            original_size,
            size,
            100 - float(size) / original_size * 100
        )
        return memoryview(block), block_info

    def bx_block_to_block(
            self, bx_block_msg, tx_service
    ) -> Tuple[Optional[AbstractMessage], BlockInfo, List[int], List[Sha256Hash]]:
        """
        Uncompresses a bx_block from a broadcast bx_block message and converts to a raw BTC bx_block.

        bx_block must be a memoryview, since memoryview[offset] returns a bytearray, while bytearray[offset] returns
        a byte.
        """
        if not isinstance(bx_block_msg, memoryview):
            bx_block_msg = memoryview(bx_block_msg)

        decompress_start_datetime = datetime.utcnow()
        decompress_start_timestamp = time.time()

        # Initialize tracking of transaction and SID mapping
        block_pieces = deque()
        header_info = parse_bx_block_header(bx_block_msg, block_pieces)
        unknown_tx_sids, unknown_tx_hashes, offset = parse_bx_block_transactions(
            header_info.block_hash,
            bx_block_msg,
            header_info.offset,
            header_info.short_ids,
            header_info.block_offsets,
            tx_service,
            block_pieces
        )
        total_tx_count = header_info.txn_count

        if not unknown_tx_sids and not unknown_tx_hashes:
            btc_block_msg, offset = build_btc_block(block_pieces, offset)
            logger.debug(
                "Successfully parsed bx_block broadcast message. {0} transactions in bx_block".format(total_tx_count)
            )
        else:
            btc_block_msg = None
            logger.warning("Block recovery needed. Missing {0} sids, {1} tx hashes. Total txs in bx_block: {2}"
                        .format(len(unknown_tx_sids), len(unknown_tx_hashes), total_tx_count))
        block_info = get_block_info(
            bx_block_msg,
            header_info.block_hash,
            header_info.short_ids,
            decompress_start_datetime,
            decompress_start_timestamp,
            total_tx_count,
            btc_block_msg
        )
        return btc_block_msg, block_info, unknown_tx_sids, unknown_tx_hashes

    def compact_block_to_bx_block(
            self,
            compact_block: CompactBlockBtcMessage,
            transaction_service: TransactionService
    ) -> CompactBlockCompressionResult:
        """
         Handle decompression of Bitcoin compact block.
         Decompression converts compact block message to full block message.
         """
        compress_start_datetime = datetime.utcnow()
        block_header = compact_block.block_header()
        sha256_hash = hashlib.sha256()
        sha256_hash.update(block_header)
        sha256_hash.update(compact_block.short_nonce_buf())
        hex_digest = sha256_hash.digest()
        key = hex_digest[0:16]

        short_ids = compact_block.short_ids()

        short_id_to_tx_contents = {}

        for tx_hash in transaction_service.iter_transaction_hashes():
            tx_hash_binary = tx_hash.binary[::-1]
            tx_short_id = compute_short_id(key, tx_hash_binary)
            if tx_short_id in short_ids:
                tx_content = transaction_service.get_transaction_by_hash(tx_hash)
                if tx_content is None:
                    logger.debug("Hash {} is known by transactions service but content is missing.", tx_hash)
                else:
                    short_id_to_tx_contents[tx_short_id] = tx_content
            if len(short_id_to_tx_contents) == len(short_ids):
                break

        block_transactions = []
        missing_transactions_indices = []
        pre_filled_transactions = compact_block.pre_filled_transactions()
        total_txs_count = len(pre_filled_transactions) + len(short_ids)

        size = 0
        block_msg_parts = deque()

        block_msg_parts.append(block_header)
        size += len(block_header)

        tx_count_size = btc_messages_util.get_sizeof_btc_varint(total_txs_count)
        tx_count_buf = bytearray(tx_count_size)
        btc_messages_util.pack_int_to_btc_varint(total_txs_count, tx_count_buf, 0)
        block_msg_parts.append(tx_count_buf)
        size += tx_count_size

        short_ids_iter = iter(short_ids.keys())

        for index in range(total_txs_count):
            if index not in pre_filled_transactions:
                short_id = next(short_ids_iter)

                if short_id in short_id_to_tx_contents:
                    short_tx = short_id_to_tx_contents[short_id]
                    block_msg_parts.append(short_tx)
                    block_transactions.append(short_tx)
                    size += len(short_tx)
                else:
                    missing_transactions_indices.append(index)
                    block_transactions.append(None)
            else:
                pre_filled_transaction = pre_filled_transactions[index]
                block_msg_parts.append(pre_filled_transaction)
                block_transactions.append(pre_filled_transaction)
                size += len(pre_filled_transaction)

        recovered_item = CompactBlockRecoveryData(
            block_transactions, block_header, compact_block.magic(), transaction_service
        )

        block_info = BlockInfo(
            compact_block.block_hash(),
            [],
            compress_start_datetime,
            compress_start_datetime,
            0,
            None,
            None,
            None,
            len(compact_block.rawbytes()),
            None,
            None
        )

        if len(missing_transactions_indices) > 0:
            recovery_index = self._last_recovery_idx
            self._last_recovery_idx += 1
            self._recovery_items[recovery_index] = recovered_item  # pyre-ignore
            return CompactBlockCompressionResult(
                False,
                block_info,
                None,
                recovery_index,
                missing_transactions_indices,
                []
            )
        result = CompactBlockCompressionResult(False, block_info, None, None, [], [])
        return self._recovered_compact_block_to_bx_block(result, recovered_item)

    def recovered_compact_block_to_bx_block(
            self,
            failed_compression_result: CompactBlockCompressionResult,
    ) -> CompactBlockCompressionResult:
        failed_block_info = failed_compression_result.block_info
        start_datetime = datetime.utcnow()
        block_info = BlockInfo(
            failed_block_info.block_hash,  # pyre-ignore
            failed_block_info.short_ids,  # pyre-ignore
            start_datetime,
            start_datetime,
            0,
            None,
            None,
            None,
            failed_block_info.original_size,  # pyre-ignore
            None,
            None
        )
        failed_compression_result.block_info = block_info
        return self._recovered_compact_block_to_bx_block(
            failed_compression_result,
            self._recovery_items.pop(failed_compression_result.recovery_index)  # pyre-ignore
        )

    def _recovered_compact_block_to_bx_block(
            self,
            compression_result: CompactBlockCompressionResult,
            recovery_item: CompactBlockRecoveryData
    ) -> CompactBlockCompressionResult:
        """
        Handle recovery of Bitcoin compact block message.
        """

        missing_indices = compression_result.missing_indices
        recovered_transactions = compression_result.recovered_transactions
        block_transactions = recovery_item.block_transactions
        if len(missing_indices) != len(recovered_transactions):
            logger.debug(
                "Number of transactions missing in compact block does not match number of recovered transactions."
                "Missing transactions - {}. Recovered transactions - {}", len(missing_indices),
                len(recovered_transactions))
            return CompactBlockCompressionResult(
                False, None, None, None, missing_indices, recovered_transactions
            )

        for i in range(len(missing_indices)):
            missing_index = missing_indices[i]
            block_transactions[missing_index] = recovered_transactions[i]

        size = 0
        total_txs_count = len(block_transactions)
        block_msg_parts = deque()

        block_header = recovery_item.block_header
        block_msg_parts.append(block_header)
        size += len(block_header)

        tx_count_size = btc_messages_util.get_sizeof_btc_varint(total_txs_count)
        tx_count_buf = bytearray(tx_count_size)
        btc_messages_util.pack_int_to_btc_varint(total_txs_count, tx_count_buf, 0)
        block_msg_parts.append(tx_count_buf)
        size += tx_count_size

        for transaction in block_transactions:
            block_msg_parts.append(transaction)
            size += len(transaction)  # pyre-ignore

        msg_header = bytearray(btc_constants.BTC_HDR_COMMON_OFF)
        struct.pack_into("<L12sL", msg_header, 0, recovery_item.magic, BtcMessageType.BLOCK, size)
        block_msg_parts.appendleft(msg_header)
        size += btc_constants.BTC_HDR_COMMON_OFF

        block_msg_bytes = bytearray(size)
        off = 0
        for blob in block_msg_parts:
            next_off = off + len(blob)
            block_msg_bytes[off:next_off] = blob
            off = next_off

        checksum = crypto.bitcoin_hash(block_msg_bytes[btc_constants.BTC_HDR_COMMON_OFF:size])
        block_msg_bytes[btc_constants.BTC_HEADER_MINUS_CHECKSUM:btc_constants.BTC_HDR_COMMON_OFF] = checksum[0:4]
        bx_block, compression_block_info = self.block_to_bx_block(
            BlockBtcMessage(buf=block_msg_bytes), recovery_item.tx_service
        )
        compress_start_datetime = compression_block_info.start_datetime
        compress_end_datetime = datetime.utcnow()
        block_info = BlockInfo(
            compression_block_info.block_hash,
            compression_block_info.short_ids,
            compress_start_datetime,
            compress_end_datetime,
            (compress_end_datetime - compress_start_datetime).total_seconds() * 1000,
            compression_block_info.txn_count,
            compression_block_info.compressed_block_hash,
            compression_block_info.prev_block_hash,
            compression_block_info.original_size,
            compression_block_info.compressed_size,
            compression_block_info.compression_rate
        )
        return CompactBlockCompressionResult(True, block_info, bx_block, None, [], [])

