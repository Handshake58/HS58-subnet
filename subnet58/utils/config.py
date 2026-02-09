# Adapted from opentensor/bittensor-subnet-template
# Simplified for Subnet 58 - no wandb, no mock, no events logger

import os
import argparse
import bittensor as bt


def check_config(cls, config: "bt.Config"):
    """Checks/validates the config namespace object."""
    bt.logging.check_config(config)

    full_path = os.path.expanduser(
        "{}/{}/{}/netuid{}/{}".format(
            config.logging.logging_dir,
            config.wallet.name,
            config.wallet.hotkey,
            config.netuid,
            config.neuron.name,
        )
    )
    config.neuron.full_path = os.path.expanduser(full_path)
    if not os.path.exists(config.neuron.full_path):
        os.makedirs(config.neuron.full_path, exist_ok=True)


def add_args(cls, parser):
    """Adds relevant arguments to the parser for operation."""
    parser.add_argument("--netuid", type=int, help="Subnet netuid", default=58)
    parser.add_argument(
        "--neuron.device", type=str, help="Device to run on.", default="cpu"
    )
    parser.add_argument(
        "--neuron.epoch_length",
        type=int,
        help="Epoch length in blocks (12s each).",
        default=100,
    )


def add_miner_args(cls, parser):
    """Add miner specific arguments."""
    parser.add_argument(
        "--neuron.name", type=str, help="Neuron name.", default="miner"
    )
    parser.add_argument(
        "--blacklist.force_validator_permit",
        action="store_true",
        help="Only allow validators to query.",
        default=False,
    )
    parser.add_argument(
        "--blacklist.allow_non_registered",
        action="store_true",
        help="Allow non-registered entities.",
        default=False,
    )


def add_validator_args(cls, parser):
    """Add validator specific arguments."""
    parser.add_argument(
        "--neuron.name", type=str, help="Neuron name.", default="validator"
    )
    parser.add_argument(
        "--neuron.timeout",
        type=float,
        help="Timeout for each forward call in seconds.",
        default=30,
    )
    parser.add_argument(
        "--neuron.num_concurrent_forwards",
        type=int,
        help="Number of concurrent forwards.",
        default=1,
    )
    parser.add_argument(
        "--neuron.disable_set_weights",
        action="store_true",
        help="Disables setting weights.",
        default=False,
    )
    parser.add_argument(
        "--neuron.moving_average_alpha",
        type=float,
        help="Moving average alpha for scores.",
        default=0.1,
    )
    parser.add_argument(
        "--neuron.axon_off",
        action="store_true",
        help="Do not serve an Axon.",
        default=False,
    )


def config(cls):
    """Returns the configuration object."""
    parser = argparse.ArgumentParser()
    bt.wallet.add_args(parser)
    bt.subtensor.add_args(parser)
    bt.logging.add_args(parser)
    bt.axon.add_args(parser)
    cls.add_args(parser)
    return bt.config(parser)
