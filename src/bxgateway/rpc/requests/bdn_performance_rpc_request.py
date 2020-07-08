from typing import Any, Dict, Optional, TYPE_CHECKING

from bxcommon.rpc.json_rpc_response import JsonRpcResponse
from bxcommon.rpc.requests.abstract_rpc_request import AbstractRpcRequest
from bxcommon.utils.stats import stats_format
from bxgateway.utils.stats.gateway_bdn_performance_stats_service import (
    gateway_bdn_performance_stats_service,
    GatewayBdnPerformanceStatInterval,
)

if TYPE_CHECKING:
    # noinspection PyUnresolvedReferences
    # pylint: disable=ungrouped-imports,cyclic-import
    from bxgateway.connections.abstract_gateway_node import AbstractGatewayNode

INTERVAL_START_TIME = "interval_start_time"
INTERVAL_END_TIME = "interval_end_time"
BLOCKS_FROM_BDN = "blocks_from_bdn_percentage"
TX_FROM_BDN = "transactions_from_bdn_percentage"


class BdnPerformanceRpcRequest(AbstractRpcRequest["AbstractGatewayNode"]):
    help = {
        "params": "",
        "description": "return percentage of blocks/transactions first received from BDN rather than from p2p network "
        "in the previous 15 minute interval",
    }

    def validate_params(self) -> None:
        pass

    async def process_request(self) -> JsonRpcResponse:
        return self.ok(self._calc_bdn_performance_stats())

    def _calc_bdn_performance_stats(self) -> Dict[str, Any]:
        stats = {}
        interval_data: Optional[
            GatewayBdnPerformanceStatInterval
        ] = gateway_bdn_performance_stats_service.get_most_recent_stats()

        if interval_data is None:
            stats[INTERVAL_START_TIME] = float("nan")
            stats[INTERVAL_END_TIME] = float("nan")
            stats[BLOCKS_FROM_BDN] = float("nan")
            stats[TX_FROM_BDN] = float("nan")
            return stats

        stats[INTERVAL_START_TIME] = str(interval_data.start_time)
        assert interval_data.end_time is not None
        stats[INTERVAL_END_TIME] = str(interval_data.end_time)

        if (
            interval_data.new_blocks_received_from_bdn
            + interval_data.new_blocks_received_from_blockchain_node
            == 0
        ):
            stats[BLOCKS_FROM_BDN] = float("nan")
        if (
            interval_data.new_tx_received_from_bdn
            + interval_data.new_tx_received_from_blockchain_node
            == 0
        ):
            stats[TX_FROM_BDN] = float("nan")

        if BLOCKS_FROM_BDN not in stats:
            stats[BLOCKS_FROM_BDN] = stats_format.percentage(
                100
                * (
                    interval_data.new_blocks_received_from_bdn
                    / (
                        interval_data.new_blocks_received_from_bdn
                        + interval_data.new_blocks_received_from_blockchain_node
                    )
                )
            )
        if TX_FROM_BDN not in stats:
            stats[TX_FROM_BDN] = stats_format.percentage(
                100
                * (
                    interval_data.new_tx_received_from_bdn
                    / (
                        interval_data.new_tx_received_from_bdn
                        + interval_data.new_tx_received_from_blockchain_node
                    )
                )
            )

        return stats