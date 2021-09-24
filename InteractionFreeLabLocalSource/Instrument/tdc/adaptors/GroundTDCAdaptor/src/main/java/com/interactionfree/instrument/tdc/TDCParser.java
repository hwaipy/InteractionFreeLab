package com.interactionfree.instrument.tdc;

import java.nio.ByteBuffer;
import java.util.Iterator;
import java.util.Timer;
import java.util.TimerTask;
import java.util.concurrent.BlockingQueue;
import java.util.concurrent.LinkedBlockingQueue;

/**
 * The refresh time is used to trigger write events. In some application, the
 * tdc datawriter tends to wait for enough data before write out. So the offer
 * method is invoked in a fixed frequency with arguments null to remaind the
 * adapters to write out the translated data.
 *
 * @author Hwaipy
 */
public class TDCParser {

    private final TDCDataProcessor processor;
    private final TDCDataAdapter[] adapters;
    private final BlockingQueue<Object> dataQueue = new LinkedBlockingQueue<>();
    private boolean running = true;

    public TDCParser(TDCDataProcessor processor, long flushTime, TDCDataAdapter... adapters) {
        this.processor = processor;
        this.adapters = adapters;
        Timer timer = new Timer("TDCParser refresh timer", true);
        timer.schedule(new TimerTask() {
            @Override
            public void run() {
                flush();
            }
        }, flushTime, flushTime);
        Thread processingThread = new Thread(new Runnable() {
            @Override
            public void run() {
                try {
                    while (running) {
                        processLoop();
                    }
                } catch (InterruptedException ex) {
                    ex.printStackTrace();
                    throw new RuntimeException(ex);
                }
            }
        }, "TDCParser processor");
        processingThread.start();
    }

    public TDCParser(TDCDataProcessor processor, TDCDataAdapter[] adapters) {
        this(processor, 100, adapters);
    }

    public int bufferedDataSize() {
        Iterator it = dataQueue.iterator();
        int size = 0;
        while (it.hasNext()) {
            Object ne = it.next();
            if (ne instanceof byte[]) {
                byte[] bs = (byte[]) ne;
                size += bs.length;
            }
        }
        return size;
    }

    public void offer(byte[] data) {
        dataQueue.offer(data);
    }

    public void stop() {
        running = false;
        dataQueue.offer(FLUSH_OBJECT);
    }

    private static final byte[] FLUSH_OBJECT = new byte[0];

    private void flush() {
        dataQueue.offer(FLUSH_OBJECT);
    }

    private void processLoop() throws InterruptedException {
        Object data = dataQueue.take();
        if (data == FLUSH_OBJECT) {
            shrinkQueue();
        }
        if (!(data instanceof byte[])) {
            System.out.println(data);
        }
        data = ByteBuffer.wrap((byte[]) data);
        for (TDCDataAdapter adapter : adapters) {
            data = adapter.offer(data);
        }
        processor.process(data);
    }

    private void shrinkQueue() {
        while (!dataQueue.isEmpty()) {
            Object peeked = dataQueue.peek();
            if (peeked == FLUSH_OBJECT) {
                dataQueue.poll();
            } else {
                return;
            }
        }
    }
}
