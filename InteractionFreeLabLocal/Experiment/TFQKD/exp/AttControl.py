#!/usr/bin/env python3
"""Upload and trigger a one-second MEMS voltage waveform on Gen1 or Gen2.

Python API::

    set_waveform("gen1", 1, [0.5, 0.6, 0.7])

Command line::

    python AttControl.py gen1 1 voltages.txt
    python AttControl.py --serve
"""

import argparse
import hashlib
import json
import math
import re
import socket
import struct
import sys
import time
import warnings
from functools import lru_cache
from pathlib import Path
from threading import RLock


GEN1_IP = "192.168.25.56"
GEN2_IP = "192.168.25.55"
GEN2_PORT = 5025
VOLTAGE_MIN = 0.0
VOLTAGE_MAX = 5.0
STEP_SECONDS = 100e-6
STEP_COUNT = round(1.0 / STEP_SECONDS)
GEN2_SAMPLES_PER_STEP = 100
DEVICE_ENDPOINT = "tcp://192.168.25.5:1061"
DEVICE_SERVICE = "AttSim"
MAPPING_PATH = Path(__file__).with_name("AttControlMapping.json")


def _channel_key(generator, channel):
    generator = str(generator).strip().lower()
    generator = {"1": "gen1", "2": "gen2"}.get(generator, generator)
    if generator not in ("gen1", "gen2"):
        raise ValueError("generator must be 'gen1' or 'gen2'")
    if isinstance(channel, bool) or channel not in (1, 2):
        raise ValueError("channel must be 1 or 2")
    return f"{generator}_ch{int(channel)}"


@lru_cache(maxsize=1)
def _calibration():
    content = MAPPING_PATH.read_bytes()
    models = json.loads(content)["channels"]
    for key in ("gen1_ch1", "gen1_ch2", "gen2_ch1", "gen2_ch2"):
        model = models[key]
        coefficients = model["bernstein_coefficients_db"]
        if (len(coefficients) != model["degree"] + 1 or coefficients[0] != 0
                or not all(math.isfinite(value) for value in coefficients)
                or any(after < before for before, after in zip(coefficients, coefficients[1:]))
                or coefficients[-1] <= 0):
            raise ValueError(f"Invalid monotone calibration for {key}")
        lower, upper = model["voltage_range_V"]
        endpoints = sorted([model["peak_voltage_V"], model["peak_voltage_V"] + model["voltage_scale_V"]])
        if (not 0 <= lower < upper <= 5
                or not all(math.isclose(value, endpoint, abs_tol=1e-12) for value, endpoint in zip((lower, upper), endpoints))
                or model["attenuation_range_db"] != [0.0, coefficients[-1]]):
            raise ValueError(f"Invalid calibration range for {key}")
    return models, hashlib.sha256(content).hexdigest()


@lru_cache(maxsize=32768)
def _voltage_from_attenuation(key, attenuation):
    model = _calibration()[0][key]
    coefficients = model["bernstein_coefficients_db"]
    if attenuation == 0:
        return model["peak_voltage_V"]
    if attenuation == coefficients[-1]:
        return model["peak_voltage_V"] + model["voltage_scale_V"]
    lower, upper = 0.0, 1.0
    degree = len(coefficients) - 1
    for _ in range(48):
        position = (lower + upper) / 2
        predicted = sum(value * math.comb(degree, index) * position**index
                        * (1-position)**(degree-index) for index, value in enumerate(coefficients))
        if predicted < attenuation:
            lower = position
        else:
            upper = position
    return model["peak_voltage_V"] + model["voltage_scale_V"] * (lower + upper) / 2


def prepare_attenuation_waveform(generator, channel, attenuations_db):
    """Validate every input dB value before converting to a 1 s voltage waveform."""
    key = _channel_key(generator, channel)
    model = _calibration()[0][key]
    maximum = model["attenuation_range_db"][1]
    try:
        values = list(attenuations_db)
    except TypeError as exc:
        raise ValueError("attenuations_db must be a non-empty sequence") from exc
    if not values or isinstance(attenuations_db, (str, bytes)):
        raise ValueError("attenuations_db must be a non-empty sequence")
    converted = []
    for index, value in enumerate(values):
        try:
            number = float(value)
        except (ValueError, TypeError, OverflowError) as exc:
            raise ValueError(f"{key}: attenuation[{index}] is not a finite number") from exc
        if isinstance(value, bool) or not math.isfinite(number) or not 0 <= number <= maximum:
            raise ValueError(f"{key}: attenuation[{index}]={value!r} outside calibrated range [0, {maximum:.12g}] dB")
        converted.append(number)
    truncated = len(converted) > STEP_COUNT
    if truncated:
        warnings.warn(f"Attenuation sequence has {len(converted)} steps; truncating to {STEP_COUNT} steps (1 s).",
                      RuntimeWarning, stacklevel=2)
    used = converted[:STEP_COUNT]
    voltages = prepare_waveform([_voltage_from_attenuation(key, value) for value in used])
    return voltages, {
        "generator": key.split("_")[0], "channel": int(channel),
        "input_steps": len(converted), "truncated": truncated,
        "attenuation_min_db": min(used), "attenuation_max_db": max(used),
        "voltage_min_V": min(voltages), "voltage_max_V": max(voltages),
        "calibration_sha256": _calibration()[1],
    }


