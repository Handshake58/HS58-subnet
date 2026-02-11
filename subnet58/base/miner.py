# Adapted from opentensor/bittensor-subnet-template
# Base miner class for Subnet 58

import time
import asyncio
import threading
import argparse
import traceback

import bittensor as bt

from subnet58.base.neuron import BaseNeuron
from subnet58.utils.config import add_miner_args

from typing import Union


class BaseMinerNeuron(BaseNeuron):
    """Base class for Bittensor miners."""

    neuron_type: str = "MinerNeuron"

    @classmethod
    def add_args(cls, parser: argparse.ArgumentParser):
        super().add_args(parser)
        add_miner_args(cls, parser)

    def __init__(self, config=None):
        super().__init__(config=config)

        if not self.config.blacklist.force_validator_permit:
            bt.logging.warning(
                "Allowing non-validators to send requests. This is a security risk."
            )

        # The axon handles request processing
        axon_port = getattr(self.config.axon, 'port', 8091)
        axon_external_ip = getattr(self.config.axon, 'external_ip', None)
        axon_external_port = getattr(self.config.axon, 'external_port', None)
        bt.logging.info(f"Creating Axon (port={axon_port}, external_ip={axon_external_ip}, external_port={axon_external_port})...")

        # Pass all params directly to avoid Axon auto-detecting IPs (hangs on Railway)
        axon_kwargs = {
            'wallet': self.wallet,
            'ip': '0.0.0.0',  # Bind on all interfaces
            'port': int(axon_port),
        }
        if axon_external_ip:
            axon_kwargs['external_ip'] = str(axon_external_ip)
        if axon_external_port:
            axon_kwargs['external_port'] = int(axon_external_port)

        self.axon = bt.Axon(**axon_kwargs)
        bt.logging.info("Axon created successfully.")

        bt.logging.info(f"Attaching forward function to miner axon.")
        self.axon.attach(
            forward_fn=self.forward,
            blacklist_fn=self.blacklist,
            priority_fn=self.priority,
        )
        bt.logging.info(f"Axon created: {self.axon}")

        self.should_exit: bool = False
        self.is_running: bool = False
        self.thread: Union[threading.Thread, None] = None
        self.lock = asyncio.Lock()

    def run(self):
        """Main loop for the miner."""
        self.sync()

        bt.logging.info(
            f"Serving miner axon on network: {self.config.subtensor.chain_endpoint} "
            f"with netuid: {self.config.netuid}"
        )
        try:
            self.axon.serve(netuid=self.config.netuid, subtensor=self.subtensor)
            self.axon.start()
            bt.logging.info("Axon serving successfully.")
        except Exception as e:
            bt.logging.warning(
                f"Axon serve failed (expected on Railway/no public port): {e}. "
                f"Miner will still run and respond to queries via internal networking."
            )

        bt.logging.info(f"Miner starting at block: {self.block}")

        try:
            while not self.should_exit:
                while (
                    self.block - self.metagraph.last_update[self.uid]
                    < self.config.neuron.epoch_length
                ):
                    time.sleep(1)
                    if self.should_exit:
                        break
                self.sync()
                self.step += 1
        except KeyboardInterrupt:
            self.axon.stop()
            bt.logging.success("Miner killed by keyboard interrupt.")
            exit()
        except Exception as e:
            bt.logging.error(traceback.format_exc())

    def run_in_background_thread(self):
        if not self.is_running:
            bt.logging.debug("Starting miner in background thread.")
            self.should_exit = False
            self.thread = threading.Thread(target=self.run, daemon=True)
            self.thread.start()
            self.is_running = True

    def stop_run_thread(self):
        if self.is_running:
            bt.logging.debug("Stopping miner in background thread.")
            self.should_exit = True
            if self.thread is not None:
                self.thread.join(5)
            self.is_running = False

    def __enter__(self):
        self.run_in_background_thread()
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.stop_run_thread()

    def resync_metagraph(self):
        bt.logging.info("resync_metagraph()")
        self.metagraph.sync(subtensor=self.subtensor)
