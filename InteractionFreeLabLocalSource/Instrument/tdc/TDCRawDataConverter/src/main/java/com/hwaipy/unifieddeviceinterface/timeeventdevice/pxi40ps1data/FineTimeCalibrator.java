package com.hwaipy.unifieddeviceinterface.timeeventdevice.pxi40ps1data;

import java.io.BufferedReader;
import java.io.File;
import java.io.FileInputStream;
import java.io.FileNotFoundException;
import java.io.IOException;
import java.io.InputStreamReader;

/**
 *
 * @author Hwaipy
 */
class FineTimeCalibrator {

    private final boolean enabled;
    private long[][] mapping;

    public FineTimeCalibrator(File file, int channelCount) throws FileNotFoundException, IOException {
        if (file == null) {
            enabled = false;
        } else {
            enabled = true;
            BufferedReader reader = new BufferedReader(new InputStreamReader(new FileInputStream(file)));
            mapping = new long[channelCount][0];
            for (int channel = 0; channel < channelCount; channel++) {
                String line = reader.readLine();
                String[] splits = line.split(";");
                mapping[channel] = new long[splits.length - 1];
                for (int i = 1; i < splits.length; i++) {
                    String valueString = splits[i];
                    double valueDouble = Double.parseDouble(valueString);
                    mapping[channel][i - 1] = (long) valueDouble;
                }
            }
        }
    }

    public long calibration(int channel, int fineTime) {
        if (!enabled) {
            if (fineTime >= 273) {
                return 6250;
            } else {
                return (long) (6250. / 273 * fineTime);
            }
        }
        long[] m = mapping[channel];
        if (fineTime < m.length) {
            return m[fineTime];
        } else {
            return 6250;
        }
    }
}