def prepare_waveform(voltages):
    """Validate, truncate or pad voltages to exactly 10,000 steps."""
    try:
        values = [float(value) for value in voltages]
    except (TypeError, ValueError) as exc:
        raise ValueError("voltages must be a non-empty iterable of numbers") from exc

    if not values:
        raise ValueError("voltage sequence cannot be empty")
    if not all(math.isfinite(value) for value in values):
        raise ValueError("voltages must all be finite numbers")
    if any(value < VOLTAGE_MIN or value > VOLTAGE_MAX for value in values):
        raise ValueError("voltages must be between 0 V and 5 V")

    if len(values) > STEP_COUNT:
        warnings.warn(
            f"Voltage sequence has {len(values)} steps; truncating to {STEP_COUNT} steps (1 s).",
            RuntimeWarning,
            stacklevel=2,
        )
        values = values[:STEP_COUNT]
    elif len(values) < STEP_COUNT:
        values.extend([values[-1]] * (STEP_COUNT - len(values)))
    return values


def _normalized_waveform(voltages):
    low = min(voltages)
    high = max(voltages)
    span = high - low
    vpp = max(span, 0.001)
    offset = (high + low) / 2.0
    if span < 0.001:
        offset = min(max(offset, VOLTAGE_MIN + vpp / 2.0), VOLTAGE_MAX - vpp / 2.0)
        normalized = [0.0] * len(voltages)
    else:
        normalized = [2.0 * (value - low) / span - 1.0 for value in voltages]
    return normalized, vpp, offset


def _set_gen1(channel, voltages):
    try:
        from rigol_dg4062 import RigolVXI11
        connection = RigolVXI11(GEN1_IP)
        manager = None
    except ImportError:
        try:
            import pyvisa
        except ImportError as exc:
            raise RuntimeError(
                "Gen1 needs rigol_dg4062.py or pyvisa with a VXI-11 backend"
            ) from exc
        manager = pyvisa.ResourceManager()
        connection = manager.open_resource(f"TCPIP0::{GEN1_IP}::INSTR")

    normalized, vpp, offset = _normalized_waveform(voltages)
    try:
        if manager is not None:
            connection.timeout = 30000
        connection.write(f":OUTPut{channel} OFF")
        connection.write(f":SOURce{channel}:BURSt:STATe OFF")
        connection.write(f":OUTPut{channel}:LOAD INFinity")
        connection.write(f":SOURce{channel}:FUNCtion USER")
        connection.write(f":SOURce{channel}:FREQuency 1")
        connection.write(f":SOURce{channel}:VOLTage {vpp:.9g}")
        connection.write(f":SOURce{channel}:VOLTage:OFFSet {offset:.9g}")
        samples = ",".join(f"{value:.6f}" for value in normalized)
        connection.write(f":SOURce{channel}:DATA VOLATILE,{samples}")

        uploaded_points = int(connection.query(
            f":SOURce{channel}:DATA:POINts? VOLATILE"
        ).strip())
        if uploaded_points != STEP_COUNT:
            raise IOError(
                f"Gen1 CH{channel}: expected {STEP_COUNT} uploaded points, "
                f"instrument reports {uploaded_points}"
            )

        connection.write(":DATA:POINts:INTerpolate OFF")
        connection.write(f":SOURce{channel}:BURSt:STATe ON")
        connection.write(f":SOURce{channel}:BURSt:MODE INFinity")
        connection.write(f":SOURce{channel}:BURSt:TRIGger:SOURce EXTernal")
        connection.write(f":OUTPut{channel} ON")
        error = connection.query(":SYSTem:ERRor?").strip()
        if not error.startswith(("0", "+0")):
            raise IOError(f"Gen1 CH{channel} reported instrument error: {error}")
    finally:
        connection.close()
        if manager is not None:
            manager.close()


def _set_gen2(channel, voltages):
    normalized, vpp, offset = _normalized_waveform(voltages)
    samples = []
    for value in normalized:
        encoded = max(-32768, min(32767, round(value * 32767)))
        samples.extend([encoded] * GEN2_SAMPLES_PER_STEP)
    data = struct.pack(f">{len(samples)}h", *samples)
    source = f"SOURCE{channel}"
    name = f"MEMS{channel}"

    with socket.create_connection((GEN2_IP, GEN2_PORT), timeout=10) as instrument:
        instrument.settimeout(30)

        def write(command):
            instrument.sendall((command + "\n").encode("ascii"))

        def query(command):
            write(command)
            response = bytearray()
            while not response.endswith(b"\n"):
                chunk = instrument.recv(4096)
                if not chunk:
                    raise IOError("Gen2 closed the connection while returning a response")
                response.extend(chunk)
            return response.decode("ascii", errors="replace").strip()

        write(f"OUTPUT{channel} OFF")
        write(f"{source}:DATA:VOL:CLEAR")
        time.sleep(0.3)
        length = str(len(data))
        header = f"{source}:DATA:ARB:DAC {name}, #{len(length)}{length}".encode("ascii")
        instrument.sendall(header + data + b"\n")
        time.sleep(0.5)
        for command in (
            f"{source}:FUNCTION ARB",
            f"{source}:FUNCTION:ARB {name}",
            f"{source}:FUNC:ARB:SRATE 1000000",
            f"{source}:VOLTAGE {vpp:.9g}",
            f"{source}:VOLTAGE:OFFSET {offset:.9g}",
            f"{source}:BURST:STATE ON",
            f"{source}:BURST:MODE TRIGGERED",
            f"{source}:BURST:NCYCLES INFINITY",
            f"TRIGGER{channel}:SOURCE EXT",
            f"OUTPUT{channel} ON",
        ):
            write(command)
            time.sleep(0.1)
        error = query("SYSTEM:ERROR?")
        if not error.startswith(("+0", "0")):
            raise IOError(f"Gen2 CH{channel} reported instrument error: {error}")


