"""Build the deterministic synthetic dataset used to bootstrap the detector."""

import argparse
import math
from pathlib import Path

import numpy as np
import pandas as pd

FEATURES = [
    "click_count",
    "avg_click_interval",
    "click_interval_variance",
    "click_interval_entropy",
    "mouse_velocity_variance",
    "max_element_click_rate",
    "scroll_events",
    "keystroke_count",
]
SEED = 42
ENTROPY_BITS_TO_NATS = math.log(2)
DATASET_DIR = Path(__file__).resolve().parents[1] / "DATASET"


def _build_human_rows(random_state):
    """Create the three historical synthetic human personas."""
    entropy_scale = ENTROPY_BITS_TO_NATS
    casual = pd.DataFrame({
        "click_count": random_state.poisson(5, 1250),
        "avg_click_interval": random_state.normal(1200, 300, 1250),
        "click_interval_variance": random_state.normal(200000, 70000, 1250),
        "click_interval_entropy": random_state.normal(3.0, 0.4, 1250) * entropy_scale,
        "mouse_velocity_variance": random_state.normal(0.55, 0.18, 1250),
        "max_element_click_rate": random_state.uniform(0.1, 1.5, 1250),
        "scroll_events": random_state.poisson(10, 1250),
        "keystroke_count": random_state.poisson(8, 1250),
        "persona": "casual_browser",
        "label": "human",
    })
    power_user = pd.DataFrame({
        "click_count": random_state.poisson(18, 1250),
        "avg_click_interval": random_state.normal(500, 150, 1250),
        "click_interval_variance": random_state.normal(120000, 40000, 1250),
        "click_interval_entropy": random_state.normal(2.6, 0.4, 1250) * entropy_scale,
        "mouse_velocity_variance": random_state.normal(0.85, 0.25, 1250),
        "max_element_click_rate": random_state.uniform(1.0, 4.0, 1250),
        "scroll_events": random_state.poisson(4, 1250),
        "keystroke_count": random_state.poisson(45, 1250),
        "persona": "power_user",
        "label": "human",
    })
    mobile = pd.DataFrame({
        "click_count": random_state.poisson(7, 1250),
        "avg_click_interval": random_state.normal(1000, 350, 1250),
        "click_interval_variance": random_state.normal(160000, 55000, 1250),
        "click_interval_entropy": random_state.normal(2.4, 0.5, 1250) * entropy_scale,
        "mouse_velocity_variance": random_state.normal(0.05, 0.03, 1250),
        "max_element_click_rate": random_state.uniform(0.1, 2.0, 1250),
        "scroll_events": random_state.poisson(3, 1250),
        "keystroke_count": random_state.poisson(12, 1250),
        "persona": "mobile_user",
        "label": "human",
    })
    return pd.concat([casual, power_user, mobile], ignore_index=True)


def _build_bot_rows(random_state):
    """Create the four historical synthetic bot personas."""
    flooder = pd.DataFrame({
        "click_count": random_state.randint(100, 300, 250),
        "avg_click_interval": random_state.normal(30, 3, 250),
        "click_interval_variance": random_state.normal(8, 2, 250),
        "click_interval_entropy": random_state.normal(0.02, 0.01, 250) * ENTROPY_BITS_TO_NATS,
        "mouse_velocity_variance": np.zeros(250),
        "max_element_click_rate": random_state.uniform(20, 60, 250),
        "scroll_events": np.zeros(250),
        "keystroke_count": np.zeros(250),
        "persona": "http_flooder",
        "label": "bot",
    })
    slow_bot = pd.DataFrame({
        "click_count": random_state.poisson(8, 250),
        "avg_click_interval": random_state.normal(950, 15, 250),
        "click_interval_variance": random_state.normal(150, 10, 250),
        "click_interval_entropy": random_state.normal(0.12, 0.04, 250) * ENTROPY_BITS_TO_NATS,
        "mouse_velocity_variance": np.zeros(250),
        "max_element_click_rate": random_state.uniform(0.8, 1.3, 250),
        "scroll_events": np.zeros(250),
        "keystroke_count": np.zeros(250),
        "persona": "slow_bot",
        "label": "bot",
    })
    headless = pd.DataFrame({
        "click_count": random_state.poisson(11, 250),
        "avg_click_interval": random_state.normal(280, 12, 250),
        "click_interval_variance": random_state.normal(420, 30, 250),
        "click_interval_entropy": random_state.normal(0.65, 0.08, 250) * ENTROPY_BITS_TO_NATS,
        "mouse_velocity_variance": random_state.normal(0.008, 0.002, 250),
        "max_element_click_rate": random_state.uniform(2.5, 6.0, 250),
        "scroll_events": random_state.poisson(1, 250),
        "keystroke_count": np.zeros(250),
        "persona": "headless_browser",
        "label": "bot",
    })
    stuffer = pd.DataFrame({
        "click_count": random_state.poisson(4, 250),
        "avg_click_interval": random_state.normal(1100, 8, 250),
        "click_interval_variance": random_state.normal(40, 5, 250),
        "click_interval_entropy": random_state.normal(0.08, 0.03, 250) * ENTROPY_BITS_TO_NATS,
        "mouse_velocity_variance": random_state.normal(0.015, 0.004, 250),
        "max_element_click_rate": random_state.uniform(0.4, 1.0, 250),
        "scroll_events": np.zeros(250),
        "keystroke_count": random_state.normal(38, 1.5, 250),
        "persona": "credential_stuffer",
        "label": "bot",
    })
    return pd.concat([flooder, slow_bot, headless, stuffer], ignore_index=True)


def build_dataset(seed=SEED):
    """Return a deterministically shuffled dataset with human and bot labels."""
    random_state = np.random.RandomState(seed)
    humans = _build_human_rows(random_state)
    bots = _build_bot_rows(random_state)
    dataset = pd.concat([humans, bots], ignore_index=True)
    dataset[FEATURES] = dataset[FEATURES].clip(lower=0)
    return dataset.sample(frac=1, random_state=seed).reset_index(drop=True)


def write_dataset(dataset_dir=DATASET_DIR, seed=SEED):
    """Write the full synthetic dataset and its human-only training subset."""
    output_dir = Path(dataset_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    dataset = build_dataset(seed)
    dataset.to_csv(output_dir / "training_data.csv", index=False)
    dataset.loc[dataset["label"] == "human", FEATURES].to_csv(
        output_dir / "human_only.csv", index=False
    )
    return dataset


def main():
    """Build the default dataset in ML/DATASET."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, default=SEED)
    args = parser.parse_args()
    dataset = write_dataset(seed=args.seed)
    print(f"Wrote {len(dataset)} synthetic rows to {DATASET_DIR}")


if __name__ == "__main__":
    main()
