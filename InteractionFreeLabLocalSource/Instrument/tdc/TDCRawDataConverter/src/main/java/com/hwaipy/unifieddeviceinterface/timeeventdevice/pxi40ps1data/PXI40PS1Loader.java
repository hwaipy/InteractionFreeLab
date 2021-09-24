package com.hwaipy.unifieddeviceinterface.timeeventdevice.pxi40ps1data;

import com.hwaipy.unifieddeviceinterface.DeviceException;
import com.hwaipy.unifieddeviceinterface.timeeventdevice.TimeEvent;
import com.hwaipy.unifieddeviceinterface.timeeventdevice.data.TimeEventLoader;
import com.hwaipy.unifieddeviceinterface.timeeventdevice.io.TimeEventSerializer;
import com.hwaipy.unifieddeviceinterface.timeeventdevice.timeeventcontainer.TimeEventSegment;
import java.io.File;
import java.io.IOException;
import java.io.RandomAccessFile;
import java.nio.ByteBuffer;
import java.nio.channels.FileChannel;

/**
 *
 * @author Hwaipy
 */
public class PXI40PS1Loader implements TimeEventLoader {

    private static final int CHANNEL_COUNT = 16;
    private final File file;
    private boolean available = false;
    private RandomAccessFile raf;
    private FileChannel fileChannel;
    private MappingReader mappingReader;
    private final TimeCalculator tc;

    public PXI40PS1Loader(File dataFile, File fineTimeCalibratorFile) throws IOException {
        this.file = dataFile;
        if (file != null && file.exists() && file.isFile() && file.length() > 0) {
            available = true;
        }
        if (available) {
            raf = new RandomAccessFile(file, "rw");
            fileChannel = raf.getChannel();
            mappingReader = new MappingReader(fileChannel);
        }
        FineTimeCalibrator fineTimeCalibrator = new FineTimeCalibrator(fineTimeCalibratorFile, 8);
        tc = new TimeCalculator(fineTimeCalibrator);
    }

    @Override
    public int getChannelCount() {
        return CHANNEL_COUNT;
    }

    @Override
    public TimeEvent loadNext() throws IOException, DeviceException {
        if (!available) {
            return null;
        }
        while (true) {
            ByteBuffer unit = mappingReader.getNextUnit();
            if (unit == null) {
                return null;
            }
//            boolean check = checkDataUnit(unit.array());
//            if (check) {
            unit.position(0);
            return parse(unit);
//            } else {
//                mappingReader.rollBackUnit();
//                ByteBuffer fixBuffer = mappingReader.getFixBuffer();
//                if (fixBuffer == null) {
//                    return null;
//                }
//                int offset = checkOffset(fixBuffer);
//                if (offset == -1) {
//                    throw new DeviceException("Fix failed.");
//                }
//                mappingReader.skip(offset);
//            }
        }
    }

    @Override
    public void complete(TimeEventSegment segment) {
    }

    private boolean checkDataUnit(byte[] data) {
//        if (((data[3] & 0xE0) != 0x00) || ((data[6] & 0XF0) != 0x40) || (data[1] != (byte) 0xFF)) {
//            System.out.println("false");
//            System.out.println(data[3]);
//            System.out.println(data[6]);
//            System.out.println(data[1]);
//            System.out.println("1" + ((data[3] & 0xEF) != 0xEF));
//            System.out.println("2" + ((data[6] & 0XF0) != 0x40));
//            System.out.println("3" + (data[1] != (byte) 0xFF));
//            return false;
//        }
        return true;
    }

//    private int checkOffset(ByteBuffer map) {
//        int fixPreLength = 100;
//        if (map.remaining() < 817) {
//            return -1;
//        }
//        int originPosition = map.position();
//        while (map.position() - originPosition < 16) {
//            byte get = map.get();
//            if (get == -1) {
//                int p = map.position();
//                map.position(p + 2);
//                byte[] data = new byte[8];
//                boolean isOK = true;
//                for (int i = 0; i < fixPreLength; i++) {
//                    map.get(data);
//                    boolean check = checkDataUnit(data);
//                    if (!check) {
//                        isOK = false;
//                        break;
//                    }
//                }
//                if (isOK) {
//                    map.position(originPosition);
//                    return p - originPosition + 2;
//                } else {
//                    map.position(p);
//                }
//            }
//        }
//        map.position(originPosition);
//        return -1;
//    }
    private final long[] lastTime = new long[CHANNEL_COUNT];

    private TimeEvent parse(ByteBuffer unit) throws DeviceException {
        long time;
        int channel = unit.get(6) & 0x0F;
//        System.out.println(channel);
        time = tc.calculate(unit, channel);

//        if (channel != 0 && channel != 2) {
//            System.out.println(channel + "\t" + (time / 1000000000.));
//        }

        if (channel >= 0 && channel < CHANNEL_COUNT) {
            if (time < lastTime[channel]) {
//                time += 256 * 256 * 6250;
//                if (time < lastTime[channel]) {
//                System.out.println("error in parse source file: " + time + "   " + lastTime[channel] + "\t" + channel);
//                System.out.println(
//                        p(unit.get(0)) + " "
//                        + p(unit.get(7)) + " "
//                        + p(unit.get(3)) + " "
//                        + p(unit.get(2)) + " "
//                        + p(unit.get(5)) + " ");
//                System.out.println(
//                        p(unit.get(0)) + " "
//                        + p(unit.get(1)) + " "
//                        + p(unit.get(2)) + " "
//                        + p(unit.get(3)) + " "
//                        + p(unit.get(4)) + " "
//                        + p(unit.get(5)) + " "
//                        + p(unit.get(6)) + " "
//                        + p(unit.get(7)) + " ");
//                return TimeEvent.ERROR_EVENT;
//                }
            }
            lastTime[channel] = time;
            return new TimeEvent(time, channel);
        } else {
            throw new DeviceException("Channel number " + channel + " is not available.");
        }
    }

    private String p(int v) {
        if (v < 0) {
            v += 256;
        }
        return Integer.toHexString(v).toUpperCase();
    }

    @Override
    public TimeEventSerializer getSerializer() {
        return new TimeEventSerializer();
    }
}
