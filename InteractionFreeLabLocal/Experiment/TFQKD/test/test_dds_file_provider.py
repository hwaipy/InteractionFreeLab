"""Verify durable DDS command storage and inter-process file locking."""
from concurrent.futures import ThreadPoolExecutor
import contextlib
import io
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

SERVICES = Path(__file__).resolve().parents[1] / 'services'
sys.path.insert(0, str(SERVICES))
from DDS_File_Provider import DDSFileProvider


class DDSFileProviderTest(unittest.TestCase):
    def setUp(self):
        root = tempfile.TemporaryDirectory()
        self.addCleanup(root.cleanup)
        self.path = Path(root.name) / 'delay.txt'
        self.service = DDSFileProvider(self.path)
        with contextlib.redirect_stdout(io.StringIO()):
            self.service.start()

    def child(self, code, *args):
        return subprocess.Popen([sys.executable, '-c',
                                 f'import sys; sys.path.insert(0, {str(SERVICES)!r})\n' + code,
                                 str(self.path), *args], stdin=subprocess.PIPE,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

    def test_delay_units_return_format_and_frequency_restore(self):
        for delay in (-1234.5, 0, 50):
            result = self.service.correctDelay(delay)
            self.assertEqual(result['State'], 'Success')
            self.assertTrue(result['Saved'])
            self.assertEqual(result['Provider'], 'File')
            self.assertEqual(result['DelayPs'], delay)
            self.assertEqual(float(self.path.read_text()), delay / 1000)
            self.assertEqual(result['FileDelayUnit'], 'ns')
        self.assertEqual(float(self.path.read_text()), .05)
        with contextlib.redirect_stdout(io.StringIO()):
            self.service.setFrequency(11000000)
            restored = DDSFileProvider(self.path)
            restored.start()
        self.assertEqual(restored.getFrequency(), 11000000)
        self.assertEqual(self.path.read_text(), '0\n')
        self.assertEqual(self.service.frequency_path.read_text().strip(), '11000000')

    def test_invalid_values_do_not_write(self):
        for value in (None, True, '100', float('nan'), float('inf')):
            with self.assertRaises(ValueError):
                self.service.correctDelay(value)
        for value in (0, -1, 125E6):
            with self.assertRaises(ValueError):
                self.service.setFrequency(value)
        self.assertEqual(self.path.read_text(), '')

    def test_write_failure_propagates_and_releases_lock(self):
        with patch('DDS_File_Provider.os.fsync', side_effect=OSError('disk failed')):
            with self.assertRaisesRegex(OSError, 'disk failed'):
                self.service.correctDelay(10)
        self.assertEqual(self.service.getStatus()['State'], 'FileError')
        self.assertEqual(self.service.correctDelay(20)['State'], 'Success')

    def test_waits_for_other_process_to_release_lock(self):
        child = self.child('''from DDS_File_Provider import file_lock
from pathlib import Path
with file_lock(Path(sys.argv[1])):
    print('LOCKED', flush=True)
    sys.stdin.readline()
''')
        try:
            self.assertEqual(child.stdout.readline().strip(), 'LOCKED')
            with ThreadPoolExecutor(max_workers=1) as pool:
                write = pool.submit(self.service.correctDelay, 99)
                try:
                    time.sleep(.05)
                    self.assertFalse(write.done())
                    self.assertEqual(self.path.read_text(), '')
                finally:
                    child.stdin.write('\n')
                    child.stdin.flush()
                self.assertEqual(write.result(timeout=5)['State'], 'Success')
            out, err = child.communicate(timeout=5)
            self.assertEqual(child.returncode, 0, err)
        finally:
            if child.poll() is None:
                child.kill()
                child.communicate()

    def test_concurrent_process_writes_keep_one_complete_value(self):
        code = '''from DDS_File_Provider import DDSFileProvider
service = DDSFileProvider(sys.argv[1])
for i in range(20):
    service.correctDelay(int(sys.argv[2]) * 100 + i)
'''
        children = [self.child(code, str(index)) for index in range(4)]
        try:
            for child in children:
                out, err = child.communicate(timeout=10)
                self.assertEqual(child.returncode, 0, err)
        finally:
            for child in children:
                if child.poll() is None:
                    child.kill()
                    child.communicate()
        rows = [float(line) for line in self.path.read_text().splitlines()]
        self.assertEqual(len(rows), 1)
        self.assertIn(rows[0],
                      {(index * 100 + i) / 1000 for index in range(4) for i in range(20)})


if __name__ == '__main__':
    unittest.main()
