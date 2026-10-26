#!/usr/bin/env python3
"""Calibrate MEMS transmission and validate remote attenuation waveforms.

VS Code Remote SSH: run the following in a notebook or Python Interactive
Window with the remote Python environment (numpy, matplotlib, interactionfreepy).

    from AttSim import test_random_waveform, plot_random_waveform_test
    result, figure = test_random_waveform(show=True, save_plot=True)

One-channel quick check, with one second each of reference and waveform data:

    result, figure = test_random_waveform(
        channels=(("gen1", 1),), acquisition_seconds=1,
        reference_seconds=1, reference_after=False,
        show=True, save_plot=False,
    )

Raw JSON is always saved. Replot it without accessing hardware:

    figure = plot_random_waveform_test("path/to/random_100Hz_timestamp.json")

Historical counts replay (Alice = Gen1 CH1, Bob = Gen1 CH2):

    prepare_counts_transmission()
    result, figure = validate_counts_waveforms(show=True)
    load_counts_waveforms()

Validation restores both channels; the final load call leaves both waveforms
armed/running. The source, converted JSON and this module must be available in
the Python environment used by VS Code Remote SSH; copying is not automatic.

Running this file directly connects to the control service and loads the saved
Gen1 waveforms. Import the module instead for manual AttSimClient control.
The voltage-calibration CLI is available through an explicit call to main(argv).
"""

import argparse
import ast
import csv
import hashlib
import json
import math
import time
from datetime import datetime, timezone
from pathlib import Path


CONTROL_ENDPOINT = "tcp://code.qpqi.group:1161"
CONTROL_SERVICE = "AttSim"
DATA_BROKER = "tcp://code.qpqi.group:1161"
TDC_COLLECTION = "TFQKD_TDC"
TDC_BLOCK_SECONDS = 1.0
DETECTOR_CHANNEL = {1: 4, 2: 5}
MAX_TRANSMISSION_VOLTAGE = {"gen1": 5.0, "gen2": 0.0}


def _as_utc_datetime(value):
    result = value if isinstance(value, datetime) else datetime.fromisoformat(str(value))
    if result.tzinfo is None:
        result = result.replace(tzinfo=timezone.utc)
    return result.astimezone(timezone.utc)


def _collect_counts(worker, after, acquisition_seconds):
    block_count = round(acquisition_seconds / TDC_BLOCK_SECONDS)
    if not math.isclose(block_count * TDC_BLOCK_SECONDS, acquisition_seconds):
        raise ValueError("acquisition_seconds must be a whole number of 1PPS TDC blocks")

    deadline = time.monotonic() + max(15.0, acquisition_seconds * 3)
    records = {}
    while time.monotonic() < deadline:
        entries = worker.Storage.latest(
            TDC_COLLECTION,
            by="FetchTime",
            filter={"FetchTime": 1, "Data.ChannelMonitor.CountSections": 1},
            length=max(20, block_count * 3),
        )
        for entry in entries or []:
            fetched = entry.get("FetchTime")
            if fetched is None:
                continue
            fetched_at = _as_utc_datetime(fetched)
            if fetched_at <= after:
                continue
            sections = entry["Data"]["ChannelMonitor"]["CountSections"]
            records[fetched_at] = (
                sum(int(value) for value in sections["4"]),
                sum(int(value) for value in sections["5"]),
            )
        if len(records) >= block_count:
            break
        time.sleep(0.25)

    selected = sorted(records.items())[:block_count]
    if len(selected) < block_count:
        raise TimeoutError(
            f"Collected {len(selected)} of {block_count} required 1PPS TDC blocks"
        )
    return (
        selected[0][0],
        selected[-1][0],
        sum(record[0] for _, record in selected),
        sum(record[1] for _, record in selected),
        len(selected),
    )


