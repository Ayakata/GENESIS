from dataclasses import FrozenInstanceError

import pytest

from genesis.config import AgentConfig, Config, ConfigError, dump_config, parse_config


def test_complete_config_roundtrip():
    config = Config()
    assert parse_config(dump_config(config)) == config
    with pytest.raises(FrozenInstanceError):
        config.seed = 5


@pytest.mark.parametrize(
    "text",
    [
        "",
        "[]",
        "seed: 1",
        "schema_version: 1",
        "schema_version: 3",
        "schema_version: true",
        "schema_version: 2\nseed: -1",
        "schema_version: 2\nseed: 18446744073709551616",
        "schema_version: 2\nseed: 1.5",
        "schema_version: 2\nseed: false",
        "schema_version: 2\nunknown: 2",
        "schema_version: 2\nworld: null",
        "schema_version: 2\nworld: {width: 0}",
        "schema_version: 2\nworld: {width: 1.5}",
        "schema_version: 2\nworld: {width: 5000, height: 5000}",
        "schema_version: 2\nworld: {boundary: invalid}",
        "schema_version: 2\nworld: {widht: 10}",
        "schema_version: 2\nterrain: {kind: plants}",
        "schema_version: 2\nterrain: {islands: 0}",
        "schema_version: 2\nterrain: {radius: 0}",
        "schema_version: 2\nresource: {diffusion: 0.251}",
        "schema_version: 2\nresource: {decay: -0.1}",
        "schema_version: 2\nresource: {initial_min: 2, initial_max: 1}",
        "schema_version: 2\nresource: {source_rate: .nan}",
        "schema_version: 2\nresource: {source_rate: .inf}",
        "schema_version: 2\nresource: {source_rate: true}",
        "schema_version: 2\nconditions: {humidity_max: 1.1}",
        "schema_version: 2\nconditions: {light_min: 0.9, light_max: 0.5}",
        "schema_version: 2\nrun: {steps: -1}",
        "schema_version: 2\nrun: {metrics_interval: 0}",
        "schema_version: 2\nseed: 1\nseed: 2",
        "schema_version: 2\nworld: {width: 1, width: 2}",
        "schema_version: 2\n1: value",
        "schema_version: [",
        "schema_version: 2\nworld: !!python/object:builtins.object {}",
    ],
)
def test_invalid_configuration_is_rejected(text):
    with pytest.raises(ConfigError):
        parse_config(text)


def test_large_config_rejected():
    with pytest.raises(ConfigError, match="1 MiB"):
        parse_config("#" * 1_048_577)


def test_numeric_overflow_is_configuration_error():
    with pytest.raises(ConfigError):
        parse_config("schema_version: 2\nresource: {source_rate: " + "9" * 1000 + "}")


@pytest.mark.parametrize(
    "values",
    [
        {"initial_count": -1},
        {"initial_count": 2, "max_population": 1},
        {"max_population": 1_000_001},
        {"initial_count": 1, "initial_energy": 0},
        {"basal_cost": -0.1},
        {"basal_cost": float("nan")},
        {"assimilation_efficiency": 1.1},
        {"assimilation_efficiency": float("inf")},
        {"death_recycle_fraction": -0.1},
        {"max_age": 0},
        {"reproduction_threshold": 1, "offspring_energy": 1, "reproduction_cost": 1},
    ],
)
def test_invalid_agent_configuration_is_rejected(values):
    with pytest.raises(ConfigError):
        AgentConfig(**values)
