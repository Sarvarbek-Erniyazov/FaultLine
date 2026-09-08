"""Deterministic seeding for every source of randomness used at M0."""

from __future__ import annotations

import os
import random

import numpy as np

DEFAULT_SEED = 20260909


def seed_everything(seed: int = DEFAULT_SEED) -> int:
    """Seed Python, NumPy and the hash randomization of child processes.

    Torch seeding is added at M1 together with the training code.

    Args:
        seed: Seed value applied to every generator.

    Returns:
        The seed that was applied, for logging by the caller.
    """
    os.environ["PYTHONHASHSEED"] = str(seed)
    random.seed(seed)
    np.random.seed(seed)
    return seed
