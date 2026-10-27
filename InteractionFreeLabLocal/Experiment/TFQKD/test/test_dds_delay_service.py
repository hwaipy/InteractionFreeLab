"""Exercise DDS correction math and exception retries without hardware."""
import time
import inspect
import ast
import types
import hashlib
import contextlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

SERVICES = Path(__file__).resolve().parents[1] / 'services'
sys.path.insert(0, str(SERVICES))
# Load the real script but expose its main-block definitions without launching it.
# The unavailable SDK is stubbed; original hardware functions run against FakeDDS.
script = SERVICES / 'dds20261023.py'
tree = ast.parse(script.read_text())
main_guard = tree.body[-1]
assert isinstance(main_guard, ast.If)
assert isinstance(main_guard.body[-1], ast.Expr)  # main() starts the real service.
tree.body[-1:] = main_guard.body[:-1]
ast.fix_missing_locations(tree)
dds = types.ModuleType('dds_main_test')
dds.__file__ = str(script)
sys.modules[dds.__name__] = dds
sdk_stubs = {
    'ezq_driver.protocol.cmu_protocol': types.SimpleNamespace(CMUProtocol=object),
    'ezq_driver.driver': types.SimpleNamespace(EzqDevice=object),
    'ezq_driver.utils': types.SimpleNamespace(bytes_to_int=lambda value: int.from_bytes(value)),
}
previous_sdk_modules = {name: sys.modules.get(name) for name in sdk_stubs}
try:
  sys.modules.update(sdk_stubs)
  exec(compile(tree, str(script), 'exec'), dds.__dict__)
finally:
  for name, previous in previous_sdk_modules.items():
    if previous is None:
      sys.modules.pop(name, None)
    else:
      sys.modules[name] = previous
DDSDelayService, correction_plan = dds.DDSDelayService, dds.correction_plan
driver = dds



class FakeDDS:
  def __init__(self, parameter_failures=0, trigger_failures=0):
    self.parameter_failures = parameter_failures
    self.trigger_failures = trigger_failures
    self.registers = {}
    self.trigger_attempts = 0
    self.successes = []

  def __getitem__(self, key):
    if key == (23, 'CPU.FIX_DATE'):
      return b'\x00' * 4
    return self.registers[key]

  def __setitem__(self, key, value):
    if key[2] == 0x94 << 2 and self.parameter_failures:
      self.parameter_failures -= 1
      raise IOError('parameter write failed')
    if key[2] == 0xAC << 2:
      self.trigger_attempts += 1
      if self.trigger_failures:
        self.trigger_failures -= 1
        raise IOError('trigger failed')
      self.successes.append(dict(self.registers))
    self.registers[key] = value


class DDSCorrectionPlanTest(unittest.TestCase):
  def test_units_sign_and_duration(self):
    for delay in (1000, -1000, 50, -50):
      with self.subTest(delay=delay):
        plan = correction_plan(delay, 10E6)
        self.assertEqual(plan['DurationNs'], 10000000)
        self.assertAlmostEqual(plan['TemporaryFrequencyHz'], 10E6 + delay / 1000)
        self.assertAlmostEqual((plan['TemporaryFrequencyHz'] / plan['FrequencyHz'] - 1) *
                               plan['DurationNs'] * 1000, delay, delta=.001)
    reversed_plan = correction_plan(1000, 10E6, -1)
    self.assertLess(reversed_plan['TemporaryFrequencyHz'], 10E6)

  def test_invalid_input_does_not_enter_retry_loop(self):
    for value in (None, True, '1000', float('nan'), float('inf')):
      with self.subTest(value=value), self.assertRaises(ValueError):
        correction_plan(value, 10E6)
    for frequency in (0, 125E6):
      with self.assertRaises(ValueError):
        DDSDelayService(frequency=frequency)


