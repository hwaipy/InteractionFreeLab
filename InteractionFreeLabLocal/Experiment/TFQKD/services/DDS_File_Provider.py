"""DDS-compatible IFWorker service that saves commands to a plain text file (latest delay in ns; IFWorker input remains ps)."""
import errno
import math
import os
import time
from contextlib import contextmanager
from pathlib import Path


@contextmanager
def file_lock(path):
    """Lock byte zero of delay.txt itself, matching the Windows DDS reader.

    Always read/write through the yielded handle while locked. Windows forbids
    accessing its locked byte range via another handle, even in this process.
    """
    with Path(path).open('a+', encoding='utf-8', newline='\n') as lock:
        if os.name == 'nt':
            import msvcrt
            lock.seek(0)
            while True:
                try:
                    msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
                    break
                except OSError as exc:
                    if exc.errno not in (errno.EACCES, errno.EAGAIN, errno.EDEADLK):
                        raise
                    time.sleep(0.01)
        else:
            import fcntl
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        try:
            yield lock
        finally:
            if os.name == 'nt':
                lock.seek(0)
                msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(lock.fileno(), fcntl.LOCK_UN)


def finite_number(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError('Expected a finite number')


def valid_frequency(value):
    finite_number(value)
    if not 125000000 / 2 ** 48 <= value < 125000000:
        raise ValueError('Frequency must be between the DDS tuning resolution and 125 MHz')


class DDSFileProvider:
    def __init__(self, data_file, frequency=10E6, frequency_file=None):
        valid_frequency(frequency)
        self.path = Path(data_file).resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.frequency_path = (self.path.with_name('f2.txt') if frequency_file is None
                               else Path(frequency_file).resolve())
        self.frequency = frequency
        self._ready = False
        self._status = {'State': 'AwaitingStartup', 'LastError': None}

    def start(self):
        if self._ready:
            return self.getStatus()
        with file_lock(self.path):
            if self.frequency_path.exists():
                frequency = float(self.frequency_path.read_text(encoding='utf-8').strip())
                valid_frequency(frequency)
                self.frequency = frequency
            else:
                self._save_frequency(self.frequency)
        self._ready = True
        self._status = {'State': 'Ready', 'LastError': None}
        print(f'DDS file provider: {self.path}, frequency={self.frequency:.12g} Hz', flush=True)
        return self.getStatus()

    def getStatus(self):
        return dict(self._status, FrequencyHz=self.frequency, Ready=self._ready,
                    Provider='File', FilePath=str(self.path), FileDelayUnit='ns')

    def getFrequency(self):
        return self.frequency

    def _save_frequency(self, frequency):
        # Caller holds delay.txt's lock, also used by the reader while reading f2.txt.
        with self.frequency_path.open('w', encoding='utf-8') as stream:
            stream.write(str(frequency) + '\n')
            stream.flush()
            os.fsync(stream.fileno())

    def _write(self, delay_ns, frequency=None):
        try:
            with file_lock(self.path) as stream:
                if frequency is not None:
                    self._save_frequency(frequency)
                # No truncation until after acquiring the lock; use the same handle.
                stream.seek(0)
                stream.truncate()
                stream.write(str(delay_ns) + '\n')
                stream.flush()
                os.fsync(stream.fileno())
        except Exception as exc:
            self._status = {'State': 'FileError', 'LastError': str(exc)}
            raise
        self._status = {'State': 'Success', 'LastError': None, 'Saved': True,
                        'FileDelayNs': delay_ns}

    def correctDelay(self, delayPs):
        """IFWorker takes ps; the DDS reader's changePosition takes ns."""
        finite_number(delayPs)
        self._write(delayPs / 1000)
        self._status['DelayPs'] = delayPs
        return self.getStatus()

    def setFrequency(self, frequencyHz):
        valid_frequency(frequencyHz)
        old_frequency = self.frequency
        # A zero-delay command makes the reader actually apply the new frequency.
        self._write(0, frequency=frequencyHz)
        self.frequency = frequencyHz
        print(f'DDS file frequency: {old_frequency:.12g} -> {frequencyHz:.12g} Hz; saved', flush=True)
        return self.getStatus()


def main():
    # All deployment settings are configured here, matching the DDS service.
    broker = 'tcp://tf.qpqi.group:1161'
    service_name = 'DDSClock'
    frequency = 10E6  # Default when no command file exists; Hz.
    data_file = Path(__file__).resolve().with_name('delay.txt')
    frequency_file = data_file.with_name('f2.txt')
    registration_timeout = 5

    service = DDSFileProvider(data_file, frequency, frequency_file)
    service.start()
    from interactionfreepy import IFWorker, IFLoop
    worker = IFWorker(broker, service_name, service, timeout=registration_timeout)
    print(f'{service_name} registered at {broker}; commands saved to {service.path}', flush=True)
    try:
        IFLoop.join()
    except KeyboardInterrupt:
        print('DDS file provider stopped.', flush=True)
    finally:
        worker.close()


if __name__ == '__main__':
    main()
