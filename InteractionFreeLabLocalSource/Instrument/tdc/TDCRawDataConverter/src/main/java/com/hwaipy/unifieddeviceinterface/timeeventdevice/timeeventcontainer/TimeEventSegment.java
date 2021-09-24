package com.hwaipy.unifieddeviceinterface.timeeventdevice.timeeventcontainer;

/**
 *
 * @author Hwaipy
 */
public interface TimeEventSegment {

    public int getEventCount();

    public int getChannelCount();

    public int getEventCount(int channel);

    public TimeEventList getEventList(int channel);
}
