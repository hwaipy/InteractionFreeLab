package com.interactionfree.instrument.tdc

import com.interactionfree.instrument.tdc.TDCDataAdapter;
import java.nio.ByteBuffer
import java.nio.ByteOrder

class SwabianTDCDataAdapter extends TDCDataAdapter {

  def offer(data: Any) = data match {
    case null => null
    case _ => {
      val buffer = data match {
        case data: Array[Byte] => ByteBuffer.wrap(data)
        case data: ByteBuffer  => data
        case _                 => throw new RuntimeException("Only byte array or ByteBuffer are acceptable for GroundTDCDataAdapter.")
      }
      buffer.order(ByteOrder.LITTLE_ENDIAN)
      val timeEvents = buffer.asLongBuffer()
      timeEvents
    }
  }

  def flush(data: Any) = offer(data)
}
