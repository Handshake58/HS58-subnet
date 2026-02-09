# Adapted from opentensor/bittensor-subnet-template
# Base neuron class for Subnet 58

import copy
import bittensor as bt
from abc import ABC, abstractmethod

from subnet58.utils.config import check_config, add_args, config
from subnet58.utils.misc import ttl_get_block
from subnet58 import __spec_version__ as spec_version


class BaseNeuron(ABC):
    """
    Base class for Bittensor neurons (miners and validators).
    Handles wallet, subtensor, metagraph setup and sync.
    """

    neuron_type: str = "BaseNeuron"

    @classmethod
    def check_config(cls, config: "bt.Config"):
        check_config(cls, config)

    @classmethod
    def add_args(cls, parser):
        add_args(cls, parser)

    @classmethod
    def config(cls):
        return config(cls)

    subtensor: "bt.subtensor"
    wallet: "bt.wallet"
    metagraph: "bt.metagraph"
    spec_version: int = spec_version

    @property
    def block(self):
        return ttl_get_block(self)

    def __init__(self, config=None):
        base_config = copy.deepcopy(config or BaseNeuron.config())
        self.config = self.config()
        self.config.merge(base_config)
        self.check_config(self.config)

        bt.logging.set_config(config=self.config.logging)
        self.device = self.config.neuron.device
        bt.logging.info(self.config)

        # Build Bittensor objects
        bt.logging.info("Setting up bittensor objects.")
        self.wallet = bt.wallet(config=self.config)
        self.subtensor = bt.subtensor(config=self.config)
        self.metagraph = self.subtensor.metagraph(self.config.netuid)

        bt.logging.info(f"Wallet: {self.wallet}")
        bt.logging.info(f"Subtensor: {self.subtensor}")
        bt.logging.info(f"Metagraph: {self.metagraph}")

        # Check registration
        self.check_registered()

        self.uid = self.metagraph.hotkeys.index(
            self.wallet.hotkey.ss58_address
        )
        bt.logging.info(
            f"Running neuron on subnet: {self.config.netuid} with uid {self.uid} "
            f"using network: {self.subtensor.chain_endpoint}"
        )
        self.step = 0

    @abstractmethod
    async def forward(self, synapse: bt.Synapse) -> bt.Synapse:
        ...

    @abstractmethod
    def run(self):
        ...

    def sync(self):
        """Synchronize network state."""
        self.check_registered()
        if self.should_sync_metagraph():
            self.resync_metagraph()
        if self.should_set_weights():
            self.set_weights()
        self.save_state()

    def check_registered(self):
        if not self.subtensor.is_hotkey_registered(
            netuid=self.config.netuid,
            hotkey_ss58=self.wallet.hotkey.ss58_address,
        ):
            bt.logging.error(
                f"Wallet: {self.wallet} is not registered on netuid {self.config.netuid}. "
                f"Please register using `btcli subnets register` first."
            )
            exit()

    def should_sync_metagraph(self):
        return (
            self.block - self.metagraph.last_update[self.uid]
        ) > self.config.neuron.epoch_length

    def should_set_weights(self) -> bool:
        if self.step == 0:
            return False
        if self.config.neuron.disable_set_weights:
            return False
        return (
            (self.block - self.metagraph.last_update[self.uid])
            > self.config.neuron.epoch_length
            and self.neuron_type != "MinerNeuron"
        )

    def save_state(self):
        pass

    def load_state(self):
        pass