def set_waveform(generator, channel, voltages):
    """Configure one generator channel for an externally triggered 1 s loop.

    ``voltages`` is a sequence of per-step voltages in the 0–5 V range. The
    returned list is the exact 10,000-step waveform uploaded to the instrument.
    """
    generator = str(generator).strip().lower()
    if generator in ("1", "gen1"):
        generator = "gen1"
    elif generator in ("2", "gen2"):
        generator = "gen2"
    else:
        raise ValueError("generator must be 'gen1' or 'gen2'")
    if channel not in (1, 2):
        raise ValueError("channel must be 1 or 2")

    waveform = prepare_waveform(voltages)
    if generator == "gen1":
        _set_gen1(channel, waveform)
    else:
        _set_gen2(channel, waveform)
    print(
        f"{generator} CH{channel}: configured {STEP_COUNT} steps "
        "(100 us/step, 1 s), external trigger, continuous repeat"
    )
    return waveform


def _load_voltage_file(path):
    values = []
    for line_number, line in enumerate(Path(path).read_text(encoding="utf-8").splitlines(), 1):
        line = line.split("#", 1)[0].strip()
        if not line:
            continue
        for item in re.split(r"[\s,;]+", line):
            try:
                values.append(float(item))
            except ValueError as exc:
                raise ValueError(f"invalid voltage on line {line_number}: {item!r}") from exc
    return values


class AttControlService:
    def __init__(self):
        self._lock = RLock()

    def getAttenuationCalibration(self):
        models, digest = _calibration()
        return {"sha256": digest, "definition": "dB relative to calibrated peak; no background subtraction",
                "channels": {key: {field: model[field] for field in (
                    "voltage_range_V", "attenuation_range_db", "peak_voltage_V", "source_file")}
                    for key, model in models.items()}}

    def previewAttenuationWaveform(self, generator, channel, attenuations_db):
        waveform, metadata = prepare_attenuation_waveform(generator, channel, attenuations_db)
        return dict(metadata, voltages=waveform, steps=len(waveform),
                    step_seconds=STEP_SECONDS, duration_seconds=STEP_SECONDS*len(waveform))

    def setAttenuationWaveform(self, generator, channel, attenuations_db):
        with self._lock:
            waveform, metadata = prepare_attenuation_waveform(generator, channel, attenuations_db)
            result = self.setWaveform(generator, channel, waveform)
            return dict(result, **{key: value for key, value in metadata.items() if key not in result})

    def setWaveform(self, generator, channel, voltages):
        with self._lock:
            waveform = set_waveform(generator, channel, voltages)
        return {
            "generator": str(generator).lower(),
            "channel": channel,
            "steps": len(waveform),
            "step_seconds": STEP_SECONDS,
            "duration_seconds": STEP_SECONDS * len(waveform),
            "trigger": "external",
            "repeat": "infinite",
        }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("generator", nargs="?", choices=("gen1", "gen2"))
    parser.add_argument("channel", nargs="?", type=int, choices=(1, 2))
    parser.add_argument("voltage_file", nargs="?", help="text file with one voltage per value (comma/space separated)")
    parser.add_argument("--serve", action="store_true", help="register as an IFWorker service")
    parser.add_argument("--endpoint", default=DEVICE_ENDPOINT)
    parser.add_argument("--service", default=DEVICE_SERVICE)
    args = parser.parse_args(argv)

    if args.serve:
        from interactionfreepy import IFWorker, IFLoop

        IFWorker(args.endpoint, args.service, AttControlService(), force=True)
        print(f"IFWorker service {args.service!r} registered at {args.endpoint}", flush=True)
        IFLoop().join()
        return

    if args.generator is None or args.channel is None or args.voltage_file is None:
        parser.error("provide generator, channel and voltage_file, or use --serve")
    set_waveform(args.generator, args.channel, _load_voltage_file(args.voltage_file))


if __name__ == "__main__":
    try:
        main()
    except (OSError, RuntimeError, ValueError) as error:
        print(f"Error: {error}", file=sys.stderr)
        sys.exit(1)
