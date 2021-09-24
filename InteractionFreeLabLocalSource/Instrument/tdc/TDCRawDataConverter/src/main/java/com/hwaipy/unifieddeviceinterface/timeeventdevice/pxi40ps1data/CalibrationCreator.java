package com.hwaipy.unifieddeviceinterface.timeeventdevice.pxi40ps1data;

import com.hwaipy.unifieddeviceinterface.DeviceException;
import java.io.File;
import java.io.IOException;
import java.io.RandomAccessFile;
import java.nio.ByteBuffer;
import java.nio.channels.FileChannel;
import java.util.Iterator;
import java.util.TreeMap;

/**
 *
 * @author Hwaipy
 */
public class CalibrationCreator {

    private final File file;
    private boolean available = false;
    private RandomAccessFile raf;
    private FileChannel fileChannel;
    private MappingReader mappingReader;

    public CalibrationCreator(File file) throws IOException {
        this.file = file;
        if (file != null && file.exists() && file.isFile() && file.length() > 0) {
            available = true;
        }
        if (available) {
            raf = new RandomAccessFile(file, "rw");
            fileChannel = raf.getChannel();
            mappingReader = new MappingReader(fileChannel);
        }
    }

    public long[] calibrationMap(int channel) throws IOException, DeviceException {
        TreeMap<Long, Integer> map = new TreeMap<>();
        int c = 0;
        while (available && c < 1000000) {
            long[] load = loadNextFineTime();
            if (load == null) {
                break;
            }
            if (channel != load[1]) {
                continue;
            }
            long fineTime = load[0];
            if (map.containsKey(fineTime)) {
                map.put(fineTime, map.get(fineTime) + 1);
            } else {
                map.put(fineTime, 1);
            }
            c++;
        }
        long[] distribution = new long[(int) (map.lastKey() + 1)];
        Iterator<Long> iterator = map.keySet().iterator();
        while (iterator.hasNext()) {
            Long key = iterator.next();
            Integer value = map.get(key);
            distribution[(int) (long) key] = (int) value;
        }
        int sum = 0;
        for (long d : distribution) {
            sum += d;
        }
        double position = 0;
        for (int i = 0; i < distribution.length; i++) {
            double count = distribution[i];
            double value = count / sum * 6250;
            distribution[i] = (long) (position + value);
            position += value;
            System.out.println(position);
        }
        return distribution;
    }

    public long[] loadNextFineTime() throws IOException, DeviceException {
        if (!available) {
            return null;
        }
        while (true) {
            ByteBuffer unit = mappingReader.getNextUnit();
            if (unit == null) {
                return null;
            }
            boolean check = checkDataUnit(unit.array());
            if (check) {
                unit.position(0);
                return parse(unit);
            } else {
                mappingReader.rollBackUnit();
                ByteBuffer fixBuffer = mappingReader.getFixBuffer();
                if (fixBuffer == null) {
                    return null;
                }
                int offset = checkOffset(fixBuffer);
                if (offset == -1) {
                    throw new DeviceException("Fix failed.");
                }
                mappingReader.skip(offset);
            }
        }
    }

    private long[] parse(ByteBuffer unit) throws DeviceException {
        long fineTime;
        long channel = unit.get(6) & 0x0F;
        long[] b = new long[8];
        for (int i = 0; i < 8; i++) {
            b[i] = unit.get(i);
            if (b[i] < 0) {
                b[i] += 256;
            }
        }
        fineTime = ((b[3] & 0x10) << 4) | b[7];
        return new long[]{fineTime, channel};
    }

    private boolean checkDataUnit(byte[] data) {
        if (((data[3] & 0xE0) != 0x00) || ((data[6] & 0XF0) != 0x40) || (data[1] != (byte) 0xFF)) {
            System.out.println("false");
            System.out.println(data[3]);
            System.out.println(data[6]);
            System.out.println(data[1]);
            System.out.println("1" + ((data[3] & 0xEF) != 0xEF));
            System.out.println("2" + ((data[6] & 0XF0) != 0x40));
            System.out.println("3" + (data[1] != (byte) 0xFF));
            return false;
        }
        return true;
    }

    private int checkOffset(ByteBuffer map) {
        int fixPreLength = 100;
        if (map.remaining() < 817) {
            return -1;
        }
        int originPosition = map.position();
        while (map.position() - originPosition < 16) {
            byte get = map.get();
            if (get == -1) {
                int p = map.position();
                map.position(p + 2);
                byte[] data = new byte[8];
                boolean isOK = true;
                for (int i = 0; i < fixPreLength; i++) {
                    map.get(data);
                    boolean check = checkDataUnit(data);
                    if (!check) {
                        isOK = false;
                        break;
                    }
                }
                if (isOK) {
                    map.position(originPosition);
                    return p - originPosition + 2;
                } else {
                    map.position(p);
                }
            }
        }
        map.position(originPosition);
        return -1;
    }
}
