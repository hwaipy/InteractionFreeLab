package com.hwaipy.unifieddeviceinterface.timeeventdevice.timeeventcontainer;

/**
 *
 * @author Hwaipy
 */
public class DefaultTimeEventSegment implements TimeEventSegment {

    protected final TimeEventList[] timeEventLists;

    public DefaultTimeEventSegment(TimeEventList[] timeEventLists) {
        this.timeEventLists = timeEventLists;
    }

    @Override
    public int getEventCount() {
        int eventCount = 0;
        for (TimeEventList timeEventList : timeEventLists) {
            eventCount += timeEventList.size();
        }
        return eventCount;
    }

    @Override
    public int getChannelCount() {
        return timeEventLists.length;
    }

    @Override
    public int getEventCount(int channel) {
        return timeEventLists[channel].size();
    }

    @Override
    public TimeEventList getEventList(int channel) {
        return timeEventLists[channel];
    }
}
