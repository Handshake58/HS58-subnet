# Adapted from opentensor/bittensor-subnet-template

import bittensor as bt


def ttl_get_block(self) -> int:
    """Returns the current block number from the subtensor."""
    return self.subtensor.get_current_block()
