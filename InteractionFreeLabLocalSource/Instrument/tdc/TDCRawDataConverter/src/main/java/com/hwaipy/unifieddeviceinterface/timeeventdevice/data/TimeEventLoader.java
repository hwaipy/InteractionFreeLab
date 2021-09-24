package com.hwaipy.unifieddeviceinterface.timeeventdevice.data;

import com.hwaipy.unifieddeviceinterface.DeviceException;
import com.hwaipy.unifieddeviceinterface.timeeventdevice.TimeEvent;
import com.hwaipy.unifieddeviceinterface.timeeventdevice.io.TimeEventSerializer;
import com.hwaipy.unifieddeviceinterface.timeeventdevice.timeeventcontainer.TimeEventSegment;
import java.io.IOException;

/**
 *
 * @author Hwaipy
 */
public interface TimeEventLoader {

    public int getChannelCount();

    public TimeEvent loadNext() throws IOException, DeviceException;

    public void complete(TimeEventSegment segment);

    public TimeEventSerializer getSerializer();
}
