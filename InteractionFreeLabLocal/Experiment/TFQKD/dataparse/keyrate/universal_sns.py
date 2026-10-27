"""Four-intensity Universal SNS estimates (Hu et al., QST 7, 045031).

Matrices use the order v, x, y, z, with Alice in rows and Bob in columns.
This is an aggregate-data rate estimator: AOPP pairing statistics are predicted,
not observed. See README_universal_sns.md for assumptions and conventions.
"""

import argparse
import json
import math
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np
from scipy.optimize import brentq


SOURCES = ("v", "x", "y", "z")


def entropy(probability):
    if not 0 <= probability <= 1:
        raise ValueError("Entropy requires a probability in [0, 1]")
    if probability in (0, 1):
        return 0.0
    return -(probability * math.log2(probability)
             + (1 - probability) * math.log2(1 - probability))


class Chernoff:
    """Each tail uses epsilon, as in Universal SNS Appendix A."""

    def __init__(self, epsilon=1e-10, asymptotic=False):
        if not 0 < epsilon < 0.5:
            raise ValueError("epsilon must be between zero and 0.5")
        self.epsilon = epsilon
        self.asymptotic = asymptotic
        self.budget = -math.log(epsilon)

    def expected(self, observed, upper=False):
        if not math.isfinite(observed) or observed < 0:
            raise ValueError("Counts must be finite and nonnegative")
        if self.asymptotic:
            return observed
        if observed == 0:
            return self.budget if upper else 0.0
        target = self.budget / observed
        if upper:
            high = max(1.0, 2 * target)
            while high - math.log1p(high) < target:
                high *= 2
            delta = brentq(lambda value: value - math.log1p(value) - target,
                           0, high, xtol=1e-14)
            return observed * (1 + delta)
        if target > 30:
            return 0.0
        delta = brentq(lambda value: -value - math.log1p(-value) - target,
                       0, 1 - 1e-15, xtol=1e-14)
        return observed * (1 - delta)

    def observed(self, expected, upper=False):
        if not math.isfinite(expected) or expected < 0:
            raise ValueError("Means must be finite and nonnegative")
        if self.asymptotic or expected == 0:
            return expected
        target = self.budget / expected
        if upper:
            high = max(1.0, 2 * target)
            while (1 + high) * math.log1p(high) - high < target:
                high *= 2
            delta = brentq(
                lambda value: (1 + value) * math.log1p(value) - value - target,
                0, high, xtol=1e-14)
            return expected * (1 + delta)
        if target >= 1:
            return 0.0
        delta = brentq(
            lambda value: (1 - value) * math.log1p(-value) + value - target,
            0, 1 - 1e-15, xtol=1e-14)
        return expected * (1 - delta)


@dataclass
class Input:
    pulses: float
    emitted: np.ndarray
    detected: np.ndarray
    intensities: np.ndarray
    phase_fraction: float
    phase_errors: float

    def validate(self):
        if not math.isfinite(self.pulses) or self.pulses <= 0:
            raise ValueError("pulses must be finite and positive")
        for name in ("emitted", "detected"):
            matrix = np.asarray(getattr(self, name), dtype=float)
            if matrix.shape != (4, 4) or not np.all(np.isfinite(matrix)) or np.any(matrix < 0):
                raise ValueError(f"{name} must be a nonnegative finite 4 x 4 matrix")
            setattr(self, name, matrix)
        self.intensities = np.asarray(self.intensities, dtype=float)
        if self.intensities.shape != (4,) or not np.all(np.isfinite(self.intensities)):
            raise ValueError("intensities must be [0, mu_x, mu_y, mu_z]")
        if not (self.intensities[0] == 0 < self.intensities[1] < self.intensities[2]
                and self.intensities[3] > 0):
            raise ValueError("Require 0 < mu_x < mu_y and mu_z > 0")
        if not math.isclose(float(self.emitted.sum()), self.pulses, rel_tol=1e-6):
            raise ValueError("Emitted matrix must sum to pulses")
        if np.any(self.detected > self.emitted):
            raise ValueError("Detection counts cannot exceed emitted pulse pairs")
        if not math.isfinite(self.phase_fraction) or not 0 < self.phase_fraction <= 1:
            raise ValueError("phase_fraction must be in (0, 1]")
        if not math.isfinite(self.phase_errors) or not 0 <= self.phase_errors <= self.detected[1, 1]:
            raise ValueError("phase_errors must be between zero and the xx count")


