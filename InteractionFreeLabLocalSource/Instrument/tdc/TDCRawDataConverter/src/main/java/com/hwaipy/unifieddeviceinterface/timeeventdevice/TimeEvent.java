package com.hwaipy.unifieddeviceinterface.timeeventdevice;

/**
 *
 * @author Hwaipy
 */
public class TimeEvent {

    public static final TimeEvent ERROR_EVENT = new TimeEvent(-1, -1);
    private final long time;
    private final int channel;

    public TimeEvent(long time, int channel) {
        this.time = time;
        this.channel = channel;
    }

    public int getChannel() {
        return channel;
    }

    public long getTime() {
        return time;
    }

    public double getTimeInSecond() {
        return time / 1000000000000.;
    }

    @Override
    public String toString() {
        return "TimeEvent(Channel: " + channel + ", Time: " + time + ")";
    }
}