class DDSDelayServiceTest(unittest.TestCase):
  def setUp(self):
    connection = patch.object(dds, 'connect_board')
    self.board_connection = connection.start()
    self.addCleanup(connection.stop)

  def test_everything_before_main_is_preserved_byte_for_byte(self):
    prefix = script.read_bytes().split(b"if __name__ == '__main__':", 1)[0]
    digest = hashlib.sha256(prefix).hexdigest()
    self.assertEqual(digest, '6e169f756659bdc1cd7f73427d13e8e27a8214673387d782472af849a57c33ab')

  def test_service_calls_original_change_function_and_leaves_internal_retries_to_driver(self):
    device = FakeDDS()
    self.board_connection.return_value = device
    service = self.make_service(device)
    device.trigger_failures = 1
    with patch.object(driver, 'changePosition', wraps=driver.changePosition) as change:
      result = service.correctDelay(1000)
    change.assert_called_once_with(1.0, 10E6)
    self.assertEqual(result['State'], 'Success')
    self.assertNotIn('Attempts', result)
    self.assertEqual(device.trigger_attempts, 2)
    self.assert_command(device.successes[-1], 10000001.0, 10E6, 10000000)

  def test_change_position_uses_signed_ns_and_current_service_board(self):
    device = FakeDDS()
    service = self.make_service(device)
    service.direction = -1
    driver.cmu = FakeDDS()  # A stale global must not receive this service's correction.
    with patch.object(driver, 'changePosition', wraps=driver.changePosition) as change:
      result = service.correctDelay(1000)
    change.assert_called_once_with(-1.0, 10E6)
    self.assertIs(driver.cmu, device)
    self.assertEqual(result['DurationNs'], 10000000)
    self.assert_command(device.successes[-1], 9999999.0, 10E6, 10000000)

  def test_startup_initializes_frequency_and_enables_output_before_command(self):
    class RecordingDDS(FakeDDS):
      def __init__(self):
        super().__init__()
        self.calls = []

      def __setitem__(self, key, value):
        self.calls.append((key[2], value))
        super().__setitem__(key, value)

    device = RecordingDDS()
    self.board_connection.return_value = device
    with patch.object(driver, 'version_fpga'):
      service = DDSDelayService(
                                settle_time=0)
      result = service.start()
      self.assertTrue(result['Ready'])
      self.assertNotIn('Attempts', result)
      enabled = device.calls.index((0x3C << 2, 1))
      first_command = next(i for i, (address, _) in enumerate(device.calls) if address == 0x94 << 2)
      self.assertLess(enabled, first_command)
      # These control registers must never be cleared during startup or correction.
      forbidden = {address << 2 for address in (0x5C, 0x60, 0x64, 0x54, 0x20)}
      self.assertFalse(any(address in forbidden for address, _ in device.calls))
      self.assertFalse(any(address == 0x3C << 2 and value == 0 for address, value in device.calls))
      device.calls.clear()
      service.correctDelay(1000)
      self.assertFalse(any(address in forbidden for address, _ in device.calls))
      self.assertFalse(any(address == 0x3C << 2 for address, _ in device.calls))

  def assert_command(self, registers, f1, f2, duration_ns):
    for low, high, expected in ((0x94, 0x98, f1), (0x9C, 0xA0, f2)):
      word = registers[23, 0x050000, low << 2] | (registers[23, 0x050000, high << 2] << 32)
      self.assertAlmostEqual(word * 125000000 / 2 ** 48, expected, delta=1e-6)
    ticks = registers[23, 0x050000, 0xA4 << 2] | (registers[23, 0x050000, 0xA8 << 2] << 32)
    self.assertEqual(ticks * 8, duration_ns)

  def make_service(self, device):
    self.board_connection.return_value = device
    parameter_failures, trigger_failures = device.parameter_failures, device.trigger_failures
    device.parameter_failures = device.trigger_failures = 0
    service = DDSDelayService(
                              retry_interval=.001, settle_time=0)
    service.start()
    device.parameter_failures, device.trigger_failures = parameter_failures, trigger_failures
    device.trigger_attempts = 0
    device.successes.clear()
    return service

  def test_parameter_and_trigger_failures_are_retried(self):
    device = FakeDDS(parameter_failures=3)
    self.board_connection.return_value = device
    service = self.make_service(device)
    result = service.correctDelay(1000)
    self.assertEqual(result['State'], 'Success')
    self.assertNotIn('Attempts', result)
    self.assertIsNone(result['LastError'])
    self.assertEqual(device.trigger_attempts, 1)
    self.assertEqual(len(device.successes), 1)
    self.assert_command(device.successes[0], 10000001.0, 10E6, 10000000)

  def test_startup_connection_failure_is_retried(self):
    device = FakeDDS()
    self.board_connection.return_value = device
    attempts = []
    def connect(ip):
      attempts.append(ip)
      if len(attempts) < 3:
        raise OSError('board unavailable')
      return device
    self.board_connection.side_effect = connect
    service = DDSDelayService(retry_interval=.001,
                              settle_time=0)
    result = service.start()
    self.assertNotIn('Attempts', result)
    self.assertTrue(result['Ready'])
    self.assertEqual(len(attempts), 3)
    self.assertEqual(service.correctDelay(-1000)['State'], 'Success')

  def test_calls_are_synchronous_and_wait_for_retry_and_settling(self):
    for name in ('start', 'correctDelay', 'setFrequency'):
      self.assertFalse(inspect.iscoroutinefunction(getattr(DDSDelayService, name)))
    service = self.make_service(FakeDDS(parameter_failures=2))
    service.settle_time = .02
    started = time.monotonic()
    result = service.correctDelay(1000)
    self.assertGreaterEqual(time.monotonic() - started, .022)
    self.assertIsInstance(result, dict)
    self.assertEqual(result['State'], 'Success')
    self.assertNotIn('Attempts', result)

  def test_zero_delay_does_not_touch_hardware_after_startup(self):
    device = FakeDDS()
    self.board_connection.return_value = device
    service = self.make_service(device)
    result = service.correctDelay(0)
    self.assertEqual(result['State'], 'Success')
    self.assertNotIn('Attempts', result)
    self.assertEqual(device.trigger_attempts, 0)

  def test_start_synchronizes_frequency_once(self):
    device = FakeDDS()
    self.board_connection.return_value = device
    service = DDSDelayService(
                              settle_time=0)
    self.assertFalse(service.getStatus()['Ready'])
    self.assertTrue(service.start()['Ready'])
    self.assert_command(device.successes[-1], 10E6, 10E6, 10000000)
    before = device.trigger_attempts
    service.start()
    self.assertEqual(device.trigger_attempts, before)

  def test_frequency_update_retries_persists_and_survives_restart(self):
    device = FakeDDS(parameter_failures=1, trigger_failures=1)
    self.board_connection.return_value = device
    with tempfile.TemporaryDirectory() as root:
      path = Path(root) / 'frequency.json'
      output = io.StringIO()
      with contextlib.redirect_stdout(output):
        service = DDSDelayService(frequency_file=path,
                                  retry_interval=.001, settle_time=0)
        service.start()
        device.parameter_failures, device.trigger_failures = 2, 0
        device.successes.clear()
        result = service.setFrequency(20E6)
        reloaded = DDSDelayService(frequency=10E6, frequency_file=path,
                                   settle_time=0)
        reloaded.start()
      self.assertNotIn('Attempts', result)
      self.assertEqual(result['State'], 'Success')
      self.assertEqual(service.getFrequency(), 20E6)
      self.assertEqual(reloaded.getFrequency(), 20E6)
      self.assertEqual(json.loads(path.read_text())['FrequencyHz'], 20E6)
      self.assertIn('10000000 -> 20000000 Hz', output.getvalue())
      self.assertIn(f'source={path}', output.getvalue())
      self.assertEqual(list(Path(root).glob('*.tmp')), [])
      self.assert_command(device.successes[0], 20E6, 20E6, 10000000)
      correction = reloaded.correctDelay(1000)
      self.assertEqual(correction['FrequencyHz'], 20E6)

  def test_persistence_failure_is_reported_and_can_be_retried(self):
    device = FakeDDS()
    self.board_connection.return_value = device
    with tempfile.TemporaryDirectory() as root:
      path = Path(root) / 'frequency.json'
      service = DDSDelayService(frequency_file=path,
                                settle_time=0)
      service.start()
      service.setFrequency(11E6)
      with patch.object(service, '_save_frequency', side_effect=OSError('disk full')):
        with self.assertRaisesRegex(RuntimeError, 'persistence failed'):
          service.setFrequency(12E6)
      self.assertEqual(service.getFrequency(), 12E6)
      self.assertEqual(service.getStatus()['State'], 'PersistenceError')
      self.assertEqual(json.loads(path.read_text())['FrequencyHz'], 11E6)
      service.setFrequency(12E6)
      self.assertEqual(json.loads(path.read_text())['FrequencyHz'], 12E6)

  def test_invalid_frequency_and_wrong_board_settings_are_rejected(self):
    with tempfile.TemporaryDirectory() as root:
      path = Path(root) / 'frequency.json'
      service = DDSDelayService(frequency_file=path)
      for value in (True, '1000', 0, -1, 125E6, float('nan'), float('inf')):
        with self.subTest(value=value), self.assertRaises(ValueError):
          service.setFrequency(value)
      self.assertFalse(path.exists())
      path.write_text(json.dumps({'BoardIP': 'other-board', 'FrequencyHz': 20E6}))
      with self.assertRaisesRegex(ValueError, 'board IP'):
        DDSDelayService(frequency_file=path)


if __name__ == '__main__':
  unittest.main()