@dataclass
class Result:
    option: str
    profile: str
    status: str = "no_key"
    keyrate: float = 0.0
    key_bits: float = 0.0
    raw_bits: float = 0.0
    bit_error_before: float = 0.0
    bit_error_after: float = 0.0
    n1_before: float = 0.0
    n1_after: float = 0.0
    phase_error_before: float = 0.5
    phase_error_after: float = 0.5
    survived_bits: float = 0.0
    error_correction_bits: float = 0.0
    security_bits: float = 0.0
    disclosure_bits: float = 0.0
    s10: float = 0.0
    s01: float = 0.0
    s1: float = 0.0


def read_scan(path):
    """Read scan.py's four-source, tab-delimited export, without executing it."""
    rows = [line.split("\t") for line in Path(path).read_text(encoding="utf-8-sig").splitlines()]
    values = {row[0]: row[1:] for row in rows if row}
    intensities = [0.0]
    for label in ("X基弱源强度", "X基强光强度", "Z基光源强度"):
        sides = [float(value) for value in values[label]]
        if len(sides) != 2 or not math.isclose(*sides, rel_tol=1e-12, abs_tol=1e-15):
            raise ValueError("Only equal Alice/Bob intensities are supported")
        intensities.append(sides[0])
    pulses = float(values["发送总脉冲数"][0])
    matrices = []
    for label in ("实际发送组合比例", "实际引起有效相应个数"):
        matches = [index for index, row in enumerate(rows) if row[0] == label]
        if len(matches) != 1:
            raise ValueError(f"Require exactly one {label} table")
        start = matches[0]
        labels = ["Z信号态", "X真空态", "X诱骗态1", "X诱骗态2"]
        if rows[start][1:] != labels or [row[0] for row in rows[start + 1:start + 5]] != labels:
            raise ValueError("Require four-source table order Z, vacuum, X1, X2")
        matrix = np.array([[float(value) for value in row[1:5]] for row in rows[start + 1:start + 5]])
        order = [1, 2, 3, 0]
        matrices.append(matrix[np.ix_(order, order)])
    result = Input(pulses, matrices[0] * pulses, matrices[1], np.array(intensities),
                   float(values["X基筛选比例"][0].rstrip("%")) / 100,
                   float(values["X基1"][1]))
    result.validate()
    return result


def from_statistics(statistic, num_photons, phaseSeletcedRatio=1 / 8, scale=1):
    """Adapt four-source nested statistics or scan.py's selected aggregate."""
    if not math.isfinite(scale) or scale <= 0:
        raise ValueError("scale must be finite and positive")
    intensities = np.asarray(num_photons, dtype=float)
    if intensities.shape != (3,):
        raise ValueError("num_photons must contain mu_x, mu_y, mu_z")
    if "signalZ0" in statistic or "signalZ1" in statistic:
        raise ValueError("Five-source statistics belong to the old protocol; supply four-source v,x,y,z statistics")
    if {"pulses", "detections", "errors"}.issubset(statistic):
        emitted = np.asarray(statistic["pulses"], dtype=float)
        detected = np.asarray(statistic["detections"], dtype=float)
        errors = np.asarray(statistic["errors"], dtype=float)
        if errors.shape != (4, 2) or not np.all(np.isfinite(errors)) or np.any(errors < 0):
            raise ValueError("errors must be a nonnegative finite 4 x 2 array: correct, incorrect")
        pulses = float(emitted.sum())
        phase_errors = float(errors[1, 1])
    else:
        basis = ("signal0", "signalX", "signalY", "signalZ")
        pulses = float(statistic["signal"]["signal"]["count"])
        emitted = np.array([[float(statistic[row][column]["ratio"]) * pulses
                             for column in basis] for row in basis])
        detected = np.array([[float(statistic[row][column]["detector_count"])
                              for column in basis] for row in basis])
        phase_errors = float(statistic["Sifted Key"]["XX"]["incorrect"])
    data = Input(pulses * scale, emitted * scale, detected * scale,
                 np.concatenate(([0.0], intensities)), phaseSeletcedRatio, phase_errors * scale)
    data.validate()
    return data


