# TDC DataBlock Serialization

## DataBlock

A DataBlock is a data structure that describe TDC events in a certain duration, which contain the following information:

`creationTime`: Specify the absolute time of data fetching. The accuracy is normally < 1 s.

`resolution`: Specify the time unit of `dataTimeBegin`, `dataTimeEnd`, and `content`.

`dataTimeBegin`: Specify the begin of the DataBlock relative to the TDC time.

`dataTimeEnd`: Specify the end of the DataBlock relative to the TDC time. Has the same resolution with `dataTimeBegin`. `dataTimeEnd` is required to be larger than `dataTimeBegin`.

`content`: TDC events. For each event, `time` and `channel` is specified. `time` is required to be bewteen `dataTimeBegin` and `dataTimeEnd`.  `channel` start with `0`.

`released`: To prevent memory leak, a DataBlock is allowed to be RELEASED. In this case, `content` will be empty. The DataBlock itself still remains to notify the program that "there was a DataBlock" but the information of events are lost. 

`sizes`: A list of integer that specify the number of events in each channel. This information is useful when the DataBlock is RELEASED.

## Protocol_V1

The entire DataBlock should be serialized by [MsgPack](https://msgpack.org) as follows:

```
{
	"Format": "DataBlock_V1",
	"CreationTime": $creationTime,
	"Resolution": $resolution,
	"DataTimeBegin": $dataTimeBegin,
	"DataTimeEnd": $dataTimeEnd,
	"Sizes": $sizes,
	"Content": $serializedContent
}
```

`creationTime`: `Long`. milliseconds from midnight, January 1, 1970 UTC (coordinated universal time).

`resolution`: `Float`. Second. For example, 1 ps is `1e-12`.

`dataTimeBegin`, `dataTimeEnd`: `Long`. Picosecond. For example, 1 ms with `resolution` of `16` is `62,500,000`.

`sizes`: `Array[Int]`.

`$serializedContent`: `Array[Array[Array[Byte]]]`. This is the key of DataBlock serialization. The `content` should be serialized channel by channel. For each channel, the events are sliced into fragments to enhence the capacity of parallelism. The size of each fragment is recommand to be 100000, yet not restricted. Each fragment of events is serialized as `Array[Byte]`, thus a channel of events is serialized as  `Array[Array[Byte]]`. Each fragment is serialized as follows:

1. Suppose there is `N` events in total. Record the first time as `TIME_FIRST`.
2. Calculate time differents between neighbor events. `delta[i] = time[i+1] - time[i]`, `i=0` to `N-1`.
3. Each time difference is serialized independently by two's-complement representation, and sliced as 4 * Q bits. Q is the minimal valid positive integer that remains the value of the number. Examples are listed below. Max valid Q is 15.

| Decimal | Binary | Q |
| :----: | :----: | :----: |
| 0 | 0 | 1 |
| 1 | 1 | 1 |
| 7 | 111 | 1 |
| 8 | 1000 | 2 |
| 127 | 1111111 | 2 |
| 128 | 10000000 | 3 |
| -1 | ...1111 | 1 |
| -2 | ...1110 | 1 |
| -8 | ...1000 | 1 |
| -9 | ...11110111 | 2 |
| -128 | ...10000000 | 2 |
| -129 | ...111101111111 | 3 |

4. Generate binaries. The first 8 bits represent `TIME_FIRST`, big-endian, signed. The following bits are group in 4, for the storage of time differences. Time differences are written one by one. For each time difference, the first 4 bits represents Q, and the following Q * 4 bits represent the value. After the written of the last time difference, any remaining bits of the last byte are filled with 0.