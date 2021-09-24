package com.hwaipy.unifieddeviceinterface.timeeventdevice.timeeventcontainer;

import com.hwaipy.unifieddeviceinterface.timeeventdevice.TimeEvent;
import com.hwaipy.unifieddeviceinterface.timeeventdevice.io.TimeEventSerializer;
import java.io.File;
import java.io.IOException;
import java.io.RandomAccessFile;
import java.nio.ByteBuffer;
import java.nio.MappedByteBuffer;
import java.nio.channels.FileChannel;
import java.util.Iterator;
import java.util.LinkedList;
import java.util.concurrent.BlockingQueue;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.LinkedBlockingQueue;
import java.util.concurrent.TimeUnit;

/**
 *
 * @author Hwaipy
 */
public class MappingFileTimeEventList implements TimeEventList {

    private static final int BUFFER_SIZE = 1024000;
    private static final int UNIT_SIZE = 8;
    private static final BlockingQueue<Runnable> tasks = new LinkedBlockingQueue<>(20);
    private boolean complete = false;
    private final File file;
    private final FileChannel channel;
    private int count = 0;
    private ByteBuffer buffer = ByteBuffer.allocate(BUFFER_SIZE);
    private MappedByteBuffer map;
    private final LinkedList<Long> stack = new LinkedList<>();
    private final TimeEventSerializer serializer = new TimeEventSerializer();
    private final boolean disposed = false;

    public MappingFileTimeEventList(File file) throws IOException {
        this.file = file;
        RandomAccessFile raf = new RandomAccessFile(file, "rw");
        raf.setLength(0);
        channel = raf.getChannel();
    }

    @Override
    public int size() {
        if (!complete || disposed) {
            throw new RuntimeException();
        }
        return count;
    }

    @Override
    public TimeEvent get(int index) {
        if (!complete || disposed) {
            throw new RuntimeException();
        }
        if (index >= count) {
            throw new IndexOutOfBoundsException(index + ">=" + count);
        }
        try {
            map.position(index * UNIT_SIZE);
            return read();
        } catch (IOException ex) {
            throw new RuntimeException(ex);
        }
    }

    @Override
    public void set(TimeEvent event, int index) {
        if (!complete || disposed) {
            throw new RuntimeException();
        }
        if (index >= count) {
            throw new IndexOutOfBoundsException(index + ">=" + count);
        }
        try {
            map.position(index * UNIT_SIZE);
            write(serializer.serialize(event));
        } catch (IOException ex) {
            throw new RuntimeException(ex);
        }
    }

    @Override
    public Iterator<TimeEvent> iterator() {
        if (!complete || disposed) {
            throw new RuntimeException();
        }
        return new Iterator<TimeEvent>() {
            private int index = 0;

            @Override
            public boolean hasNext() {
                return index < count;
            }

            @Override
            public TimeEvent next() {
                TimeEvent e = get(index);
                index++;
                return e;
            }

            @Override
            public void remove() {
                throw new UnsupportedOperationException("Not supported yet.");
            }
        };
    }

    public void push(long storage) throws IOException {
        if (complete || disposed) {
            throw new RuntimeException();
        }
        write(storage);
        count++;
    }

    public void complete() throws IOException {
        if (complete || disposed) {
            throw new RuntimeException();
        }
        complete = true;
        flush(true);
        final CountDownLatch countDownLatch = new CountDownLatch(1);
        try {
            tasks.offer(new Runnable() {
                @Override
                public void run() {
                    countDownLatch.countDown();
                }
            }, 24, TimeUnit.HOURS);
            countDownLatch.await();
        } catch (InterruptedException ex) {
            throw new RuntimeException(ex);
        }
        map = channel.map(FileChannel.MapMode.READ_WRITE, 0, channel.position());
        reOrder();
//        TODO no need
//        check();
    }

    private TimeEvent read() throws IOException {
        if (!complete || disposed) {
            throw new RuntimeException();
        }
        return serializer.deserialize(map.getLong());
    }

    private void write(long storage) throws IOException {
        if (complete || disposed) {
            map.putLong(storage);
        } else {
            buffer.putLong(storage);
            flush(false);
        }
    }

    private void flush(final boolean force) throws IOException {
        if (force || !buffer.hasRemaining()) {
            final ByteBuffer writeBuffer = buffer;
            buffer = ByteBuffer.allocate(1024000);
            try {
                Runnable runnable = new Runnable() {
                    @Override
                    public void run() {
                        try {
                            writeBuffer.limit(writeBuffer.position());
                            writeBuffer.position(0);
                            while (writeBuffer.hasRemaining()) {
                                channel.write(writeBuffer);
                            }
                            if (force) {
                                channel.force(false);
                            }
                        } catch (IOException ex) {
                            throw new RuntimeException(ex);
                        }
                    }
                };
                tasks.offer(runnable, 24, TimeUnit.HOURS);
            } catch (InterruptedException ex) {
                throw new RuntimeException(ex);
            }
        }
    }

    private void reOrder() {
        map.position(0);
        long lastTime = Long.MIN_VALUE;
        while (map.hasRemaining()) {
            long currentTime = map.getLong();
            if (lastTime <= currentTime) {
                lastTime = currentTime;
            } else {
//                System.out.println(lastTime + "   " + currentTime + " : " + TimeEvent.parse(currentTime).getChannel());
                popUp(currentTime);
                while (!stack.isEmpty()) {
                    map.putLong(stack.pop());
                }
            }
        }
    }

    private void popUp(long time) {
        stack.clear();
        if (map.position() >= UNIT_SIZE * 2) {
            map.position(map.position() - UNIT_SIZE * 2);
            long t = map.getLong();
            while (t > time) {
                stack.push(t);
                if (map.position() < UNIT_SIZE * 2) {
                    map.position(map.position() - UNIT_SIZE);
                    break;
                }
                map.position(map.position() - UNIT_SIZE * 2);
                t = map.getLong();
            }
        }
        stack.push(time);
    }

    private void check() {
        Iterator<TimeEvent> iterator = iterator();
        long t = Long.MIN_VALUE;
        while (iterator.hasNext()) {
            TimeEvent n = iterator.next();
            if (n.getTime() < t) {
                throw new RuntimeException();
            }
            t = n.getTime();
        }
    }

    static {
        Thread thread = new Thread(new Runnable() {
            @Override
            public void run() {
                while (true) {
                    try {
                        Runnable runnable = tasks.take();
                        runnable.run();
                    } catch (InterruptedException ex) {
                        throw new RuntimeException(ex);
                    }
                }
            }
        });
        thread.setDaemon(true);
        thread.start();
    }
}
