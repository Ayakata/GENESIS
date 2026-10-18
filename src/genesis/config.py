"""Strict, immutable, versioned configuration; reject typos rather than silently defaulting."""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field, fields, is_dataclass
from pathlib import Path
from typing import Any, Literal, TypeVar, get_args, get_origin, get_type_hints

import yaml

from genesis import CONFIG_SCHEMA_VERSION


class ConfigError(ValueError):
    """Invalid or unsupported experiment configuration."""


@dataclass(frozen=True)
class WorldConfig:
    width: int = 96
    height: int = 64
    boundary: Literal["closed", "periodic"] = "closed"

    def __post_init__(self) -> None:
        if self.width < 1 or self.height < 1 or self.width * self.height > 4_194_304:
            raise ConfigError("world: dimensions must be positive; at most 4194304 cells")


@dataclass(frozen=True)
class TerrainConfig:
    kind: Literal["uniform", "archipelago"] = "archipelago"
    islands: int = 6
    radius: float = 0.15
    sea_level: float = 0.30
    noise: float = 0.06

    def __post_init__(self) -> None:
        if not 1 <= self.islands <= 128:
            raise ConfigError("terrain.islands must be in [1,128]")
        if not 0 < self.radius <= 1 or not 0 <= self.sea_level < 1 or not 0 <= self.noise <= 1:
            raise ConfigError("terrain: radius in (0,1], sea_level in [0,1), noise in [0,1]")


@dataclass(frozen=True)
class ConditionsConfig:
    equator_temperature: float = 25.0
    polar_drop: float = 20.0
    elevation_drop: float = 10.0
    humidity_min: float = 0.2
    humidity_max: float = 1.0
    light_min: float = 0.3
    light_max: float = 1.0

    def __post_init__(self) -> None:
        if self.polar_drop < 0 or self.elevation_drop < 0:
            raise ConfigError("conditions: temperature drops must be nonnegative")
        for name in ("humidity", "light"):
            if not 0 <= getattr(self, f"{name}_min") <= getattr(self, f"{name}_max") <= 1:
                raise ConfigError(f"conditions: 0 <= {name}_min <= {name}_max <= 1 required")


@dataclass(frozen=True)
class ResourceConfig:
    initial_min: float = 0.5
    initial_max: float = 1.5
    source_rate: float = 0.01
    diffusion: float = 0.10
    decay: float = 0.002

    def __post_init__(self) -> None:
        if not 0 <= self.initial_min <= self.initial_max or self.source_rate < 0:
            raise ConfigError("resource: initial bounds and source_rate must be nonnegative")
        if not 0 <= self.diffusion <= 0.25 or not 0 <= self.decay <= 1:
            raise ConfigError("resource: diffusion in [0,0.25], decay in [0,1] required")


@dataclass(frozen=True)
class RunConfig:
    steps: int = 200
    metrics_interval: int = 10

    def __post_init__(self) -> None:
        if self.steps < 0 or self.metrics_interval < 1:
            raise ConfigError("run: steps >= 0 and metrics_interval >= 1 required")


@dataclass(frozen=True)
class Config:
    schema_version: int = CONFIG_SCHEMA_VERSION
    seed: int = 42
    world: WorldConfig = field(default_factory=WorldConfig)
    terrain: TerrainConfig = field(default_factory=TerrainConfig)
    conditions: ConditionsConfig = field(default_factory=ConditionsConfig)
    resource: ResourceConfig = field(default_factory=ResourceConfig)
    run: RunConfig = field(default_factory=RunConfig)

    def __post_init__(self) -> None:
        if self.schema_version != CONFIG_SCHEMA_VERSION:
            raise ConfigError(f"Unsupported config schema_version: {self.schema_version}")
        if not 0 <= self.seed < 2**64:
            raise ConfigError("seed must be in [0,2**64)")
        # These are intentionally generous numerical guards, not biological constraints.
        values = (*asdict(self.conditions).values(), *asdict(self.resource).values())
        if any(not math.isfinite(v) or abs(v) > 1e12 for v in values):
            raise ConfigError("conditions/resource values must be finite with magnitude <= 1e12")


class _Loader(yaml.SafeLoader):
    pass


def _mapping(loader: _Loader, node: yaml.MappingNode) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node)
        if not isinstance(key, str):
            raise ConfigError("YAML keys must be strings")
        if key in result:
            raise ConfigError(f"Duplicate YAML key: {key}")
        result[key] = loader.construct_object(value_node)
    return result


_Loader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _mapping)
T = TypeVar("T")


def _decode(cls: type[T], raw: Any, path: str) -> T:
    if not isinstance(raw, dict):
        raise ConfigError(f"{path} must be a mapping")
    hints = get_type_hints(cls)
    extra = set(raw) - set(hints)
    if extra:
        raise ConfigError(f"{path}: unknown keys: {', '.join(sorted(map(str, extra)))}")
    values: dict[str, Any] = {}
    for item in fields(cls):  # type: ignore[arg-type]
        if item.name not in raw:
            continue
        value, kind = raw[item.name], hints[item.name]
        label = f"{path}.{item.name}"
        if isinstance(kind, type) and is_dataclass(kind):
            values[item.name] = _decode(kind, value, label)
            continue
        if get_origin(kind) is Literal:
            if value not in get_args(kind) or not isinstance(value, str):
                raise ConfigError(f"{label} must be one of {get_args(kind)}")
        elif kind is int:
            if type(value) is not int:
                raise ConfigError(f"{label} must be an integer")
        elif kind is float:
            if type(value) not in (int, float):
                raise ConfigError(f"{label} must be a finite number")
            try:
                value = float(value)
            except OverflowError as exc:
                raise ConfigError(f"{label} is too large") from exc
            if not math.isfinite(value):
                raise ConfigError(f"{label} must be a finite number")
        values[item.name] = value
    return cls(**values)


def parse_config(text: str) -> Config:
    if len(text.encode("utf-8")) > 1_048_576:
        raise ConfigError("Config exceeds 1 MiB")
    try:
        raw = yaml.load(text, Loader=_Loader)
    except yaml.YAMLError as exc:
        raise ConfigError(f"Invalid YAML: {exc}") from exc
    if not isinstance(raw, dict) or "schema_version" not in raw:
        raise ConfigError("Explicit schema_version is required")
    return _decode(Config, raw, "config")


def load_config(path: Path) -> Config:
    return parse_config(path.read_text(encoding="utf-8"))


def dump_config(config: Config) -> str:
    return yaml.safe_dump(asdict(config), sort_keys=False)
