from dataclasses import FrozenInstanceError

import pytest

from genesis.config import Config, ConfigError, dump_config, parse_config


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
        "schema_version: 2",
        "schema_version: true",
        "schema_version: 1\nseed: -1",
        "schema_version: 1\nseed: 18446744073709551616",
        "schema_version: 1\nseed: 1.5",
        "schema_version: 1\nseed: false",
        "schema_version: 1\nunknown: 2",
        "schema_version: 1\nworld: null",
        "schema_version: 1\nworld: {width: 0}",
        "schema_version: 1\nworld: {width: 1.5}",
        "schema_version: 1\nworld: {width: 5000, height: 5000}",
        "schema_version: 1\nworld: {boundary: invalid}",
        "schema_version: 1\nworld: {widht: 10}",
        "schema_version: 1\nterrain: {kind: plants}",
        "schema_version: 1\nterrain: {islands: 0}",
        "schema_version: 1\nterrain: {radius: 0}",
        "schema_version: 1\nresource: {diffusion: 0.251}",
        "schema_version: 1\nresource: {decay: -0.1}",
        "schema_version: 1\nresource: {initial_min: 2, initial_max: 1}",
        "schema_version: 1\nresource: {source_rate: .nan}",
        "schema_version: 1\nresource: {source_rate: .inf}",
        "schema_version: 1\nresource: {source_rate: true}",
        "schema_version: 1\nconditions: {humidity_max: 1.1}",
        "schema_version: 1\nconditions: {light_min: 0.9, light_max: 0.5}",
        "schema_version: 1\nrun: {steps: -1}",
        "schema_version: 1\nrun: {metrics_interval: 0}",
        "schema_version: 1\nseed: 1\nseed: 2",
        "schema_version: 1\nworld: {width: 1, width: 2}",
        "schema_version: 1\n1: value",
        "schema_version: [",
        "schema_version: 1\nworld: !!python/object:builtins.object {}",
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
        parse_config("schema_version: 1\nresource: {source_rate: " + "9" * 1000 + "}")
