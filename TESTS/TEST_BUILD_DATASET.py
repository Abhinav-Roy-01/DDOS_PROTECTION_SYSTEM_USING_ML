"""Tests for deterministic synthetic training data generation."""

import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "ML", "TRAINING"))

import BUILD_DATASET


def test_dataset_is_deterministic_and_has_expected_classes():
    """The fixed seed produces the same synthetic population each time."""
    first = BUILD_DATASET.build_dataset()
    second = BUILD_DATASET.build_dataset()

    pd.testing.assert_frame_equal(first, second)
    assert len(first) == 4750
    assert first["label"].value_counts().to_dict() == {"human": 3750, "bot": 1000}
    assert first.columns.tolist() == BUILD_DATASET.FEATURES + ["persona", "label"]


def test_entropy_uses_nats_and_element_rate_exceeds_one():
    """Converted entropy and per-second element rates follow the PRD units."""
    dataset = BUILD_DATASET.build_dataset()
    human_rows = dataset.loc[dataset["label"] == "human"]

    assert human_rows["click_interval_entropy"].mean() < 3.0
    assert human_rows["max_element_click_rate"].max() > 1.0


def test_historical_fixtures_are_converted_to_prd_entropy_units():
    """The known synthetic fixtures remain represented after bits-to-nats conversion."""
    dataset = BUILD_DATASET.build_dataset()
    human_fixture = np.array([
        8,
        1524.9435637982203,
        269875.23591802106,
        2.304229902307089 * np.log(2),
        0.3561481826419697,
        1.2012582857050627,
        11,
        5,
    ])
    bot_fixture = np.array([
        200,
        22.60973187772914,
        6.132684489013476,
        0.014982035810896866 * np.log(2),
        0.0,
        39.29298216437756,
        0,
        0,
    ])

    assert np.isclose(dataset[BUILD_DATASET.FEATURES].to_numpy(), human_fixture).all(axis=1).any()
    assert np.isclose(dataset[BUILD_DATASET.FEATURES].to_numpy(), bot_fixture).all(axis=1).any()


def test_dataset_writer_creates_training_and_human_csvs(tmp_path):
    """The writer creates both expected CSV files with the correct columns."""
    dataset = BUILD_DATASET.write_dataset(tmp_path)
    full_dataset = pd.read_csv(tmp_path / "training_data.csv")
    human_only = pd.read_csv(tmp_path / "human_only.csv")

    assert len(full_dataset) == 4750
    assert len(human_only) == 3750
    assert human_only.columns.tolist() == BUILD_DATASET.FEATURES
    assert len(dataset) == len(full_dataset)
