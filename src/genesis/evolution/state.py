"""Counters describing inheritance events without affecting selection."""

from dataclasses import dataclass


@dataclass
class EvolutionLedger:
    mutated_loci: int = 0
    clipped_loci: int = 0
    mutated_offspring: int = 0

    def assert_valid(self) -> None:
        values = (self.mutated_loci, self.clipped_loci, self.mutated_offspring)
        if any(type(value) is not int or value < 0 for value in values):
            raise RuntimeError("Invalid evolution event ledger")
        if self.clipped_loci > self.mutated_loci:
            raise RuntimeError("Clipped loci cannot exceed mutated loci")
