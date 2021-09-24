package com.hwaipy.unifieddeviceinterface.timeeventdevice.pxi40ps1data;

import com.hwaipy.unifieddeviceinterface.DeviceException;
import java.nio.ByteBuffer;

/**
 *
 * @author Hwaipy
 */
class TimeCalculator {

  private static final long COARSE_TIME_LIMIT = 1 << 28;
  private long carry = 0;
  private long lastCoarseTime = -1;
  private final FineTimeCalibrator calibrator;
  private long count = 0;
  private long[] counts = new long[100];

  public TimeCalculator(FineTimeCalibrator calibrator) {
    this.calibrator = calibrator;
  }

  long calculate(ByteBuffer buffer, int channel) throws DeviceException {
    count++;
    counts[channel]++;
    long[] b = new long[8];
    for (int i = 0; i < 8; i++) {
      b[i] = buffer.get(i);
      if (b[i] < 0) {
        b[i] += 256;
      }
    }
    long fineTime = ((b[3] & 0x10) << 4) | b[7];
    long coarseTime = (b[4]) | (b[5] << 8)
            | (b[2] << 16) | ((b[3] & 0x0F) << 24);

    long currentCarry = carry;
    if (coarseTime < lastCoarseTime && (lastCoarseTime > COARSE_TIME_LIMIT / 5 * 4) && (coarseTime < COARSE_TIME_LIMIT / 5)) {
      carry++;
      currentCarry = carry;
      lastCoarseTime = coarseTime;
    } else if (coarseTime > lastCoarseTime && (coarseTime > COARSE_TIME_LIMIT / 5 * 4) && (lastCoarseTime < COARSE_TIME_LIMIT / 5)) {
      currentCarry = carry - 1;
    } else {
      lastCoarseTime = coarseTime;
    }

//    lastCoarseTime = coarseTime;

    long time = -getExactTime(fineTime, channel)
            + ((coarseTime + (currentCarry << 28)) * 6250);
    return time;
  }

  private long getExactTime(long exactTime, int channel) {
    return calibrator.calibration(channel, (int) exactTime);
  }
}