def calKeyRate(statistic, num_photons=(0.0303853, 0.482834, 0.494035),
               phaseSeletcedRatio=1 / 8, strict=False, scale=1, *,
               option="yz", profile="paper", epsilon=None, error_correction=1.16,
               asymptotic=False):
    """Old-style call signature for the four-source Universal SNS protocol.

    strict=False uses epsilon=1e-7; strict=True uses 1e-10 unless overridden.
    transmittance is the aggregate effective efficiency, as in the old API.
    """
    data = from_statistics(statistic, num_photons, phaseSeletcedRatio, scale)
    failure = (1e-10 if strict else 1e-7) if epsilon is None else epsilon
    result = calculate(data, option=option, epsilon=failure, error_correction=error_correction,
                       asymptotic=asymptotic, profile=profile)
    photons = float(np.sum(data.emitted * (data.intensities[:, None] + data.intensities[None, :])))
    transmittance = float(data.detected.sum()) / photons if photons > 0 else None
    attenuation = -10 * math.log10(transmittance) if transmittance and transmittance > 0 else None
    details = {key: float(value) if isinstance(value, np.floating) else value
               for key, value in asdict(result).items()}
    details.update(epsilon=failure, error_correction=error_correction, asymptotic=asymptotic)
    return {"keyrate": float(result.keyrate), "transmittance": transmittance,
            "attenuation": attenuation, "key_bits": float(result.key_bits), "details": details}


