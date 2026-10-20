"""Read-oriented controller for a Keysight/Agilent M8190A AWG.

The default transport is the instrument's SCPI socket and needs no third-party
packages.  A PyVISA transport is also available when ``pyvisa`` is installed.
"""

from __future__ import annotations

from array import array
import math
import socket
import sys
from typing import Any, Callable


def _text(value: str) -> str:
    return value.strip().strip('"')


def _integer(value: str) -> int:
    return int(value.strip(), 0)


def _number(value: str) -> float:
    return float(value.strip())


def _boolean(value: str) -> bool:
    normalized = value.strip().upper()
    if normalized in {"1", "ON", "TRUE"}:
        return True
    if normalized in {"0", "OFF", "FALSE"}:
        return False
    raise ValueError(f"not a SCPI boolean: {value!r}")


def _carrier_frequency(value: str) -> dict[str, float]:
    integral_text, fractional_text = value.strip().split(",", maxsplit=1)
    integral = float(integral_text)
    fractional = float(fractional_text)
    return {
        "integral_hz": integral,
        "fractional_hz": fractional,
        "total_hz": integral + fractional,
    }


class SocketTransport:
    """Line-oriented SCPI transport over a raw TCP socket."""

    def __init__(self, host: str, port: int = 5025, timeout: float = 5.0):
        self.host = host
        self.port = port
        self.timeout = timeout
        self._socket: socket.socket | None = None
        self._stream = None

    def open(self) -> None:
        self._socket = socket.create_connection(
            (self.host, self.port), timeout=self.timeout
        )
        self._socket.settimeout(self.timeout)
        self._stream = self._socket.makefile("rwb", buffering=0)

    def close(self) -> None:
        if self._stream is not None:
            self._stream.close()
            self._stream = None
        if self._socket is not None:
            self._socket.close()
            self._socket = None

    def query(self, command: str) -> str:
        if self._stream is None:
            raise RuntimeError("transport is not open")
        self._stream.write(command.rstrip().encode("ascii") + b"\n")
        response = self._stream.readline()
        if not response:
            raise ConnectionError("instrument closed the connection")
        return response.decode("ascii", errors="replace").strip()

    def write(self, command: str) -> None:
        if self._stream is None:
            raise RuntimeError("transport is not open")
        self._stream.write(command.rstrip().encode("ascii") + b"\n")

    def write_binary_block(self, command: str, payload: bytes) -> None:
        if self._stream is None:
            raise RuntimeError("transport is not open")
        length = str(len(payload)).encode("ascii")
        block = (
            command.encode("ascii")
            + b"#"
            + str(len(length)).encode("ascii")
            + length
            + payload
            + b"\n"
        )
        self._stream.write(block)


class VisaTransport:
    """PyVISA transport; works with Keysight VISA, NI-VISA, or pyvisa-py."""

    def __init__(self, resource: str, timeout: float = 5.0):
        self.resource = resource
        self.timeout = timeout
        self._resource_manager = None
        self._instrument = None

    def open(self) -> None:
        try:
            import pyvisa
        except ImportError as exc:
            raise RuntimeError(
                "PyVISA is not installed; install requirements.txt in the venv"
            ) from exc
        self._resource_manager = pyvisa.ResourceManager()
        self._instrument = self._resource_manager.open_resource(
            self.resource,
            timeout=int(self.timeout * 1000),
            read_termination="\n",
            write_termination="\n",
        )

    def close(self) -> None:
        if self._instrument is not None:
            self._instrument.close()
            self._instrument = None
        if self._resource_manager is not None:
            self._resource_manager.close()
            self._resource_manager = None

    def query(self, command: str) -> str:
        if self._instrument is None:
            raise RuntimeError("transport is not open")
        return str(self._instrument.query(command)).strip()

    def write(self, command: str) -> None:
        if self._instrument is None:
            raise RuntimeError("transport is not open")
        self._instrument.write(command)

    def write_binary_block(self, command: str, payload: bytes) -> None:
        if self._instrument is None:
            raise RuntimeError("transport is not open")
        length = str(len(payload)).encode("ascii")
        block = (
            command.encode("ascii")
            + b"#"
            + str(len(length)).encode("ascii")
            + length
            + payload
            + b"\n"
        )
        self._instrument.write_raw(block)