def calibrate_transmission(
    generator,
    channel,
    voltage_range=(0.0, 5.0),
    points=100,
    wait_seconds=3.0,
    acquisition_seconds=5.0,
    save_dir="./mems_calibration",
    control_endpoint=CONTROL_ENDPOINT,
    control_service=CONTROL_SERVICE,
    data_broker=DATA_BROKER,
    control_worker=None,
    data_worker=None,
    restore=True,
):
    """Sweep one MEMS channel; save TDC counts and relative transmission.

    The control call goes to ``AttSim.setWaveform`` while counts are read from
    ``TFQKD_TDC``. CH1 maps to detector CH4 and CH2 maps to detector CH5.
    """
    generator = str(generator).strip().lower()
    if generator not in ("gen1", "gen2"):
        raise ValueError("generator must be 'gen1' or 'gen2'")
    if channel not in (1, 2):
        raise ValueError("channel must be 1 or 2")
    if isinstance(points, bool) or not isinstance(points, int) or points < 1:
        raise ValueError("points must be a positive integer")
    if not math.isfinite(wait_seconds) or wait_seconds < 0:
        raise ValueError("wait_seconds must be a finite non-negative number")
    if not math.isfinite(acquisition_seconds) or acquisition_seconds <= 0:
        raise ValueError("acquisition_seconds must be a finite positive number")
    block_count = round(acquisition_seconds / TDC_BLOCK_SECONDS)
    if block_count < 1 or not math.isclose(block_count * TDC_BLOCK_SECONDS, acquisition_seconds):
        raise ValueError("acquisition_seconds must be a whole number of 1PPS TDC blocks")
    if len(voltage_range) != 2:
        raise ValueError("voltage_range must contain (start, stop)")
    start, stop = map(float, voltage_range)
    if (not math.isfinite(start) or not math.isfinite(stop)
            or start < 0 or stop > 5 or start > stop):
        raise ValueError("voltage_range must be an ascending range within 0–5 V")

    from interactionfreepy import IFWorker

    if control_worker is None:
        control_worker = IFWorker(control_endpoint, timeout=30)
    if data_worker is None:
        data_worker = IFWorker(data_broker, timeout=10)
    remote_control = getattr(control_worker, control_service)

    directory = Path(save_dir).expanduser()
    directory.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().astimezone().strftime("%Y%m%d_%H%M%S_%f")
    output_path = directory / f"{generator}_ch{channel}_{stamp}.csv"
    voltages = [start] if points == 1 else [
        start + (stop - start) * index / (points - 1)
        for index in range(points)
    ]
    fields = (
        "generator", "channel", "detector_channel", "voltage_V",
        "first_fetch_time", "last_fetch_time", "acquisition_blocks",
        "acquisition_seconds", "raw_counts_ch4", "raw_counts_ch5",
        "counts_ch4_per_s", "counts_ch5_per_s", "target_counts_per_s",
        "relative_transmission",
    )
    changed_hardware = False

    try:
        with output_path.open("w", newline="", encoding="utf-8") as output:
            writer = csv.DictWriter(output, fieldnames=fields)
            writer.writeheader()
            for index, voltage in enumerate(voltages, 1):
                remote_control.setWaveform(generator, channel, [voltage])
                changed_hardware = True
                time.sleep(wait_seconds)
                acquisition_started = datetime.now(timezone.utc)
                first_fetch, last_fetch, total_ch4, total_ch5, measured_blocks = _collect_counts(
                    data_worker, acquisition_started, acquisition_seconds
                )
                counts_ch4 = total_ch4 / acquisition_seconds
                counts_ch5 = total_ch5 / acquisition_seconds
                detector_channel = DETECTOR_CHANNEL[channel]
                target_counts = counts_ch4 if detector_channel == 4 else counts_ch5
                writer.writerow({
                    "generator": generator,
                    "channel": channel,
                    "detector_channel": detector_channel,
                    "voltage_V": f"{voltage:.6f}",
                    "first_fetch_time": first_fetch.isoformat(),
                    "last_fetch_time": last_fetch.isoformat(),
                    "acquisition_blocks": measured_blocks,
                    "acquisition_seconds": f"{acquisition_seconds:.3f}",
                    "raw_counts_ch4": total_ch4,
                    "raw_counts_ch5": total_ch5,
                    "counts_ch4_per_s": counts_ch4,
                    "counts_ch5_per_s": counts_ch5,
                    "target_counts_per_s": target_counts,
                    "relative_transmission": "",
                })
                output.flush()
                print(
                    f"{index}/{points}: {voltage:.4f} V, "
                    f"CH4={counts_ch4:.1f}/s, CH5={counts_ch5:.1f}/s "
                    f"({measured_blocks} blocks / {acquisition_seconds:g} s)"
                )

        with output_path.open(encoding="utf-8") as source:
            rows = list(csv.DictReader(source))
        maximum = max(float(row["target_counts_per_s"]) for row in rows)
        with output_path.open("w", newline="", encoding="utf-8") as output:
            writer = csv.DictWriter(output, fieldnames=fields)
            writer.writeheader()
            for row in rows:
                rate = float(row["target_counts_per_s"])
                row["relative_transmission"] = "" if maximum == 0 else f"{rate / maximum:.9g}"
                writer.writerow(row)
        return output_path
    finally:
        if restore and changed_hardware:
            remote_control.setWaveform(
                generator,
                channel,
                [MAX_TRANSMISSION_VOLTAGE[generator]],
            )


def _collect_waveform_blocks(worker, seconds):
    """Keep raw 1 ms bins; discard one boundary block after settling.

    FetchTime is a receipt timestamp, not a hardware acquisition timestamp.
    The one-second guard assumes normal, promptly delivered TDC blocks.
    """
    import numpy as np

    cutoff = datetime.now(timezone.utc).timestamp() + TDC_BLOCK_SECONDS
    deadline = time.monotonic() + max(20, seconds * 3)
    records = {}
    while time.monotonic() < deadline:
        entries = worker.Storage.latest(
            TDC_COLLECTION, by="FetchTime",
            filter={"FetchTime": 1, "Data.ChannelMonitor.CountSections": 1},
            length=max(20, seconds * 3),
        )
        for entry in entries or []:
            stamp = _as_utc_datetime(entry["FetchTime"])
            if stamp.timestamp() <= cutoff:
                continue
            sections = entry["Data"]["ChannelMonitor"]["CountSections"]
            record = {"fetch_time": stamp.isoformat()}
            for detector in (4, 5):
                values = np.asarray(sections[str(detector)], dtype=float)
                if values.shape != (1000,) or not np.all(np.isfinite(values)) or np.any(values < 0):
                    raise ValueError("Expected 1000 finite, nonnegative 1 ms counts per detector")
                record[f"ch{detector}"] = values.tolist()
            records[stamp] = record
        if len(records) >= seconds:
            return [records[stamp] for stamp in sorted(records)[:seconds]]
        time.sleep(0.25)
    raise TimeoutError(f"Collected {len(records)} of {seconds} required TDC blocks")


