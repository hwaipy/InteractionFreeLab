package com.hwaipy.unifieddeviceinterface.timeeventdevice.timeeventcontainer;

import com.hwaipy.unifieddeviceinterface.timeeventdevice.TimeEvent;

/**
 *
 * @author Hwaipy
 */
public interface TimeEventList extends Iterable<TimeEvent> {

    public int size();

    public TimeEvent get(int index);

    public void set(TimeEvent event, int index);
}