def calculate(data, option="yz", epsilon=1e-10, error_correction=1.16,
              asymptotic=False, profile="paper"):
    """Estimate both AOPP subsets; returned post-AOPP counts are their totals."""
    data.validate()
    if option not in ("z", "yz", "xyz"):
        raise ValueError("option must be z, yz or xyz")
    if profile not in ("paper", "scan"):
        raise ValueError("profile must be paper or scan")
    pooled = profile == "scan"
    if not math.isfinite(error_correction) or error_correction < 1:
        raise ValueError("error_correction must be at least one")
    bounds = Chernoff(epsilon, asymptotic)
    selected = [SOURCES.index(source) for source in option]
    codes = [0] + selected
    detected, emitted = data.detected, data.emitted
    mu_x, mu_y = data.intensities[1:3]
    result = Result(option, profile)

    def gain(entries, upper=False):
        count = sum(detected[row, column] for row, column in entries)
        sent = sum(emitted[row, column] for row, column in entries)
        if sent <= 0:
            raise ValueError("Missing required decoy emission counts")
        return bounds.expected(count, upper) / sent

    vacuum_upper = gain([(0, 0)], True)
    vacuum_lower = gain([(0, 0)])

    def single_photon(weak, strong):
        return max(0.0, (math.exp(mu_x) * mu_y ** 2 * gain(weak)
                         - math.exp(mu_y) * mu_x ** 2 * gain(strong, True)
                         - (mu_y ** 2 - mu_x ** 2) * vacuum_upper)
                   / (mu_x * mu_y * (mu_y - mu_x)))

    result.s10 = single_photon([(1, 0)], [(2, 0)])
    result.s01 = single_photon([(0, 1)], [(0, 2)])
    result.s1 = (single_photon([(1, 0), (0, 1)], [(2, 0), (0, 2)])
                 if pooled else (result.s10 + result.s01) / 2)
    weight10 = sum(emitted[source, 0] * data.intensities[source]
                   * math.exp(-data.intensities[source]) for source in selected)
    weight01 = sum(emitted[0, source] * data.intensities[source]
                   * math.exp(-data.intensities[source]) for source in selected)
    n10 = weight10 * result.s10
    n01 = weight01 * result.s01
    n1 = (weight10 + weight01) * result.s1 if pooled else n10 + n01
    result.n1_before = bounds.observed(n10 + n01)
    correct10 = sum(detected[source, 0] for source in selected)
    correct01 = sum(detected[0, source] for source in selected)
    vacuum = detected[0, 0]
    double = sum(detected[row, column] for row in selected for column in selected)
    raw = float(detected[np.ix_(codes, codes)].sum())
    result.raw_bits = raw
    if raw == 0 or min(correct10 + vacuum, correct01 + double) <= 0 or result.s1 <= 0:
        return result
    result.bit_error_before = (vacuum + double) / raw
    groups = min(correct10 + vacuum, correct01 + double) / 2
    odd_random = (correct10 + vacuum) * (correct01 + double) / raw
    sampling = groups / odd_random
    correct_pairs = correct10 / (correct10 + vacuum) * correct01 / (correct01 + double) * groups
    wrong_pairs = vacuum / (correct10 + vacuum) * double / (correct01 + double) * groups
    survived = correct_pairs + wrong_pairs
    if survived <= 0:
        return result
    result.survived_bits = 2 * survived
    result.bit_error_after = wrong_pairs / survived
    nu10 = bounds.observed(sampling * n10)
    nu01 = bounds.observed(sampling * n01)
    nu = bounds.observed(sampling * n1)
    paired = 2 * bounds.observed(nu ** 2 / (2 * sampling * raw))
    leftover = nu - paired
    if paired <= 0 or leftover <= 0:
        return result
    deviation = (0 if asymptotic else
                 math.sqrt(-math.log(epsilon) / ((2 if pooled else 1) * paired)))
    minority = min(nu10, nu01) / nu - deviation
    if not 0 < minority <= 0.5:
        return result
    n1_half = bounds.observed(paired * minority * (1 - minority))
    result.n1_after = 2 * n1_half
    if n1_half <= 0:
        return result
    phase_sent = emitted[1, 1] * data.phase_fraction
    if phase_sent <= 0:
        raise ValueError("Missing xx phase-test emission counts")
    phase_yield = bounds.expected(data.phase_errors, True) / phase_sent
    phase_error = (phase_yield - math.exp(-2 * mu_x) * vacuum_lower / 2) / (
        2 * mu_x * math.exp(-2 * mu_x) * result.s1)
    result.phase_error_before = min(0.5, max(0.0, phase_error))
    if not 0 <= phase_error < 0.5:
        return result
    correction = (0 if asymptotic else
                  -(paired + leftover) * math.log(epsilon / (3 * leftover ** 2)) / leftover)
    if paired <= 2 * correction:
        return result
    phase_upper = bounds.observed(paired * phase_error, True)
    iid_phase = phase_upper / (paired - correction)
    if not 0 <= iid_phase < 0.5:
        return result
    errors_after = bounds.observed((paired / 2 - correction) * iid_phase * (1 - iid_phase), True) + correction
    result.phase_error_after = min(0.5, errors_after / n1_half)
    result.error_correction_bits = error_correction * result.survived_bits * entropy(result.bit_error_after)
    result.security_bits = 0 if asymptotic else (
        2 * math.log2(2 / epsilon) + 4 * math.log2(1 / (math.sqrt(2) * epsilon ** 2)))
    disclosures = 0 if option == "z" else (4 if pooled and option == "xyz" else 2)
    result.disclosure_bits = (0 if asymptotic else
                              disclosures * math.log2(max(1.0, correct10 + correct01)))
    result.key_bits = max(0.0, result.n1_after * (1 - entropy(result.phase_error_after))
                          - result.error_correction_bits - result.security_bits - result.disclosure_bits)
    result.keyrate = result.key_bits / data.pulses
    result.status = "estimated" if result.keyrate > 0 else "no_key"
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("--option", choices=("z", "yz", "xyz"), default="yz")
    parser.add_argument("--epsilon", type=float, default=1e-10)
    parser.add_argument("--error-correction", type=float, default=1.16)
    parser.add_argument("--asymptotic", action="store_true")
    parser.add_argument("--profile", choices=("paper", "scan"), default="paper")
    arguments = parser.parse_args()
    result = calculate(read_scan(arguments.input), arguments.option, arguments.epsilon,
                       arguments.error_correction, arguments.asymptotic, arguments.profile)
    print(json.dumps(asdict(result), indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