def _analyse_random_waveform(entry, step_ms, edge_ms):
    import numpy as np

    detector = entry["target_detector"]
    observations = np.array([record[detector] for record in entry["random"]])
    before = np.mean([record[detector] for record in entry["before"]])
    after = np.mean([record[detector] for record in entry["after"]]) if entry.get("after") else before
    baseline = (before + after) / 2
    if baseline <= 0:
        raise ValueError("No baseline light for attenuation measurement")
    levels = np.array(entry["levels_db"])
    template = np.repeat(10 ** (-levels / 10), step_ms)
    templates = np.array([np.roll(template, lag) for lag in range(1000)])
    centered = templates - templates.mean(axis=1, keepdims=True)
    centered_observations = observations - observations.mean(axis=1, keepdims=True)
    denominator = np.linalg.norm(centered, axis=1)[:, None] * np.linalg.norm(centered_observations, axis=1)
    correlations = np.divide(centered @ centered_observations.T, denominator,
                             out=np.zeros_like(denominator), where=denominator > 0)
    best_lags = np.argmax(correlations, axis=0)
    lag = int(best_lags[0])
    selected = correlations[lag]
    detected = bool(np.all(selected > 0.8))
    aligned = np.array([np.roll(record, -lag) for record in observations])
    plateau = aligned.reshape(len(aligned), len(levels), step_ms)[:, :, edge_ms:step_ms-edge_ms]
    totals = plateau.sum(axis=(0, 2))
    measured = np.full(len(levels), np.nan)
    positive = totals > 0
    measured[positive] = -10 * np.log10(totals[positive] / (plateau.shape[0] * plateau.shape[2]) / baseline)
    errors = measured - levels
    sigma = np.full(len(levels), np.nan)
    sigma[positive] = 10 / np.log(10) / np.sqrt(totals[positive])
    other = "ch5" if detector == "ch4" else "ch4"
    other_profile = np.mean([record[other] for record in entry["random"]], axis=0)
    other_correlation = float(np.corrcoef(other_profile, templates[lag])[0, 1]) if np.std(other_profile) > 0 else None
    return {
        "sequence_detected": detected,
        "phase_validation": "same record fitted; no independent repeat" if len(observations) == 1 else "first-record phase checked on later records",
        "lag_ms": lag, "best_lags_ms": best_lags.tolist(),
        "correlations": selected.tolist(), "baseline_counts_per_ms": float(baseline),
        "reference_change_percent": float(100 * (after / before - 1)) if entry.get("after") and before > 0 else None,
        "other_detector_correlation": other_correlation,
        "measured_plateau_db": [float(value) if np.isfinite(value) else None for value in measured] if detected else None,
        "counting_sigma_db": [float(value) if np.isfinite(value) else None for value in sigma] if detected else None,
        "zero_count_plateaus": int(np.sum(~positive)),
        "error_mean_db": float(np.nanmean(errors)) if detected and positive.any() else None,
        "error_std_db": float(np.nanstd(errors)) if detected and positive.any() else None,
        "error_rmse_db": float(np.sqrt(np.nanmean(errors ** 2))) if detected and positive.any() else None,
    }


def plot_random_waveform_test(result, save_path=None, show=True):
    """Plot saved results without touching hardware; use the active backend.

    On VS Code Remote SSH use a notebook or Python Interactive Window.
    A normal headless SSH terminal cannot display a desktop GUI with show().
    """
    import numpy as np
    import matplotlib.pyplot as plt

    if isinstance(result, (str, Path)):
        result = json.loads(Path(result).read_text(encoding="utf-8"))
    entries = [(key, entry) for key, entry in result["channels"].items() if "analysis" in entry]
    if not entries:
        raise ValueError("No analysed channels to plot")
    figure, axes = plt.subplots(len(entries), 2, figsize=(15, 3.8 * len(entries)), squeeze=False, constrained_layout=True)
    lower, upper = result["attenuation_range"]
    for row, (key, entry) in enumerate(entries):
        analysis = entry["analysis"]
        levels = np.array(entry["levels_db"])
        observations = np.array([record[entry["target_detector"]] for record in entry["random"]])
        detected = analysis["sequence_detected"]
        lag = analysis["lag_ms"] if detected else 0
        transmission = np.roll(observations.mean(axis=0), -lag) / analysis["baseline_counts_per_ms"]
        expected = np.repeat(10 ** (-levels / 10), result["step_ms"])
        waveform_axis, error_axis = axes[row]
        waveform_axis.step(np.arange(1000), expected, where="post", color="black", linewidth=1, label="Requested")
        waveform_axis.plot(np.where(transmission > 0, transmission, np.nan), linewidth=.8, label=f"Measured: {len(observations)} cycle(s)")
        waveform_axis.set_yscale("log")
        waveform_axis.set_ylim(10 ** (-upper / 10), 10 ** (-lower / 10))
        ticks = np.linspace(lower, upper, 6)
        waveform_axis.set_yticks(10 ** (-ticks / 10), [f"{value:g} dB" for value in ticks])
        waveform_axis.set(xlim=(0, 1000), xlabel="Time (ms)", ylabel="Transmission (log y; dB labels)",
                          title=f"{key}: {'sequence detected' if detected else 'NOT following sequence; unaligned'}")
        waveform_axis.legend(fontsize=8)
        waveform_axis.grid(alpha=.25)
        if detected:
            measured = np.array([np.nan if value is None else value for value in analysis["measured_plateau_db"]])
            sigma = np.array([np.nan if value is None else value for value in analysis["counting_sigma_db"]])
            error_axis.errorbar(levels, measured-levels, yerr=sigma, fmt=".", alpha=.7, label="Plateau error ±1σ counting noise")
            error_axis.axhline(0, color="black", linewidth=1)
            error_axis.set(xlim=(lower, upper), xlabel="Requested attenuation (dB)", ylabel="Measured minus requested (dB)",
                           title=f"Bias {analysis['error_mean_db']:+.3f}; SD {analysis['error_std_db']:.3f}; RMSE {analysis['error_rmse_db']:.3f} dB")
            error_axis.legend(fontsize=8)
            error_axis.grid(alpha=.25)
        else:
            error_axis.text(.5, .5, "No valid dynamic accuracy: sequence not detected", ha="center", transform=error_axis.transAxes)
            error_axis.set_axis_off()
    figure.suptitle(f"{result['frequency_hz']} Hz random waveform | central plateau bins only | no background subtraction\nZero-count plateaus omitted from dB statistics; display clipped to requested attenuation range")
    if save_path is not None:
        figure.savefig(save_path, dpi=160)
    if show:
        plt.show()
    return figure


