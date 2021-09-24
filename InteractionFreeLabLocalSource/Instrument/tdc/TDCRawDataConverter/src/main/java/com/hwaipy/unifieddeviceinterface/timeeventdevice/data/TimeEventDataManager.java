package com.hwaipy.unifieddeviceinterface.timeeventdevice.data;

import com.hwaipy.unifieddeviceinterface.DeviceException;
import com.hwaipy.unifieddeviceinterface.timeeventdevice.TimeEvent;
import com.hwaipy.unifieddeviceinterface.timeeventdevice.io.TimeEventSerializer;
import com.hwaipy.unifieddeviceinterface.timeeventdevice.timeeventcontainer.DefaultTimeEventSegment;
import com.hwaipy.unifieddeviceinterface.timeeventdevice.timeeventcontainer.MappingFileTimeEventList;
import com.hwaipy.unifieddeviceinterface.timeeventdevice.timeeventcontainer.TimeEventSegment;
import java.io.File;
import java.io.IOException;
import java.util.concurrent.atomic.AtomicInteger;
//import org.joda.time.DateTime;
//import org.joda.time.format.DateTimeFormat;
//import org.joda.time.format.DateTimeFormatter;

/**
 *
 * @author Hwaipy
 */
public class TimeEventDataManager {

    private static final String MappingFilesRoot = "TimeEventMappingFiles";
    private static final String suffix = "TimeEventMapping";
//    private static final DateTimeFormatter dateTimeFormatter = DateTimeFormat.forPattern("YYYY.MM.dd HH.mm.ss.SSS");
    private static final AtomicInteger indicer = new AtomicInteger();

    public static TimeEventSegment loadTimeEventSegment(TimeEventLoader loader) throws IOException, DeviceException {
        final File folder = createMappingFileFolder();
        TimeEventSerializer serializer = loader.getSerializer();
        MappingFileTimeEventList[] mappingLists = createMappingLists(folder, loader.getChannelCount());
        while (true) {
            TimeEvent timeEvent = loader.loadNext();
            if (timeEvent == TimeEvent.ERROR_EVENT) {
                continue;
            }
            if (timeEvent == null) {
                break;
            }
            mappingLists[timeEvent.getChannel()].push(serializer.serialize(timeEvent));
        }
        for (MappingFileTimeEventList list : mappingLists) {
            list.complete();
        }
        DefaultTimeEventSegment segment = new DefaultTimeEventSegment(mappingLists);
        loader.complete(segment);
        return segment;
    }

    private static MappingFileTimeEventList[] createMappingLists(File folder, int channelCount) throws IOException {
        MappingFileTimeEventList[] mappingLists = new MappingFileTimeEventList[channelCount];
        for (int i = 0; i < channelCount; i++) {
            File file = new File(folder, i + "." + suffix);
            mappingLists[i] = new MappingFileTimeEventList(file);
        }
        clearOnExit(folder);
        return mappingLists;
    }

    //TODO 文件夹名有冲突隐患
    private static File createMappingFileFolder() {
        File file = new File(MappingFilesRoot, getUniquePrefix() + "-" + indicer.getAndIncrement());
        file.mkdirs();
        return file;
    }

    private static String getUniquePrefix() {
//        DateTime time = new DateTime(System.currentTimeMillis());
//        return time.toString(dateTimeFormatter);
        return "" + System.currentTimeMillis();
    }

    private static void clearOnExit(final File folder) {
        Runtime.getRuntime().addShutdownHook(new Thread(new Runnable() {
            @Override
            public void run() {
                clearMappingFiles(folder);
            }
        }));
    }

    private static void clearMappingFiles(File folder) {
        if (folder.exists() && folder.isDirectory()) {
            for (File file : folder.listFiles()) {
                file.delete();
            }
            folder.delete();
        }
    }
}