class M8190A:
    """High-level, read-oriented M8190A interface."""

    def __init__(self, transport: SocketTransport | VisaTransport):
        self.transport = transport
        self._waveform_segments: dict[str, tuple[int, int]] = {}

    def __enter__(self) -> "M8190A":
        self.open()
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def open(self) -> None:
        self.transport.open()

    def close(self) -> None:
        self.transport.close()

    def query(self, command: str) -> str:
        """Send any SCPI query and return its unparsed response."""
        return self.transport.query(command)

    def write(self, command: str) -> None:
        """Send a SCPI command that does not return a response."""
        self.transport.write(command)

    def write_binary_block(self, command: str, payload: bytes) -> None:
        self.transport.write_binary_block(command, payload)

    def _query(
        self, command: str, parser: Callable[[str], Any] = _text
    ) -> Any:
        return parser(self.query(command))

    @staticmethod
    def _channel(channel: int) -> int:
        if channel not in (1, 2):
            raise ValueError("channel must be 1 or 2")
        return channel

    def _collect(
        self, commands: dict[str, tuple[str, Callable[[str], Any]]]
    ) -> dict[str, Any]:
        """Run independent queries, retaining per-field failures."""
        result: dict[str, Any] = {}
        for name, (command, parser) in commands.items():
            try:
                result[name] = self._query(command, parser)
            except Exception as exc:
                result[name] = {"query_error": f"{type(exc).__name__}: {exc}"}
        return result

    def get_identity(self) -> dict[str, Any]:
        return self._collect(
            {
                "idn": ("*IDN?", _text),
                "options": ("*OPT?", _text),
                "scpi_version": (":SYST:VERS?", _text),
                "slot_number": (":INST:SLOT?", _integer),
                "module_configuration": (":INST:MMOD:CONF?", _text),
                "module_mode": (":INST:MMOD:MODE?", _text),
            }
        )

    def get_communication(self) -> dict[str, Any]:
        return self._collect(
            {
                "socket_port": (":SYST:COMM:SOCK?", _integer),
                "telnet_port": (":SYST:COMM:TELN?", _integer),
                "hislip_number": (":SYST:COMM:HISL?", _integer),
                "vxi11_instrument_number": (":SYST:COMM:INST?", _integer),
                "tcpip_control_port": (":SYST:COMM:TCP:CONT?", _integer),
            }
        )

    def get_clock(self) -> dict[str, Any]:
        result = self._collect(
            {
                "sample_rate_configured_hz": (":FREQ:RAST?", _number),
                "sample_rate_realized_hz": (":FREQ:RAST:REAL?", _number),
                "external_sample_rate_hz": (":FREQ:RAST:EXT?", _number),
                "low_phase_noise_enabled": (":FREQ:RAST:LPN:ENAB?", _boolean),
                "low_phase_noise_active": (":FREQ:RAST:LPN:ACT?", _boolean),
                "reference_source": (":ROSC:SOUR?", _text),
                "reference_frequency_hz": (":ROSC:FREQ?", _number),
            }
        )
        result["channels"] = {
            str(ch): self._collect(
                {
                    "sample_rate_source": (f":FREQ:RAST:SOUR{ch}?", _text),
                    "sample_clock_output_source": (
                        f":OUTP{ch}:SCLK:SOUR?",
                        _text,
                    ),
                }
            )
            for ch in (1, 2)
        }
        return result

    def get_sample_rate_limits(self) -> dict[str, Any]:
        """Return sample-rate limits inferred from installed hardware options.

        This unit operates in direct AWG mode. Option 14B supports up to
        8 GSa/s, while option 12G supports up to 12 GSa/s.
        """
        options = {
            item.strip().upper()
            for item in self.query("*OPT?").split(",")
            if item.strip()
        }
        if "12G" in options:
            maximum_hz = 12e9
        elif "14B" in options:
            maximum_hz = 8e9
        else:
            raise RuntimeError(
                "cannot infer maximum sample rate: neither 12G nor 14B "
                "was reported by *OPT?"
            )
        return {
            "minimum_hz": 125e6,
            "maximum_hz": maximum_hz,
            "installed_options": sorted(options),
            "mode_limits": {
                "14_bit_direct": {
                    "minimum_hz": 125e6,
                    "maximum_hz": 8e9,
                    "available": "14B" in options,
                },
                "12_bit_direct": {
                    "minimum_hz": 125e6,
                    "maximum_hz": 12e9,
                    "available": "12G" in options,
                },
                "interpolated_duc": {
                    "minimum_hz": 1e9,
                    "maximum_hz": 7.2e9,
                    "available": "DUC" in options,
                },
            },
        }

    def set_sample_rate(
        self,
        rate_hz: float,
        *,
        verify: bool = True,
    ) -> dict[str, Any]:
        """Set the internal sample rate and optionally read it back.

        The requested value is checked against the limits implied by *OPT?.
        This changes instrument timing immediately; output state is not altered.
        """
        requested_hz = float(rate_hz)
        if not math.isfinite(requested_hz):
            raise ValueError("sample rate must be finite")
        limits = self.get_sample_rate_limits()
        minimum_hz = float(limits["minimum_hz"])
        maximum_hz = float(limits["maximum_hz"])
        if not minimum_hz <= requested_hz <= maximum_hz:
            raise ValueError(
                f"sample rate {requested_hz:g} Hz is outside the installed "
                f"option range {minimum_hz:g}..{maximum_hz:g} Hz"
            )

        previous_hz = self._query(":FREQ:RAST?", _number)
        self.write(f":FREQ:RAST {requested_hz:.15g}")
        result: dict[str, Any] = {
            "requested_hz": requested_hz,
            "previous_hz": previous_hz,
            "limits": limits,
        }
        if verify:
            self._query("*OPC?", _integer)
            result["configured_hz"] = self._query(":FREQ:RAST?", _number)
            result["realized_hz"] = self._query(
                ":FREQ:RAST:REAL?", _number
            )
        return result

    def set_external_sample_clock(
        self,
        rate_hz: float,
        *,
        verify: bool = True,
    ) -> dict[str, Any]:
        """Use the signal at SAMPLE CLK IN as both channels' sample clock."""
        requested_hz = float(rate_hz)
        if not math.isfinite(requested_hz):
            raise ValueError("external sample clock rate must be finite")
        limits = self.get_sample_rate_limits()
        minimum_hz = float(limits["minimum_hz"])
        maximum_hz = float(limits["maximum_hz"])
        if not minimum_hz <= requested_hz <= maximum_hz:
            raise ValueError(
                f"external sample clock {requested_hz:g} Hz is outside the "
                f"installed option range {minimum_hz:g}..{maximum_hz:g} Hz"
            )

        self.write(f":FREQ:RAST:EXT {requested_hz:.15g}")
        self.write(":FREQ:RAST:SOUR1 EXT")
        self.write(":FREQ:RAST:SOUR2 EXT")

        result: dict[str, Any] = {
            "requested_hz": requested_hz,
            "limits": limits,
        }
        if verify:
            result["configured_hz"] = self._query(
                ":FREQ:RAST:EXT?", _number
            )
            result["channel_1_source"] = self.query(
                ":FREQ:RAST:SOUR1?"
            )
            result["channel_2_source"] = self.query(
                ":FREQ:RAST:SOUR2?"
            )
        return result

    def set_internal_sample_clock(
        self,
        rate_hz: float,
        *,
        verify: bool = True,
    ) -> dict[str, Any]:
        """Use the internal reference and internal sample-clock synthesizer."""
        self.write(":ROSC:SOUR INT")
        self.write(":FREQ:RAST:SOUR1 INT")
        self.write(":FREQ:RAST:SOUR2 INT")
        result = self.set_sample_rate(rate_hz, verify=False)
        if verify:
            result["reference_source"] = self.query(":ROSC:SOUR?")
            result["configured_hz"] = self._query(
                ":FREQ:RAST?", _number
            )
            result["channel_1_source"] = self.query(
                ":FREQ:RAST:SOUR1?"
            )
            result["channel_2_source"] = self.query(
                ":FREQ:RAST:SOUR2?"
            )
        return result

    def set_external_reference_clock(
        self,
        reference_hz: float,
        sample_rate_hz: float,
        *,
        verify: bool = True,
    ) -> dict[str, Any]:
        """Lock the internal sample-clock synthesizer to REF CLK IN."""
        requested_reference_hz = float(reference_hz)
        if (
            not math.isfinite(requested_reference_hz)
            or not 1e6 <= requested_reference_hz <= 200e6
        ):
            raise ValueError(
                "external reference frequency must be 1 MHz..200 MHz"
            )

        self.write(f":ROSC:FREQ {requested_reference_hz:.15g}")
        self.write(":ROSC:SOUR EXT")
        self.write(":FREQ:RAST:SOUR1 INT")
        self.write(":FREQ:RAST:SOUR2 INT")
        result = self.set_sample_rate(sample_rate_hz, verify=False)
        result["requested_reference_hz"] = requested_reference_hz
        if verify:
            result["reference_source"] = self.query(":ROSC:SOUR?")
            result["configured_reference_hz"] = self._query(
                ":ROSC:FREQ?", _number
            )
            result["configured_hz"] = self._query(
                ":FREQ:RAST?", _number
            )
            result["channel_1_source"] = self.query(
                ":FREQ:RAST:SOUR1?"
            )
            result["channel_2_source"] = self.query(
                ":FREQ:RAST:SOUR2?"
            )
        return result

    def configure_start_mode(self, mode: str) -> dict[str, Any]:
        """Configure immediate continuous or trigger-then-continuous start."""
        normalized = mode.strip().upper()
        if normalized in {"AUTO", "AUTOMATIC"}:
            normalized = "AUTO"
        elif normalized in {
            "TRIGGER",
            "TRIGGERED",
            "TRIGGERED_CONTINUOUS",
        }:
            normalized = "TRIGGERED_CONTINUOUS"
        else:
            raise ValueError(
                "start mode must be AUTO or TRIGGERED_CONTINUOUS"
            )

        if normalized == "TRIGGERED_CONTINUOUS":
            self.write(":ARM:TRIG:SOUR TRIG")

        for ch in (1, 2):
            self.write(f":INIT:CONT{ch}:ENAB SELF")
            self.write(f":INIT:GATE{ch} OFF")
            if normalized == "AUTO":
                self.write(f":INIT:CONT{ch} ON")
                self.write(f":TRAC{ch}:ADV AUTO")
            else:
                self.write(f":INIT:CONT{ch} OFF")
                self.write(f":TRAC{ch}:ADV COND")

        return {
            "mode": normalized,
            "trigger_source": (
                "TRIGGER IN"
                if normalized == "TRIGGERED_CONTINUOUS"
                else None
            ),
        }

    def stop(self, channel: int | None = None) -> None:
        """Stop signal generation on one channel or on both channels."""
        channels = (self._channel(channel),) if channel is not None else (1, 2)
        for ch in channels:
            self.write(f":ABOR{ch}")

    def start(self, channel: int | None = None) -> None:
        """Start signal generation on one channel or on both channels."""
        channels = (self._channel(channel),) if channel is not None else (1, 2)
        for ch in channels:
            self.write(f":INIT:IMM{ch}")

    def clear_all(self, channel: int | None = None) -> None:
        """Delete all waveform segments on one channel or on both channels."""
        channels = (self._channel(channel),) if channel is not None else (1, 2)
        for ch in channels:
            self.write(f":TRAC{ch}:DEL:ALL")
        if channel is None:
            self._waveform_segments.clear()
        else:
            self._waveform_segments = {
                name: item
                for name, item in self._waveform_segments.items()
                if item[0] != channel
            }

    def set_output(self, channel: int, enabled: bool) -> None:
        """Enable or disable the normal output of a channel."""
        ch = self._channel(channel)
        self.write(f":OUTP{ch} {'ON' if enabled else 'OFF'}")

    def set_output_route(self, channel: int, route: str) -> None:
        """Select the Direct DAC, amplified DC, or amplified AC output."""
        ch = self._channel(channel)
        normalized = route.strip().upper()
        if normalized == "DIRECT":
            normalized = "DAC"
        if normalized not in {"DAC", "DC", "AC"}:
            raise ValueError("route must be DAC/DIRECT, DC, or AC")
        self.write(f":OUTP{ch}:ROUT {normalized}")

    def write_waveform(
        self,
        channel: int,
        waveform: Any,
        *,
        segment_id: int = 1,
        name: str | None = None,
    ) -> dict[str, Any]:
        """Define, upload, and select a normalized waveform.

        Values must be in [-1, 1]. The method packs them into the M8190A
        12-bit speed or 14-bit precision direct-mode word format.
        """
        ch = self._channel(channel)
        if segment_id < 1:
            raise ValueError("segment_id must be positive")

        width = self.query(f":TRAC{ch}:DWID?").strip().upper()
        if width == "WSP":
            minimum_length, granularity = 320, 64
            negative_scale, positive_scale, shift = 2048, 2047, 4
        elif width == "WPR":
            minimum_length, granularity = 240, 48
            negative_scale, positive_scale, shift = 8192, 8191, 2
        else:
            raise RuntimeError(
                f"waveform upload supports direct modes WSP/WPR, got {width!r}"
            )

        packed = array("h")
        for value in waveform:
            normalized = float(value)
            if not math.isfinite(normalized):
                raise ValueError("waveform contains a non-finite value")
            if normalized < -1.0 or normalized > 1.0:
                raise ValueError("waveform values must be within [-1, 1]")
            scale = positive_scale if normalized >= 0 else negative_scale
            packed.append(int(round(normalized * scale)) << shift)

        length = len(packed)
        if length == 0:
            raise ValueError("waveform must not be empty")
        if length < minimum_length or length % granularity:
            raise ValueError(
                f"{width} waveform length must be >= {minimum_length} and "
                f"a multiple of {granularity}; got {length}"
            )

        self.write(f":TRAC{ch}:DEF {segment_id},{length}")
        self.write(":FORM:BORD SWAP")
        if sys.byteorder != "little":
            packed.byteswap()
        self.write_binary_block(
            f":TRAC{ch}:DATA {segment_id},0,",
            packed.tobytes(),
        )
        self.write(f":TRAC{ch}:SEL {segment_id}")
        self._query("*OPC?", _integer)

        waveform_name = name or f"CH{ch}"
        self._waveform_segments[waveform_name] = (ch, segment_id)
        return {
            "channel": ch,
            "segment_id": segment_id,
            "name": waveform_name,
            "samples": length,
            "data_width": width,
        }

    def assign_output(self, channel: int, waveform_name: str) -> None:
        """Assign a previously uploaded named waveform to an output channel."""
        ch = self._channel(channel)
        try:
            waveform_channel, segment_id = self._waveform_segments[waveform_name]
        except KeyError as exc:
            raise KeyError(f"unknown waveform {waveform_name!r}") from exc
        if waveform_channel != ch:
            raise ValueError(
                f"{waveform_name!r} was uploaded to channel {waveform_channel}"
            )
        self.write(f":TRAC{ch}:SEL {segment_id}")

    # Compatibility names used by the existing Encoder program.
    def _stop(self) -> None:
        self.stop()

    def _start(self) -> None:
        self.start()

    def clearAll(self) -> None:
        self.clear_all()

    def writeWaveform(self, name: str, waveform: Any) -> dict[str, Any]:
        normalized_name = name.strip().upper()
        if normalized_name not in {"CH1", "CH2"}:
            raise ValueError("waveform name must be CH1 or CH2")
        channel = int(normalized_name[-1])
        return self.write_waveform(
            channel,
            waveform,
            segment_id=1,
            name=normalized_name,
        )

    def assignOutput(self, channel: int, waveform_name: str) -> None:
        self.assign_output(channel, waveform_name)

    def _setOutput(self, channel: int, enabled: bool) -> None:
        self.set_output(channel, enabled)

    def get_trigger(self) -> dict[str, Any]:
        result = self._collect(
            {
                "dynamic_port_width": (":ARM:DYNPORT:WIDT?", _text),
                "event_impedance": (":ARM:EVEN:IMP?", _text),
                "event_level_v": (":ARM:EVEN:LEV?", _number),
                "event_slope": (":ARM:EVEN:SLOP?", _text),
                "trigger_frequency_hz": (":ARM:TRIG:FREQ?", _number),
                "trigger_impedance": (":ARM:TRIG:IMP?", _text),
                "trigger_level_v": (":ARM:TRIG:LEV?", _number),
                "trigger_slope": (":ARM:TRIG:SLOP?", _text),
                "trigger_source": (":ARM:TRIG:SOUR?", _text),
                "advance_source": (":TRIG:SOUR:ADV?", _text),
                "enable_source": (":TRIG:SOUR:ENAB?", _text),
            }
        )
        result["channels"] = {}
        for ch in (1, 2):
            result["channels"][str(ch)] = self._collect(
                {
                    "coarse_delay_s": (f":ARM:CDEL{ch}?", _number),
                    "delay_s": (f":ARM:DEL{ch}?", _number),
                    "reduced_noise_floor": (f":ARM:RNO{ch}?", _boolean),
                    "continuous_enabled": (
                        f":INIT:CONT{ch}:ENAB?",
                        _text,
                    ),
                    "continuous_state": (f":INIT:CONT{ch}?", _boolean),
                    "gate_state": (f":INIT:GATE{ch}?", _boolean),
                    "advance_hw_disabled": (
                        f":TRIG:ADV{ch}:HWD?",
                        _boolean,
                    ),
                    "begin_gate_state": (
                        f":TRIG:BEG{ch}:GATE?",
                        _boolean,
                    ),
                    "begin_hw_disabled": (
                        f":TRIG:BEG{ch}:HWD?",
                        _boolean,
                    ),
                    "enable_hw_disabled": (
                        f":TRIG:ENAB{ch}:HWD?",
                        _boolean,
                    ),
                }
            )
        return result

    def get_output(self, channel: int) -> dict[str, Any]:
        ch = self._channel(channel)
        result = self._collect(
            {
                "enabled": (f":OUTP{ch}?", _boolean),
                "complement_enabled": (f":OUTP{ch}:COMP?", _boolean),
                "differential_offset_v": (f":OUTP{ch}:DIOF?", _number),
                "route": (f":OUTP{ch}:ROUT?", _text),
                "function_mode": (f":FUNC{ch}:MODE?", _text),
                "voltage_amplitude_vpp": (f":VOLT{ch}?", _number),
                "voltage_high_v": (f":VOLT{ch}:HIGH?", _number),
                "voltage_low_v": (f":VOLT{ch}:LOW?", _number),
                "voltage_offset_v": (f":VOLT{ch}:OFFS?", _number),
                "ac_format": (f":AC{ch}:FORM?", _text),
                "ac_amplitude_vpp": (f":AC{ch}:VOLT?", _number),
                "dc_format": (f":DC{ch}:FORM?", _text),
                "dc_amplitude_vpp": (f":DC{ch}:VOLT?", _number),
                "dc_high_v": (f":DC{ch}:VOLT:HIGH?", _number),
                "dc_low_v": (f":DC{ch}:VOLT:LOW?", _number),
                "dc_offset_v": (f":DC{ch}:VOLT:OFFS?", _number),
                "dc_termination_ohm": (f":DC{ch}:VOLT:TERM?", _number),
                "dac_format": (f":DAC{ch}:FORM?", _text),
                "dac_amplitude_vpp": (f":DAC{ch}:VOLT?", _number),
                "dac_high_v": (f":DAC{ch}:VOLT:HIGH?", _number),
                "dac_low_v": (f":DAC{ch}:VOLT:LOW?", _number),
                "dac_offset_v": (f":DAC{ch}:VOLT:OFFS?", _number),
                "carrier_frequency": (
                    f":CARR{ch}:FREQ?",
                    _carrier_frequency,
                ),
                "carrier_frequency_fractional": (
                    f":CARR{ch}:FREQ:FRAC?",
                    _number,
                ),
                "carrier_frequency_integral": (
                    f":CARR{ch}:FREQ:INT?",
                    _integer,
                ),
                "carrier_phase_offset_deg": (f":CARR{ch}:POFF?", _number),
                "carrier_scale": (f":CARR{ch}:SCAL?", _number),
            }
        )
        result["markers"] = self._collect(
            {
                "sample_amplitude_vpp": (
                    f":MARK{ch}:SAMP:VOLT:AMPL?",
                    _number,
                ),
                "sample_high_v": (f":MARK{ch}:SAMP:VOLT:HIGH?", _number),
                "sample_low_v": (f":MARK{ch}:SAMP:VOLT:LOW?", _number),
                "sample_offset_v": (f":MARK{ch}:SAMP:VOLT:OFFS?", _number),
                "sync_amplitude_vpp": (
                    f":MARK{ch}:SYNC:VOLT:AMPL?",
                    _number,
                ),
                "sync_high_v": (f":MARK{ch}:SYNC:VOLT:HIGH?", _number),
                "sync_low_v": (f":MARK{ch}:SYNC:VOLT:LOW?", _number),
                "sync_offset_v": (f":MARK{ch}:SYNC:VOLT:OFFS?", _number),
            }
        )
        return result

    def get_waveform(self, channel: int) -> dict[str, Any]:
        ch = self._channel(channel)
        return {
            "trace": self._collect(
                {
                    "catalog": (f":TRAC{ch}:CAT?", _text),
                    "free_bytes": (f":TRAC{ch}:FREE?", _text),
                    "selected_segment": (f":TRAC{ch}:SEL?", _integer),
                    "selected_count": (f":TRAC{ch}:COUN?", _integer),
                    "data_width": (f":TRAC{ch}:DWID?", _text),
                    "marker_enabled": (f":TRAC{ch}:MARK?", _boolean),
                    "advance_mode": (f":TRAC{ch}:ADV?", _text),
                }
            ),
            "sequence": self._collect(
                {
                    "catalog": (f":SEQ{ch}:CAT?", _text),
                    "free": (f":SEQ{ch}:FREE?", _text),
                }
            ),
            "scenario": self._collect(
                {
                    "dynamic_enabled": (f":STAB{ch}:DYN?", _boolean),
                    "dynamic_hw_disabled": (
                        f":STAB{ch}:DYN:HWD?",
                        _boolean,
                    ),
                    "dynamic_selection": (f":STAB{ch}:DYN:SEL?", _integer),
                    "scenario_advance": (f":STAB{ch}:SCEN:ADV?", _text),
                    "scenario_count": (f":STAB{ch}:SCEN:COUN?", _integer),
                    "selected_scenario": (f":STAB{ch}:SCEN:SEL?", _integer),
                    "selected_sequence": (f":STAB{ch}:SEQ:SEL?", _integer),
                    "sequence_state": (f":STAB{ch}:SEQ:STAT?", _text),
                    "streaming": (f":STAB{ch}:STR?", _boolean),
                }
            ),
        }

    def get_status(self) -> dict[str, Any]:
        """Read non-destructive condition and enable registers."""
        return self._collect(
            {
                "status_byte": ("*STB?", _integer),
                "event_status_enable": ("*ESE?", _integer),
                "service_request_enable": ("*SRE?", _integer),
                "operation_condition": (":STAT:OPER:COND?", _integer),
                "operation_enable": (":STAT:OPER:ENAB?", _integer),
                "operation_run_condition": (
                    ":STAT:OPER:RUN:COND?",
                    _integer,
                ),
                "operation_run_enable": (":STAT:OPER:RUN:ENAB?", _integer),
                "questionable_condition": (":STAT:QUES:COND?", _integer),
                "questionable_enable": (":STAT:QUES:ENAB?", _integer),
                "connection_condition": (
                    ":STAT:QUES:CONN:COND?",
                    _integer,
                ),
                "connection_enable": (":STAT:QUES:CONN:ENAB?", _integer),
                "frequency_condition": (
                    ":STAT:QUES:FREQ:COND?",
                    _integer,
                ),
                "frequency_enable": (":STAT:QUES:FREQ:ENAB?", _integer),
                "sequence_condition": (
                    ":STAT:QUES:SEQ:COND?",
                    _integer,
                ),
                "sequence_enable": (":STAT:QUES:SEQ:ENAB?", _integer),
                "voltage_condition": (
                    ":STAT:QUES:VOLT:COND?",
                    _integer,
                ),
                "voltage_enable": (":STAT:QUES:VOLT:ENAB?", _integer),
                "error_count": (":SYST:ERR:COUN?", _integer),
            }
        )

    def read_event_registers(self) -> dict[str, Any]:
        """Read-and-clear event registers. This intentionally changes them."""
        return self._collect(
            {
                "standard_event": ("*ESR?", _integer),
                "operation_event": (":STAT:OPER:EVEN?", _integer),
                "operation_run_event": (":STAT:OPER:RUN:EVEN?", _integer),
                "questionable_event": (":STAT:QUES:EVEN?", _integer),
                "connection_event": (":STAT:QUES:CONN:EVEN?", _integer),
                "frequency_event": (":STAT:QUES:FREQ:EVEN?", _integer),
                "sequence_event": (":STAT:QUES:SEQ:EVEN?", _integer),
                "voltage_event": (":STAT:QUES:VOLT:EVEN?", _integer),
            }
        )

    def get_error_count(self) -> int:
        return self._query(":SYST:ERR:COUN?", _integer)

    def read_next_error(self) -> dict[str, Any]:
        """Pop one entry from the instrument error queue."""
        raw = self.query(":SYST:ERR:NEXT?")
        code_text, separator, message = raw.partition(",")
        return {
            "code": int(code_text.strip()),
            "message": message.strip().strip('"') if separator else "",
            "raw": raw,
        }

    def drain_error_queue(self, limit: int = 100) -> list[dict[str, Any]]:
        """Pop queued errors until code 0 is returned or *limit* is reached."""
        errors: list[dict[str, Any]] = []
        for _ in range(limit):
            item = self.read_next_error()
            if item["code"] == 0:
                break
            errors.append(item)
        return errors

    def get_system(self) -> dict[str, Any]:
        return self._collect(
            {
                "memory_catalog": (":MMEM:CAT?", _text),
                "current_directory": (":MMEM:CDIR?", _text),
                "licenses": (":SYST:LIC:LIST?", _text),
                "extended_licenses": (":SYST:LIC:EXT:LIST?", _text),
            }
        )

    def get_snapshot(
        self,
        *,
        include_waveforms: bool = True,
        drain_errors: bool = False,
        read_events: bool = False,
    ) -> dict[str, Any]:
        """Return a structured state snapshot.

        Error and event registers are not consumed unless explicitly requested.
        """
        snapshot: dict[str, Any] = {
            "identity": self.get_identity(),
            "communication": self.get_communication(),
            "clock": self.get_clock(),
            "trigger": self.get_trigger(),
            "outputs": {
                str(ch): self.get_output(ch)
                for ch in (1, 2)
            },
            "status": self.get_status(),
            "system": self.get_system(),
        }
        if include_waveforms:
            snapshot["waveforms"] = {
                str(ch): self.get_waveform(ch)
                for ch in (1, 2)
            }
        if read_events:
            snapshot["events_read_and_cleared"] = self.read_event_registers()
        if drain_errors:
            snapshot["errors_drained"] = self.drain_error_queue()
        return snapshot
