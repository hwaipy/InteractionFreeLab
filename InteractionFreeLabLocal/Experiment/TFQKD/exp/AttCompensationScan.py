"""Explicitly started, repeating compensation scan; never runs on import.

Run: python AttCompensationScan.py run
Stop: Ctrl+C, or python AttCompensationScan.py stop /path/to/run_directory

The TDC must already be continuously recording to Storage. This program marks
experimental windows; it does not start a TDC acquisition or download raw data.
Gen2 arrays remain in memory. Gen1 source data is frozen at startup. Do not
change generator settings from another process during the scan.
"""

import argparse
import csv
import fcntl
import hashlib
import json
import math
import os
import signal
import tempfile
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from AttSim import (
    CONTROL_ENDPOINT, CONTROL_SERVICE, DATA_BROKER, TDC_COLLECTION,
    _as_utc_datetime, _counts_waveform_commands, generate_compensation_waveforms,
)


THRESHOLDS = (None, 1, 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7, 1.8, 2, 3, 4, 5)
BEIJING = ZoneInfo("Asia/Shanghai")
INTERVAL_FIELDS = (
    "round", "index", "rho", "status", "start_utc", "end_utc",
    "start_beijing", "end_beijing", "elapsed_seconds", "error",
)


def _timestamp():
    now = datetime.now(timezone.utc)
    return {"utc": now.isoformat(), "beijing": now.astimezone(BEIJING).isoformat()}


class ScanStopped(Exception):
    pass


def request_stop(run_directory):
    """Signal a cooperative stop; the running scanner performs cleanup."""
    directory = Path(run_directory).expanduser().resolve()
    if not (directory / "manifest.json").is_file():
        raise ValueError("Not a scan run directory: manifest.json is missing")
    (directory / "STOP").touch()
    return directory / "STOP"


