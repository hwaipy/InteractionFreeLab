from Instrument.FrequencyCounter.KeySight_53230A import KeySight_53230A
from Instrument.FrequencyGenerator.RIGOL_DSG800 import RIGOL_DSG800
import time

if __name__ == '__main__':
    print('start locking')

    fg = RIGOL_DSG800('TCPIP::192.168.25.148::INSTR')
    fc = KeySight_53230A('TCPIP::192.168.25.154::INSTR')

    targetFrequency = 60e6

    freqShift = fg.getFrequencySetpoint()

    while True:
        freq = fc.measureFrequency()
        diff = freq - targetFrequency
        freqShift -= diff
        fg.setFrequency(freqShift)   
        time.sleep(1)