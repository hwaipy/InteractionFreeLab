package com.hwaipy.unifieddeviceinterface.timeeventdevice.pxi40ps1data;

import java.io.IOException;
import java.nio.ByteBuffer;
import java.nio.channels.FileChannel;

/**
 *
 * @author Hwaipy
 */
class MappingReader {

    private final ByteBuffer buffer = ByteBuffer.allocate(1024000);
    private final ByteBuffer unitBuffer = ByteBuffer.allocate(8);
    private final ByteBuffer fixBuffer = ByteBuffer.allocate(824);
    private long startPosition = 0;
    private long size = 0;
    private final FileChannel channel;

    public MappingReader(FileChannel channel) throws IOException {
        this.channel = channel;
        channel.position(0);
        size = channel.size();
        readIn(0);
    }

    //这个函数可能有问题。buffer可能会overflow。
    public void rollBackUnit() {
        buffer.position(buffer.position() - 8);
    }

    //这个函数可能有问题。buffer可能会overflow。
    public void skip(int size) {
        buffer.position(buffer.position() + size);
    }

    public ByteBuffer getNextUnit() throws IOException {
        if (read(unitBuffer)) {
            return unitBuffer;
        }
        return null;
    }

    public ByteBuffer getFixBuffer() throws IOException {
        if (read(fixBuffer)) {
            return fixBuffer;
        }
        return null;
    }

    private boolean read(ByteBuffer bb) throws IOException {
        if (buffer.remaining() < bb.capacity()) {
            startPosition += buffer.position();
            readIn(startPosition);
        }
        if (buffer.remaining() < bb.capacity()) {
            return false;
        }
        buffer.get(bb.array());
        bb.position(0);
        bb.limit(bb.capacity());
        return true;
    }

    private void readIn(long startPosition) throws IOException {
        long remaining = size - startPosition;
        long readLength = remaining > 1024000 ? 1024000 : remaining;
        channel.position(startPosition);
        buffer.position(0);
        buffer.limit(buffer.capacity());
        while (readLength > 0) {
            readLength -= channel.read(buffer);
        }
        buffer.limit(buffer.position());
        buffer.position(0);
    }
}
