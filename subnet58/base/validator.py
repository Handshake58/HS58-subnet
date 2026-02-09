# Adapted from opentensor/bittensor-subnet-template
# Base validator class for Subnet 58

import copy
import numpy as np
import asyncio
import argparse
import threading
import bittensor as bt

from typing import List, Union
from traceback import print_exception

from subnet58.base.neuron import BaseNeuron
from subnet58.utils.config import add_validator_args


class BaseValidatorNeuron(BaseNeuron):
    """Base class for Bittensor validators."""

    neuron_type: str = "ValidatorNeuron"

    @classmethod
    def add_args(cls, parser: argparse.ArgumentParser):
        super().add_args(parser)
        add_validator_args(cls, parser)

    def __init__(self, config=None):
        super().__init__(config=config)

        self.hotkeys = copy.deepcopy(self.metagraph.hotkeys)
        self.dendrite = bt.dendrite(wallet=self.wallet)
        bt.logging.info(f"Dendrite: {self.dendrite}")

        # Scoring weights
        bt.logging.info("Building validation weights.")
        self.scores = np.zeros(self.metagraph.n, dtype=np.float32)

        self.sync()

        # Serve axon
        if not self.config.neuron.axon_off:
            self.serve_axon()

        self.loop = asyncio.get_event_loop()
        self.should_exit: bool = False
        self.is_running: bool = False
        self.thread: Union[threading.Thread, None] = None
        self.lock = asyncio.Lock()

    def serve_axon(self):
        bt.logging.info("Serving axon to chain...")
        try:
            self.axon = bt.axon(wallet=self.wallet, config=self.config)
            self.subtensor.serve_axon(
                netuid=self.config.netuid, axon=self.axon
            )
        except Exception as e:
            bt.logging.error(f"Failed to serve Axon: {e}")

    def run(self):
        """Main loop for the validator."""
        self.sync()
        bt.logging.info(f"Validator starting at block: {self.block}")

        try:
            while True:
                bt.logging.info(f"step({self.step}) block({self.block})")
                self.loop.run_until_complete(self.forward())

                if self.should_exit:
                    break

                self.sync()
                self.step += 1
        except KeyboardInterrupt:
            bt.logging.success("Validator killed by keyboard interrupt.")
            exit()
        except Exception as err:
            bt.logging.error(f"Error during validation: {str(err)}")
            bt.logging.debug(str(print_exception(type(err), err, err.__traceback__)))

    def run_in_background_thread(self):
        if not self.is_running:
            bt.logging.debug("Starting validator in background thread.")
            self.should_exit = False
            self.thread = threading.Thread(target=self.run, daemon=True)
            self.thread.start()
            self.is_running = True

    def stop_run_thread(self):
        if self.is_running:
            bt.logging.debug("Stopping validator in background thread.")
            self.should_exit = True
            self.thread.join(5)
            self.is_running = False

    def __enter__(self):
        self.run_in_background_thread()
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        if self.is_running:
            self.should_exit = True
            self.thread.join(5)
            self.is_running = False

    def set_weights(self):
        """Sets validator weights on chain based on scores."""
        if np.isnan(self.scores).any():
            bt.logging.warning("Scores contain NaN values.")

        # Normalize scores
        raw_weights = self.scores.copy()
        norm = np.sum(raw_weights)
        if norm > 0:
            raw_weights = raw_weights / norm
        else:
            bt.logging.warning("All scores are zero, skipping set_weights.")
            return

        bt.logging.info(f"Setting weights: {raw_weights}")

        # Convert to uint16
        uids = self.metagraph.uids
        result, msg = self.subtensor.set_weights(
            wallet=self.wallet,
            netuid=self.config.netuid,
            uids=uids,
            weights=raw_weights,
            wait_for_finalization=False,
            wait_for_inclusion=False,
            version_key=self.spec_version,
        )
        if result:
            bt.logging.info("set_weights on chain successfully!")
        else:
            bt.logging.error(f"set_weights failed: {msg}")

    def resync_metagraph(self):
        """Resyncs metagraph and handles hotkey changes."""
        bt.logging.info("resync_metagraph()")
        previous_metagraph = copy.deepcopy(self.metagraph)
        self.metagraph.sync(subtensor=self.subtensor)

        if previous_metagraph.axons == self.metagraph.axons:
            return

        bt.logging.info("Metagraph updated, re-syncing hotkeys and scores.")

        # Zero out scores for replaced hotkeys
        overlap = min(len(self.hotkeys), len(self.metagraph.hotkeys))
        for uid in range(overlap):
            if self.hotkeys[uid] != self.metagraph.hotkeys[uid]:
                self.scores[uid] = 0

        # Resize scores if metagraph size changed
        if len(self.scores) != int(self.metagraph.n):
            new_scores = np.zeros(self.metagraph.n, dtype=np.float32)
            copy_len = min(len(self.scores), int(self.metagraph.n))
            new_scores[:copy_len] = self.scores[:copy_len]
            self.scores = new_scores

        self.hotkeys = copy.deepcopy(self.metagraph.hotkeys)

    def update_scores(self, rewards: np.ndarray, uids: List[int]):
        """Exponential moving average on scores."""
        if np.isnan(rewards).any():
            rewards = np.nan_to_num(rewards, nan=0)

        rewards = np.asarray(rewards)
        uids_array = np.array(uids) if not isinstance(uids, np.ndarray) else uids.copy()

        if rewards.size == 0 or uids_array.size == 0:
            return

        scattered_rewards = np.zeros_like(self.scores)
        scattered_rewards[uids_array] = rewards

        alpha = self.config.neuron.moving_average_alpha
        self.scores = alpha * scattered_rewards + (1 - alpha) * self.scores

    def save_state(self):
        """Saves validator state."""
        try:
            np.savez(
                self.config.neuron.full_path + "/state.npz",
                step=self.step,
                scores=self.scores,
                hotkeys=self.hotkeys,
            )
        except Exception as e:
            bt.logging.warning(f"Failed to save state: {e}")

    def load_state(self):
        """Loads validator state."""
        try:
            state = np.load(self.config.neuron.full_path + "/state.npz")
            self.step = int(state["step"])
            self.scores = state["scores"]
            self.hotkeys = list(state["hotkeys"])
        except Exception:
            bt.logging.info("No saved state found, starting fresh.")