def test_random_waveform(
    channels=(("gen1", 1), ("gen1", 2), ("gen2", 1), ("gen2", 2)),
    frequency_hz=100, attenuation_range=(0.0, 25.0), acquisition_seconds=20,
    reference_seconds=5, wait_seconds=2.0, reference_after=True, edge_ms=2,
    seed=20261026, save_dir="./mems_waveform_tests", show=True, save_plot=True,
    control_endpoint=CONTROL_ENDPOINT, control_service=CONTROL_SERVICE,
    data_broker=DATA_BROKER, control_worker=None, data_worker=None,
):
    """Test channels sequentially with 1 s external-triggered random waveforms.

    Saves raw CH4/CH5 1000×1 ms bins, metadata, analysis and optional PNG.
    Returns (result, figure). Plot display happens only after hardware restoration.
    Fast example: channels=(("gen1", 1),), acquisition_seconds=1,
    reference_seconds=1, reference_after=False. This cannot check repeatability
    or reference drift. Every plateau uses only its central bins; zero counts
    have undefined dB values. Counting error bars exclude baseline uncertainty.
    Restoration is the established maximum-transmission voltage (Gen1 5 V,
    Gen2 0 V), NOT a snapshot of any pre-existing arbitrary waveform.
    Other channels are not modified; keep them constant during this test.
    """
    import numpy as np
    from interactionfreepy import IFWorker

    channels = tuple((str(generator).lower(), channel) for generator, channel in channels)
    if not channels or len(set(channels)) != len(channels) or any(generator not in MAX_TRANSMISSION_VOLTAGE or channel not in (1, 2) for generator, channel in channels):
        raise ValueError("channels must contain unique (gen1/gen2, 1/2) pairs")
    for name, value in (("frequency_hz", frequency_hz), ("acquisition_seconds", acquisition_seconds), ("reference_seconds", reference_seconds)):
        if isinstance(value, bool) or not isinstance(value, int) or value < 1:
            raise ValueError(f"{name} must be a positive integer")
    if 1000 % frequency_hz or frequency_hz < 2:
        raise ValueError("frequency_hz must divide 1000 and be at least 2")
    step_ms = 1000 // frequency_hz
    if not isinstance(edge_ms, int) or edge_ms < 0 or edge_ms * 2 >= step_ms:
        raise ValueError("edge_ms must leave at least one interior 1 ms bin")
    lower, upper = map(float, attenuation_range)
    if not all(math.isfinite(value) for value in (lower, upper, wait_seconds)) or not 0 <= lower < upper or wait_seconds < 0:
        raise ValueError("Invalid attenuation range or wait_seconds")
    control_worker = control_worker if control_worker is not None else IFWorker(control_endpoint, timeout=60)
    data_worker = data_worker if data_worker is not None else IFWorker(data_broker, timeout=30)
    remote = getattr(control_worker, control_service)
    for generator, channel in channels:
        remote.previewAttenuationWaveform(generator, channel, [lower, upper])
    directory = Path(save_dir).expanduser().resolve()
    directory.mkdir(parents=True, exist_ok=True)
    stem = directory / f"random_{frequency_hz}Hz_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}"
    json_path, png_path = stem.with_suffix(".json"), stem.with_suffix(".png")
    result = {"started_at": datetime.now(timezone.utc).isoformat(), "frequency_hz": frequency_hz,
              "step_ms": step_ms, "hardware_step_us": 100, "attenuation_range": [lower, upper],
              "acquisition_seconds": acquisition_seconds, "reference_seconds": reference_seconds,
              "wait_seconds": wait_seconds, "boundary_guard_seconds": 1, "edge_ms": edge_ms,
              "calibration": remote.getAttenuationCalibration(), "channels": {},
              "json_path": str(json_path), "png_path": str(png_path) if save_plot else None}

    def save():
        json_path.write_text(json.dumps(result, indent=2, allow_nan=False) + "\n", encoding="utf-8")

    started = time.monotonic()
    for generator, channel in channels:
        key = f"{generator}_ch{channel}"
        channel_seed = seed + (0 if generator == "gen1" else 10) + channel
        levels = np.random.default_rng(channel_seed).uniform(lower, upper, frequency_hz)
        levels[:min(3, frequency_hz)] = [min(upper, max(lower, 10)), upper, lower][:min(3, frequency_hz)]
        if frequency_hz == 2:
            levels[:] = [lower, upper]
        entry = {"seed": channel_seed, "levels_db": levels.tolist(), "target_detector": f"ch{DETECTOR_CHANNEL[channel]}", "restored": False, "timings_seconds": {}}
        result["channels"][key] = entry

        def measure(label, waveform, seconds):
            phase_started = time.monotonic()
            remote.setAttenuationWaveform(generator, channel, waveform)
            entry["timings_seconds"][f"{label}_command"] = time.monotonic() - phase_started
            time.sleep(wait_seconds)
            entry[label] = _collect_waveform_blocks(data_worker, seconds)
            entry["timings_seconds"][label] = time.monotonic() - phase_started
            save()
            print(f"{key}: {label}, {seconds} blocks, {entry['timings_seconds'][label]:.2f} s", flush=True)

        try:
            measure("before", [0], reference_seconds)
            measure("random", np.repeat(levels, step_ms * 10).tolist(), acquisition_seconds)
            if reference_after:
                measure("after", [0], reference_seconds)
            entry["analysis"] = _analyse_random_waveform(entry, step_ms, edge_ms)
        except BaseException as error:
            entry["error"] = repr(error)
            raise
        finally:
            restore_started = time.monotonic()
            try:
                remote.setWaveform(generator, channel, [MAX_TRANSMISSION_VOLTAGE[generator]])
                entry["restored"] = True
            except BaseException as error:
                entry["restore_error"] = repr(error)
                raise
            finally:
                entry["timings_seconds"]["restore"] = time.monotonic() - restore_started
                save()
    result["elapsed_measurement_seconds"] = time.monotonic() - started
    result["finished_at"] = datetime.now(timezone.utc).isoformat()
    save()
    figure = plot_random_waveform_test(result, png_path if save_plot else None, show=show)
    return result, figure