def run_scan(thresholds=THRESHOLDS, acquisition_seconds=600, settle_seconds=15,
             data_path=None, output_dir=None, rounds=None,
             endpoint=CONTROL_ENDPOINT, service=CONTROL_SERVICE,
             data_broker=DATA_BROKER, health_interval=10, max_data_age=30,
             control_worker=None, data_worker=None, stop_event=None):
    """Loop indefinitely by default; explicitly calling this operates hardware.

    Every stage reloads all four channels, then settles, then marks a complete
    acquisition interval. Failed/interrupted windows are not marked complete.
    STOP/SIGINT/SIGTERM requests interrupt waiting within one second; an active
    remote call can take up to its timeout. Cleanup attempts BOTH Gen2 channels
    at 0 dB, leaving Gen1 as last loaded. No automatic retry or resume.
    The advisory lock excludes other scanners on this host, not other hosts.
    """
    thresholds = tuple(thresholds)
    if not thresholds or any(value is not None and
                             (isinstance(value, bool) or not math.isfinite(value) or value < 1)
                             for value in thresholds):
        raise ValueError("Thresholds must be None (off) or finite numbers >= 1")
    for value in (acquisition_seconds, health_interval, max_data_age):
        if not math.isfinite(value) or value <= 0:
            raise ValueError("Acquisition/health durations must be finite and positive")
    if not math.isfinite(settle_seconds) or settle_seconds < 0:
        raise ValueError("settle_seconds must be finite and nonnegative")
    if rounds is not None and (isinstance(rounds, bool) or not isinstance(rounds, int) or rounds < 1):
        raise ValueError("rounds must be a positive integer or None")
    source_path = Path(data_path) if data_path else Path(__file__).with_name("CountsTransmission100us.json")
    source_bytes = source_path.read_bytes()
    source_hash = hashlib.sha256(source_bytes).hexdigest()
    source = json.loads(source_bytes)
    plans = []
    for rho in thresholds:
        if rho is None:
            plans.append([("gen2", 1, [0.0]), ("gen2", 2, [0.0])])
        else:
            generated = generate_compensation_waveforms(rho, source_path)
            if generated["source_sha256"] != source_hash:
                raise ValueError("Source file changed while preparing the scan")
            plans.append([("gen2", entry["channel"], entry["attenuation_db"].tolist())
                          for entry in generated["channels"].values()])

    lock_key = hashlib.sha256(f"{endpoint}/{service}".encode()).hexdigest()[:20]
    lock_path = Path(tempfile.gettempdir()) / f"mems_scan_{lock_key}.lock"
    lock = lock_path.open("a+")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        lock.close()
        raise RuntimeError("Another compensation scanner is running on this host")
    directory = None
    previous_handlers = {}
    stopped = stop_event if stop_event is not None else threading.Event()
    hardware_attempted = False
    stage = None
    remote = None
    cleanup_errors = {}
    failure = None

    try:
        root = Path(output_dir) if output_dir else Path(__file__).with_name("mems_compensation_scans")
        directory = root.expanduser().resolve() / datetime.now(BEIJING).strftime("%Y%m%d_%H%M%S_%f")
        directory.mkdir(parents=True, exist_ok=False)
        manifest = {"created": _timestamp(), "pid": os.getpid(), "thresholds": thresholds,
                    "acquisition_seconds": acquisition_seconds, "settle_seconds": settle_seconds,
                    "rounds": rounds, "endpoint": endpoint, "service": service,
                    "data_broker": data_broker, "collection": TDC_COLLECTION,
                    "source_path": str(source_path.resolve()), "source_sha256": source_hash,
                    "health_interval": health_interval, "max_data_age": max_data_age,
                    "window_semantics": "[start, end); wall-clock condition windows, not hardware timestamps",
                    "storage_boundary_caution": "FetchTime is receipt time; exclude overlapping/uncertain boundary blocks",
                    "state": "preparing"}

        def checkpoint():
            temporary = directory / "status.tmp"
            with temporary.open("w", encoding="utf-8") as output:
                json.dump({"updated": _timestamp(), "state": manifest["state"], "stage": stage}, output, indent=2)
                output.flush()
                os.fsync(output.fileno())
            temporary.replace(directory / "status.json")

        def event(kind, **fields):
            with (directory / "events.jsonl").open("a", encoding="utf-8") as output:
                output.write(json.dumps({"event": kind, "time": _timestamp(), **fields}) + "\n")
                output.flush()
                os.fsync(output.fileno())

        def save_manifest():
            temporary = directory / "manifest.tmp"
            temporary.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
            temporary.replace(directory / "manifest.json")

        def check_stop():
            if stopped.is_set() or (directory / "STOP").exists():
                raise ScanStopped("Stop requested")

        def health():
            check_stop()
            entries = data_worker.Storage.latest(TDC_COLLECTION, by="FetchTime", filter={"FetchTime": 1}, length=1)
            if not entries:
                raise RuntimeError("No TDC records found")
            entry = entries if isinstance(entries, dict) else entries[0]
            if not isinstance(entry, dict) or entry.get("FetchTime") is None:
                raise RuntimeError("Latest TDC record has no FetchTime")
            fetched = _as_utc_datetime(entry["FetchTime"])
            age = (datetime.now(timezone.utc) - fetched).total_seconds()
            if age > max_data_age or age < -5:
                raise RuntimeError(f"TDC FetchTime age {age:.1f}s: stale data or clock mismatch")
            event("data_health", latest_fetch_time=fetched.isoformat(), age_seconds=age)

        def wait_until(deadline):
            next_health = time.monotonic()
            while True:
                check_stop()
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return
                if time.monotonic() >= next_health:
                    health()
                    next_health = time.monotonic() + health_interval
                    continue
                stopped.wait(min(1, remaining, max(0, next_health-time.monotonic())))

        def interrupt(signum, frame):
            stopped.set()

        save_manifest()
        checkpoint()
        print(f"Scan directory: {directory}", flush=True)
        if threading.current_thread() is threading.main_thread():
            for signum in (signal.SIGINT, signal.SIGTERM):
                previous_handlers[signum] = signal.signal(signum, interrupt)
        check_stop()
        from interactionfreepy import IFWorker
        control_worker = control_worker if control_worker is not None else IFWorker(endpoint, timeout=60)
        data_worker = data_worker if data_worker is not None else IFWorker(data_broker, timeout=10)
        remote = getattr(control_worker, service)
        calibration = remote.getAttenuationCalibration()
        manifest["calibration"] = calibration
        gen1_commands = _counts_waveform_commands(source, remote)
        for commands in plans:
            for generator, channel, attenuation in commands:
                check_stop()
                remote.previewAttenuationWaveform(generator, channel, attenuation)
        save_manifest()
        event("preflight_complete")
        health()
        round_index = 0
        while rounds is None or round_index < rounds:
            round_index += 1
            for index, (rho, gen2_commands) in enumerate(zip(thresholds, plans), 1):
                check_stop()
                stage = {"round": round_index, "index": index, "rho": rho, "status": "loading"}
                manifest["state"] = "running"
                checkpoint()
                event("stage_start", **stage)
                try:
                    if remote.getAttenuationCalibration()["sha256"] != calibration["sha256"]:
                        raise RuntimeError("Device calibration changed; scan stopped")
                    health()
                    for generator, channel, attenuation in gen1_commands + gen2_commands:
                        check_stop()
                        hardware_attempted = True
                        response = remote.setAttenuationWaveform(generator, channel, attenuation)
                        event("channel_loaded", generator=generator, channel=channel, response=response)
                    stage["loaded_at"] = _timestamp()
                    stage["status"] = "settling"
                    checkpoint()
                    wait_until(time.monotonic() + settle_seconds)
                    health()
                    check_stop()
                    start = _timestamp()
                    started = time.monotonic()
                    stage.update(status="acquiring", start_utc=start["utc"], start_beijing=start["beijing"])
                    checkpoint()
                    event("acquisition_start", **stage)
                    print(f"Round {round_index}, {index}/{len(thresholds)}, rho={rho}: {start['beijing']}", flush=True)
                    try:
                        wait_until(started + acquisition_seconds)
                    finally:
                        end = _timestamp()
                        stage.update(end_utc=end["utc"], end_beijing=end["beijing"],
                                     elapsed_seconds=time.monotonic()-started)
                    health()
                    stage["status"] = "complete"
                except BaseException as error:
                    stage["status"] = "interrupted" if isinstance(error, (ScanStopped, KeyboardInterrupt)) else "failed"
                    stage["error"] = repr(error)
                    raise
                finally:
                    event("stage_end", **stage)
                    interval_path = directory / "intervals.csv"
                    header = not interval_path.exists()
                    with interval_path.open("a", newline="", encoding="utf-8") as output:
                        writer = csv.DictWriter(output, fieldnames=INTERVAL_FIELDS, extrasaction="ignore")
                        if header:
                            writer.writeheader()
                        writer.writerow(stage)
                        output.flush()
                        os.fsync(output.fileno())
                    checkpoint()
            event("round_complete", round=round_index)
        manifest["state"] = "completed"
    except (ScanStopped, KeyboardInterrupt):
        manifest["state"] = "stopped"
    except BaseException as error:
        failure = error
        if directory is not None and "manifest" in locals():
            manifest["state"] = "failed"
            manifest["error"] = repr(error)
    finally:
        try:
            if hardware_attempted and remote is not None:
                for channel in (1, 2):
                    try:
                        remote.setAttenuationWaveform("gen2", channel, [0.0])
                    except Exception as error:
                        cleanup_errors[f"gen2_ch{channel}"] = repr(error)
            if directory is not None and "manifest" in locals():
                manifest["finished"] = _timestamp()
                manifest["cleanup"] = {"attempted": hardware_attempted,
                                       "policy": "Gen2 both 0 dB; Gen1 left unchanged",
                                       "errors": cleanup_errors}
                if cleanup_errors:
                    manifest["state"] = "cleanup_failed"
                save_manifest()
                event("scan_end", state=manifest["state"], cleanup=manifest["cleanup"])
                checkpoint()
        finally:
            for signum, handler in previous_handlers.items():
                signal.signal(signum, handler)
            lock.close()
    if failure is not None:
        raise failure
    if cleanup_errors:
        raise RuntimeError(f"Could not disable compensation: {cleanup_errors}")
    return directory


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    run = subparsers.add_parser("run", help="Start the hardware scan; infinite rounds by default")
    run.add_argument("--rounds", type=int, default=None)
    run.add_argument("--data-path")
    run.add_argument("--output-dir")
    stop = subparsers.add_parser("stop", help="Request stop of an existing run")
    stop.add_argument("run_directory")
    args = parser.parse_args(argv)
    if args.command == "stop":
        print(request_stop(args.run_directory))
    else:
        print(run_scan(data_path=args.data_path, output_dir=args.output_dir, rounds=args.rounds))


if __name__ == "__main__":
    # main()
    run_scan(data_path="CountsTransmission100us.json", output_dir="mems_compensation_scans", rounds=None)
