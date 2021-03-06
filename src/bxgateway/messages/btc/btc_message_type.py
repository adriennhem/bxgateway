class BtcMessageType(object):
    VERSION = b"version"
    VERACK = b"verack"
    PING = b"ping"
    PONG = b"pong"
    GET_ADDRESS = b"getaddr"
    ADDRESS = b"addr"
    INVENTORY = b"inv"
    GET_DATA = b"getdata"
    NOT_FOUND = b"notfound"
    GET_HEADERS = b"getheaders"
    GET_BLOCKS = b"getblocks"
    TRANSACTIONS = b"tx"
    BLOCK = b"block"
    HEADERS = b"headers"
    REJECT = b"reject"
    SEND_HEADERS = b"sendheaders"
    COMPACT_BLOCK = b"cmpctblock"
    SEND_COMPACT = b"sendcmpct"
    GET_BLOCK_TRANSACTIONS = b"getblocktxn"
    BLOCK_TRANSACTIONS = b"blocktxn"
    FEE_FILTER = b"feefilter"
    XVERSION = b"xversion"