def prepare_counts_transmission(source_path=None, output_path=None, max_attenuation_db=25.0):
    """Normalize Alice/Bob independently and linearly interpolate to 100 us.

    Alice = counts[:1000], Bob = counts[-2000:-1000]. Sample times are
    0..999 ms; the final 0.9 ms holds the last sample, without wraparound.
    Clipping happens AFTER interpolation in transmission, not in dB.
    Both unclipped and applied transmissions are retained in the saved JSON.
    Regeneration resets any measured-mean balancing previously applied with
    balance_counts_transmission(); omit this call when loading balanced data.
    """
    import numpy as np

    source_path = Path(source_path) if source_path else Path(__file__).with_name("counts1ms.py")
    output_path = Path(output_path) if output_path else Path(__file__).with_name("CountsTransmission100us.json")
    if not math.isfinite(max_attenuation_db) or max_attenuation_db <= 0:
        raise ValueError("max_attenuation_db must be finite and positive")
    source = source_path.read_bytes()
    assignments = [node for node in ast.parse(source).body if isinstance(node, ast.Assign)
                   and any(isinstance(target, ast.Name) and target.id == "counts" for target in node.targets)]
    if len(assignments) != 1:
        raise ValueError("Expected exactly one literal counts assignment")
    counts = np.asarray(ast.literal_eval(assignments[0].value), dtype=float)
    if counts.ndim != 1 or len(counts) < 2000 or not np.all(np.isfinite(counts)) or np.any(counts < 0):
        raise ValueError("counts must contain at least 2000 finite nonnegative values")
    result = {"source": str(source_path.resolve()), "source_sha256": hashlib.sha256(source).hexdigest(),
              "source_samples": len(counts), "step_us": 100, "duration_seconds": 1,
              "interpolation": "linear transmission; last sample held from 999 to 999.9 ms",
              "normalization": "independent segment maximum", "max_attenuation_db": max_attenuation_db,
              "channels": {}}
    floor = 10 ** (-max_attenuation_db / 10)
    for name, segment, generator, channel, selection in (
        ("Alice", counts[:1000], "gen1", 1, "[:1000]"),
        ("Bob", counts[-2000:-1000], "gen1", 2, "[-2000:-1000]"),
    ):
        peak = float(segment.max())
        if peak <= 0:
            raise ValueError(f"{name} has no positive counts")
        normalized = segment / peak
        interpolated = np.interp(np.arange(10000) / 10, np.arange(1000), normalized)
        applied = np.maximum(interpolated, floor)
        result["channels"][name] = {"generator": generator, "channel": channel,
            "source_slice": selection, "normalization_counts": peak,
            "counts_1ms": segment.tolist(), "transmission_1ms": normalized.tolist(),
            "unclipped_transmission_100us": interpolated.tolist(),
            "transmission_100us": applied.tolist(), "clipped_samples": int(np.sum(interpolated < floor))}
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(result, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    return result


def generate_compensation_waveforms(rho, data_path=None):
    """Return Gen2 compensation arrays in memory; no writes or network calls.

    Implements paper Strategy 2: only attenuate the higher-transmission arm
    when its ratio to the lower arm exceeds rho. Alice maps to Gen2 CH1,
    Bob to Gen2 CH2. Uses the currently saved, balanced Gen1 transmissions.
    Ideal combined transmission excludes fixed losses and calibration errors.
    This does not validate the live device calibration or load any hardware.
    """
    import numpy as np

    if isinstance(rho, bool) or not math.isfinite(rho) or rho < 1:
        raise ValueError("rho must be finite and >= 1")
    path = Path(data_path) if data_path else Path(__file__).with_name("CountsTransmission100us.json")
    source_bytes = path.read_bytes()
    data = json.loads(source_bytes)
    if data["step_us"] != 100 or data["duration_seconds"] != 1:
        raise ValueError("Expected a 1-second waveform with 100 us samples")
    transmissions = {}
    for name, channel in (("Alice", 1), ("Bob", 2)):
        source = data["channels"][name]
        if (source["generator"], source["channel"]) != ("gen1", channel):
            raise ValueError(f"Unexpected Gen1 mapping for {name}")
        values = np.asarray(source["transmission_100us"], dtype=float)
        if values.shape != (10000,) or not np.all(np.isfinite(values)) or np.any(values <= 0) or np.any(values > 1):
            raise ValueError("Gen1 transmission must contain 10000 finite values in (0, 1]")
        transmissions[name] = values
    alice, bob = transmissions["Alice"], transmissions["Bob"]
    compensation = {
        "Alice": np.exp(np.minimum(0, math.log(rho) + np.log(bob) - np.log(alice))),
        "Bob": np.exp(np.minimum(0, math.log(rho) + np.log(alice) - np.log(bob))),
    }
    combined = {name: transmissions[name] * compensation[name] for name in transmissions}
    ratio_before = np.maximum(alice, bob) / np.minimum(alice, bob)
    ratio_after = np.maximum(combined["Alice"], combined["Bob"]) / np.minimum(combined["Alice"], combined["Bob"])
    return {
        "rho": float(rho), "step_us": 100, "duration_seconds": 1,
        "source_path": str(path.resolve()), "source_sha256": hashlib.sha256(source_bytes).hexdigest(),
        "time_ms": np.arange(10000) / 10,
        "channels": {
            name: {"generator": "gen2", "channel": channel,
                   "gen1_transmission": transmissions[name],
                   "transmission_100us": compensation[name],
                   "attenuation_db": -10 * np.log10(compensation[name]),
                   "combined_transmission": combined[name]}
            for name, channel in (("Alice", 1), ("Bob", 2))
        },
        "ratio_before": ratio_before, "ratio_after": ratio_after,
        "compensated_fraction": float(np.mean(ratio_before > rho)),
    }


def plot_compensation_waveforms(result, show=True):
    """Plot in-memory compensation, without saving files or accessing devices."""
    import matplotlib.pyplot as plt

    figure, axes = plt.subplots(2, 2, figsize=(15, 8), constrained_layout=True)
    for name, color in (("Alice", "tab:blue"), ("Bob", "tab:orange")):
        entry = result["channels"][name]
        for axis, field in ((axes[0, 0], "gen1_transmission"),
                            (axes[0, 1], "transmission_100us"),
                            (axes[1, 0], "combined_transmission")):
            axis.plot(result["time_ms"], entry[field], label=name, color=color, linewidth=.9)
            axis.set_yscale("log")
    axes[0, 0].set_title("Gen1: original balanced transmission")
    axes[0, 1].set_title("Gen2: compensation (1 = no added attenuation)")
    axes[1, 0].set_title("Predicted Gen1 × Gen2 transmission")
    ratio_axis = axes[1, 1]
    ratio_axis.plot(result["time_ms"], result["ratio_before"], label="Before", linewidth=.9, alpha=.7)
    ratio_axis.plot(result["time_ms"], result["ratio_after"], label="After", linewidth=1.1)
    ratio_axis.axhline(result["rho"], color="black", linestyle="--", label=f"Threshold rho = {result['rho']:g}")
    ratio_axis.set_yscale("log")
    ratio_axis.set_title("Higher / lower transmission: capped at rho")
    for axis in axes.flat:
        axis.set_xlim(0, 1000)
        axis.set_xlabel("Time (ms)")
        axis.set_ylabel("Transmission" if axis is not ratio_axis else "Ratio")
        axis.grid(alpha=.25, which="both")
        axis.legend(fontsize=9)
    figure.suptitle(f"Paper Strategy 2 Compensation | rho = {result['rho']:g}\nOnly the brighter arm is attenuated; no time slices discarded; ideal prediction, not a hardware measurement")
    if show:
        plt.show()
    return figure


def _counts_waveform_commands(data, remote):
    import numpy as np

    if data["step_us"] != 100 or data["duration_seconds"] != 1:
        raise ValueError("Expected 100 us sampling and exactly 1 second")
    commands = []
    for name, generator, channel in (("Alice", "gen1", 1), ("Bob", "gen1", 2)):
        entry = data["channels"][name]
        if (entry["generator"], entry["channel"]) != (generator, channel):
            raise ValueError(f"Invalid channel mapping for {name}")
        transmission = np.asarray(entry["transmission_100us"], dtype=float)
        if transmission.shape != (10000,) or not np.all(np.isfinite(transmission)) or np.any(transmission <= 0) or np.any(transmission > 1):
            raise ValueError("Transmission must contain 10000 finite values in (0, 1]")
        attenuation = (-10 * np.log10(transmission)).tolist()
        remote.previewAttenuationWaveform(generator, channel, attenuation)
        commands.append((generator, channel, attenuation))
    return commands


def balance_counts_transmission(validation_path, data_path=None, control_worker=None):
    """Match measured mean transmissions by attenuating the brighter arm.

    Uses each arm's own zero-dB reference, not absolute detector counts.
    Saves a scaled waveform after remote range validation; no hardware writes.
    The previous validation must correspond exactly to the current waveforms.
    Constant scaling preserves the attenuation span, without new clipping.
    """
    import numpy as np
    from interactionfreepy import IFWorker

    path = Path(data_path) if data_path else Path(__file__).with_name("CountsTransmission100us.json")
    data = json.loads(path.read_text(encoding="utf-8"))
    validation = json.loads(Path(validation_path).read_text(encoding="utf-8"))
    means = {}
    for name, source in data["channels"].items():
        tested = validation["waveform_source"]["channels"][name]
        if (tested["generator"], tested["channel"], tested["transmission_100us"]) != (source["generator"], source["channel"], source["transmission_100us"]):
            raise ValueError("Validation does not match the current channel waveforms")
        entry = validation["channels"][f"{name}_{source['generator']}_ch{source['channel']}"]
        if not entry["analysis"]["sequence_detected"]:
            raise ValueError(f"{name}: no valid waveform execution in reference test")
        means[name] = float(np.mean([record[entry["target_detector"]] for record in entry["random"]]) / entry["analysis"]["baseline_counts_per_ms"])
        if not math.isfinite(means[name]) or means[name] <= 0:
            raise ValueError("Measured mean transmission must be finite and positive")
    target = min(means.values())
    adjustment = {"validation_path": str(Path(validation_path).resolve()),
                  "measured_mean_transmissions": means, "target_mean_transmission": target,
                  "scale_factors": {}, "added_attenuation_db": {}}
    for name, source in data["channels"].items():
        scale = target / means[name]
        source.setdefault("unbalanced_transmission_100us", source["transmission_100us"][:])
        source["transmission_100us"] = (np.asarray(source["transmission_100us"]) * scale).tolist()
        adjustment["scale_factors"][name] = scale
        adjustment["added_attenuation_db"][name] = float(-10 * np.log10(scale))
    worker = control_worker if control_worker is not None else IFWorker(CONTROL_ENDPOINT, timeout=60)
    _counts_waveform_commands(data, worker.AttSim)
    data.setdefault("source_clipping_limit_db", data["max_attenuation_db"])
    data["max_attenuation_db"] = max(-10 * math.log10(min(source["transmission_100us"])) for source in data["channels"].values())
    data.setdefault("mean_balance_history", []).append(adjustment)
    path.write_text(json.dumps(data, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    return adjustment


def load_counts_waveforms(data_path=None, control_worker=None, control_endpoint=CONTROL_ENDPOINT):
    """Load Alice on Gen1 CH1 and Bob on Gen1 CH2; leave both armed/running.

    Both full sequences are range-checked before changing hardware. Calls are
    sequential, not atomic; common 1PPS wiring is required for hardware sync.
    Gen1 CH2 previously failed external-trigger tests; validate its output
    rather than treating successful command submission as successful playback.
    On failure both target channels are restored to maximum transmission.
    """
    from interactionfreepy import IFWorker

    path = Path(data_path) if data_path else Path(__file__).with_name("CountsTransmission100us.json")
    data = json.loads(path.read_text(encoding="utf-8"))
    worker = control_worker if control_worker is not None else IFWorker(control_endpoint, timeout=60)
    remote = worker.AttSim
    commands = _counts_waveform_commands(data, remote)
    try:
        responses = [remote.setAttenuationWaveform(generator, channel, attenuation)
                     for generator, channel, attenuation in commands]
    except BaseException:
        for generator, channel, _ in commands:
            try:
                remote.setWaveform(generator, channel, [MAX_TRANSMISSION_VOLTAGE[generator]])
            except Exception as error:
                print(f"RESTORE FAILED: {generator} CH{channel}: {error}", flush=True)
        raise
    return {"data_path": str(path.resolve()), "responses": responses,
            "clipped_samples": {name: entry["clipped_samples"] for name, entry in data["channels"].items()}}


def validate_counts_waveforms(data_path=None, acquisition_seconds=20, reference_seconds=5,
                             wait_seconds=2.0, save_dir="./mems_waveform_tests", show=True,
                             save_plot=True, control_worker=None, data_worker=None):
    """Measure both waveforms simultaneously; save JSON/PNG and restore both.

    Compare TDC 1 ms bins with the mean of each ten commanded 100 us samples,
    fitting integer-ms phase on the first record and checking later records.
    This verifies 1 ms averaged optical output, not individual 100 us samples.
    Error statistics include transitions and counting noise, no dark subtraction.
    """
    import numpy as np
    from interactionfreepy import IFWorker

    for value in (acquisition_seconds, reference_seconds):
        if isinstance(value, bool) or not isinstance(value, int) or value < 1:
            raise ValueError("Acquisition and reference seconds must be positive integers")
    if not math.isfinite(wait_seconds) or wait_seconds < 0:
        raise ValueError("wait_seconds must be finite and nonnegative")
    path = Path(data_path) if data_path else Path(__file__).with_name("CountsTransmission100us.json")
    data = json.loads(path.read_text(encoding="utf-8"))
    control_worker = control_worker if control_worker is not None else IFWorker(CONTROL_ENDPOINT, timeout=60)
    data_worker = data_worker if data_worker is not None else IFWorker(DATA_BROKER, timeout=30)
    remote = control_worker.AttSim
    commands = _counts_waveform_commands(data, remote)
    directory = Path(save_dir).expanduser().resolve()
    directory.mkdir(parents=True, exist_ok=True)
    stem = directory / f"counts_waveform_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}"
    result = {"started_at": datetime.now(timezone.utc).isoformat(), "waveform_source": data,
              "calibration": remote.getAttenuationCalibration(), "frequency_hz": 1000,
              "step_ms": 1, "edge_ms": 0, "attenuation_range": [0, data["max_attenuation_db"]],
              "acquisition_seconds": acquisition_seconds, "reference_seconds": reference_seconds,
              "wait_seconds": wait_seconds, "channels": {}, "restored": {},
              "json_path": str(stem.with_suffix('.json')), "png_path": str(stem.with_suffix('.png')) if save_plot else None}

    def save():
        stem.with_suffix(".json").write_text(json.dumps(result, indent=2, allow_nan=False) + "\n", encoding="utf-8")

    def collect(label, seconds):
        time.sleep(wait_seconds)
        result[label] = _collect_waveform_blocks(data_worker, seconds)
        save()
        print(f"Counts waveform: {label}, {seconds} blocks collected", flush=True)

    try:
        for generator, channel, _ in commands:
            remote.setAttenuationWaveform(generator, channel, [0])
        collect("before", reference_seconds)
        result["load"] = load_counts_waveforms(path, control_worker)
        collect("random", acquisition_seconds)
        for generator, channel, _ in commands:
            remote.setAttenuationWaveform(generator, channel, [0])
        collect("after", reference_seconds)
        for name, source in data["channels"].items():
            expected = np.asarray(source["transmission_100us"]).reshape(1000, 10).mean(axis=1)
            entry = {"levels_db": (-10 * np.log10(expected)).tolist(),
                     "target_detector": f"ch{DETECTOR_CHANNEL[source['channel']]}",
                     **{label: result[label] for label in ("before", "random", "after")}}
            entry["analysis"] = _analyse_random_waveform(entry, 1, 0)
            result["channels"][f"{name}_{source['generator']}_ch{source['channel']}"] = entry
    except BaseException as error:
        result["error"] = repr(error)
        raise
    finally:
        failures = []
        for generator, channel, _ in commands:
            key = f"{generator}_ch{channel}"
            try:
                remote.setWaveform(generator, channel, [MAX_TRANSMISSION_VOLTAGE[generator]])
                result["restored"][key] = True
            except Exception as error:
                result["restored"][key] = repr(error)
                failures.append(key)
        result["finished_at"] = datetime.now(timezone.utc).isoformat()
        save()
        if failures:
            raise RuntimeError(f"Failed to restore channels: {failures}")
    figure = plot_random_waveform_test(result, show=False)
    figure.suptitle(f"Alice / Bob measured transmission | 100 us commands averaged into 1 ms bins\n{acquisition_seconds} cycles; integer-ms phase alignment; transitions and counting noise included")
    for axis in figure.axes[1::2]:
        axis.set_title(axis.get_title().replace("Plateau", "1 ms bin"))
        legend = axis.get_legend()
        if legend:
            legend.get_texts()[0].set_text("1 ms bin error ±1σ counting noise")
    if save_plot:
        figure.savefig(stem.with_suffix(".png"), dpi=160)
    if show:
        import matplotlib.pyplot as plt
        plt.show()
    return result, figure


class AttSimClient:
    """Convenience controls; constructing a client does not connect to devices.

    Gen1: CH1 Alice, CH2 Bob. Gen2: CH1 Alice, CH2 Bob compensation.
    Generator controls are independent: fixed()/play() leave Gen2 unchanged;
    compensate()/disable_compensation() leave Gen1 unchanged. Common external
    1PPS and aligned waveform origins are required; submission is not a test
    of synchronization or optical performance. Multi-channel writes are not
    atomic. On write failure, stop and inspect the reported partial state.

    VS Code Remote SSH: use these calls in a notebook or Interactive Window:

        sim = AttSimClient()
        sim.preview(rho=1.4)
        sim.disable_compensation()
        sim.fixed(0.163)
        sim.play()
        sim.compensate(rho=1.4)

    Only preview() is offline. All other calls above except construction
    explicitly modify hardware. Gen2 waveform arrays are never saved to disk.
    """

    def __init__(self, data_path=None, endpoint=CONTROL_ENDPOINT,
                 service=CONTROL_SERVICE, worker=None):
        self.data_path = Path(data_path) if data_path else Path(__file__).with_name("CountsTransmission100us.json")
        self.endpoint = endpoint
        self.service = service
        self._worker = worker

    def _remote(self):
        if self._worker is None:
            from interactionfreepy import IFWorker
            self._worker = IFWorker(self.endpoint, timeout=60)
        return getattr(self._worker, self.service)

    def _apply(self, commands):
        remote = self._remote()
        for generator, channel, attenuation in commands:
            remote.previewAttenuationWaveform(generator, channel, attenuation)
        responses = []
        completed = []
        for generator, channel, attenuation in commands:
            try:
                responses.append(remote.setAttenuationWaveform(generator, channel, attenuation))
            except Exception as error:
                raise RuntimeError(
                    f"Write failed for {generator} CH{channel}; its state is uncertain. "
                    f"Completed writes: {completed}. No automatic rollback was attempted."
                ) from error
            completed.append(f"{generator} CH{channel}")
        return responses

    def fixed(self, alice=0.163, bob=None):
        """Set Gen1 constant transmissions in (0, 1]; bob defaults to alice.

        These are requested transmissions, not empirically corrected values.
        Gen2 is unchanged; call disable_compensation() for fully fixed output.
        """
        bob = alice if bob is None else bob
        for value in (alice, bob):
            if isinstance(value, bool) or not math.isfinite(value) or not 0 < value <= 1:
                raise ValueError("Transmission must be finite and in (0, 1]")
        return self._apply([("gen1", 1, [-10 * math.log10(alice)]),
                            ("gen1", 2, [-10 * math.log10(bob)])])

    def play(self):
        """Play the saved, balanced Gen1 curves without changing Gen2."""
        data = json.loads(self.data_path.read_text(encoding="utf-8"))
        commands = _counts_waveform_commands(data, self._remote())
        return self._apply(commands)

    def preview(self, rho, show=True):
        """Offline only: return (in-memory curves, figure), without saving."""
        result = generate_compensation_waveforms(rho, self.data_path)
        return result, plot_compensation_waveforms(result, show=show)

    def compensate(self, rho):
        """Generate, range-check and load Gen2 compensation; Gen1 unchanged.

        Gen1 must already be playing this client's saved source curves.
        """
        result = generate_compensation_waveforms(rho, self.data_path)
        commands = [("gen2", entry["channel"], entry["attenuation_db"].tolist())
                    for entry in result["channels"].values()]
        return {"rho": result["rho"], "source_sha256": result["source_sha256"],
                "responses": self._apply(commands)}

    def disable_compensation(self):
        """Set both Gen2 channels to calibrated 0 dB; Gen1 unchanged."""
        return self._apply([("gen2", 1, [0.0]), ("gen2", 2, [0.0])])


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("generator", choices=("gen1", "gen2"))
    parser.add_argument("channel", type=int, choices=(1, 2))
    parser.add_argument("--voltage-range", nargs=2, type=float, default=(0.0, 5.0), metavar=("START", "STOP"))
    parser.add_argument("--points", type=int, default=100)
    parser.add_argument("--wait-seconds", type=float, default=3.0)
    parser.add_argument("--acquisition-seconds", type=float, default=5.0)
    parser.add_argument("--save-dir", default="./mems_calibration")
    parser.add_argument("--control-endpoint", default=CONTROL_ENDPOINT)
    parser.add_argument("--control-service", default=CONTROL_SERVICE)
    parser.add_argument("--data-broker", default=DATA_BROKER)
    parser.add_argument("--no-restore", action="store_true")
    args = parser.parse_args(argv)
    path = calibrate_transmission(
        args.generator,
        args.channel,
        voltage_range=args.voltage_range,
        points=args.points,
        wait_seconds=args.wait_seconds,
        acquisition_seconds=args.acquisition_seconds,
        save_dir=args.save_dir,
        control_endpoint=args.control_endpoint,
        control_service=args.control_service,
        data_broker=args.data_broker,
        restore=not args.no_restore,
    )
    print(f"Calibration saved to {path}")


if __name__ == "__main__":
    # main()
    # test_random_waveform(
    #     channels=(("gen1", 2),),
    #     acquisition_seconds=10,
    #     reference_seconds=1,
    #     reference_after=False,
    #     show=False,
    #     save_plot=True,
    # )

    # from interactionfreepy import IFWorker
    # worker = IFWorker("tcp://code.qpqi.group:1161", timeout=60)

    # transmission = 0.163
    # attenuation_db = -10 * math.log10(transmission)
    # # worker.AttSim.setAttenuationWaveform("gen1", 1, [attenuation_db])
    # # worker.AttSim.setAttenuationWaveform("gen1", 2, [attenuation_db])

    # load_counts_waveforms(control_worker=worker)

    sim = AttSimClient()

    # sim.fixed(0.163)
    sim.play()

    # sim.disable_compensation()
    sim.compensate(rho=2)