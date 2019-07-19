import sys

P2P_PROTOCOL_VERSION = 4
ETH_PROTOCOL_VERSION = 63
CAPABILITIES = ((b"eth", ETH_PROTOCOL_VERSION),)
BX_ETH_CLIENT_NAME = b"BloxRoute Gateway"

SIGNATURE_LEN = 65
MDC_LEN = 32
MAC_LEN = 32

MSG_TYPE_LEN = 1
MSG_HEADER_OFF = 0

PRIVATE_KEY_LEN = 32
PUBLIC_KEY_LEN = 64
PUBLIC_KEY_X_Y_LEN = 32

ECIES_CIPHER_NAME = "aes-128-ctr"
RLPX_CIPHER_NAME = "aes-256-ctr"
ECIES_CURVE = "secp256k1"
ECIES_ENCRYPT_OVERHEAD_LENGTH = 113
ECIES_HEADER = 0x04
ECIES_HEADER_BYTE = b"\x04"
ECIES_HEADER_LEN = 1

KEY_MATERIAL_LEN = 32
SHARED_KEY_LEN = 32
ENC_KEY_LEN = 16
IV_LEN = 16

CIPHER_DECRYPT_DO = 0
CIPHER_ENCRYPT_DO = 1

PING_MSG_TTL_SEC = 60

FRAME_HDR_TOTAL_LEN = 32
FRAME_HDR_DATA_LEN = 16
FRAME_MAC_LEN = 16
MSG_PADDING = 16
FRAME_MAX_BODY_SIZE = 256 ** 3
FRAME_MSG_TYPE_LEN = 1

DEFAULT_FRAME_SIZE = sys.maxsize
DEFAULT_FRAME_PROTOCOL_ID = 0
MAX_FRAME_SEQUENCE_ID = 2 ** 16

ENC_AUTH_MSG_LEN = 307
EIP8_AUTH_PREFIX_LEN = 2
EIP8_ACK_PAD_MIN = 100
EIP8_ACK_PAD_MAX = 250
AUTH_MSG_LEN = 194
AUTH_ACK_MSG_LEN = 97
ENC_AUTH_ACK_MSG_LEN = 210
AUTH_NONCE_LEN = 32
AUTH_MSG_VERSION = 4
MAX_NONCE = 2 ** 256 - 1

SHA3_LEN_BYTES = 32
SHA3_LEN_BITS = 256

BLOCK_HASH_LEN = 32
ADDRESS_LEN = 20
MERKLE_ROOT_LEN = 32
BLOOM_LEN = 256

HANDSHAKE_TIMEOUT_SEC = 30
PING_PONG_INTERVAL_SEC = 30
PING_PONG_TIMEOUT_SEC = 60
DISCONNECT_DELAY_SEC = 2
DISCOVERY_PONG_TIMEOUT_SEC = 5

DISCONNECT_REASON_TIMEOUT = 0x0b

CHECKPOINT_BLOCK_HEADERS_REQUEST_WAIT_TIME_S = 5

MSG_CLS_SERIALIZER_ATTR = "serializer"
