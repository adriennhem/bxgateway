from bxcommon.messages.bloxroute.bloxroute_message_type import BloxrouteMessageType
from bxgateway.messages.gateway.gateway_message_type import GatewayMessageType

GATEWAY_HELLO_MESSAGES = [GatewayMessageType.HELLO, BloxrouteMessageType.ACK]

GATEWAY_BLOCKS_SEEN_EXPIRATION_TIME_S = 60 * 60 * 24

# Delay for blockchain sync message request before broadcasting to everyone
# This constants is currently unused
BLOCKCHAIN_SYNC_BROADCAST_DELAY_S = 5
BLOCKCHAIN_PING_INTERVAL_S = 15

BLOCK_RECOVERY_RECOVERY_INTERVAL_S = [0.1, 0.5, 1, 2, 5]
BLOCK_RECOVERY_MAX_RETRY_ATTEMPTS = len(BLOCK_RECOVERY_RECOVERY_INTERVAL_S)
BLOCK_RECOVERY_MAX_QUEUE_TIME = 15  # slightly more than sum(BLOCK_RECOVERY_RECOVERY_INTERVAL_S)


# enum for setting Gateway neutrality assertion policy for releasing encryption keys
class NeutralityPolicy(object):
    RECEIPT_COUNT = 1
    RECEIPT_PERCENT = 2
    RECEIPT_COUNT_AND_PERCENT = 3

    RELEASE_IMMEDIATELY = 99


# duration to wait for block receipts until timeout
NEUTRALITY_BROADCAST_BLOCK_TIMEOUT_S = 30 * 60

NEUTRALITY_POLICY = NeutralityPolicy.RECEIPT_PERCENT
NEUTRALITY_EXPECTED_RECEIPT_COUNT = 1
NEUTRALITY_EXPECTED_RECEIPT_PERCENT = 50

# Max duration to wait before releasing a block, even if blockchain node has not indicated receipt of
# previous block in chain. This value can be set to 0 if a blockchain node implementation is capable of
# immediately taking block messages without validating previous block.
MAX_INTERVAL_BETWEEN_BLOCKS_S = 0.1
NODE_READINESS_FOR_BLOCKS_CHECK_INTERVAL_S = 5

GATEWAY_TRANSACTION_STATS_INTERVAL_S = 1 * 60
GATEWAY_TRANSACTION_STATS_LOOKBACK = 1

ETH_GATEWAY_STATS_INTERVAL = 60
ETH_GATEWAY_STATS_LOOKBACK = 1

MIN_PEER_RELAYS = 1

BLOCKCHAIN_SOCKET_SEND_BUFFER_SIZE = 16 * 1024 * 1024

COOKIE_FILE_PATH_TEMPLATE = ".gateway_cookies/.cookie.blxrbdn-gw-{}"

SEND_REQUEST_RELAY_PEERS_MAX_NUM_OF_CALLS = 10
SEND_REQUEST_GATEWAY_PEERS_MAX_NUM_OF_CALLS = 5

GATEWAY_PEER_NAME = "bloXroute Gateway"
CONFIG_UPDATE_INTERVAL_S = 360
CONFIG_FILE_NAME = "config.default.json"
CONFIG_OVERRIDE_NAME = "config.override.json"

BLOCK_HANDLING_TIME_EXPIRATION_TIME_S = 300

INITIAL_LIVELINESS_CHECK_S = 30
DEFAULT_STAY_ALIVE_DURATION_S = 30 * 60

DEFAULT_BLOCKCHAIN_MESSAGE_TTL_S = 10
DEFAULT_REMOTE_BLOCKCHAIN_MESSAGE_TTL_S = 10

BLOCK_CLEANUP_NODE_BLOCK_LIST_POLL_INTERVAL_S = 60
# ignore last confirmed block and request block confirmation since last tracked block instead
BLOCK_CLEANUP_REQUEST_EXPECTED_ADDITIONAL_TRACKED_BLOCKS = 1

REMOTE_BLOCKCHAIN_MAX_CONNECT_RETRIES = 10
REMOTE_BLOCKCHAIN_SDN_CONTACT_RETRY_SECONDS = 30

BLOCK_CONFIRMATION_EXPIRE_TIME_S = 60 * 60
