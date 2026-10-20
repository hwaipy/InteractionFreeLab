// #include "timetag.h"

// int serializeDataBlock(long long *data, int begin, int end, unsigned char *buffer)
// {
//   long long head = data[begin];
//   unsigned char unit[16];
//   for (int i = 0; i < 8; i++)
//   {
//     buffer[7 - i] = (head & 0xFF);
//     head >>= 8;
//   }
//   int unitSize = 15;
//   int hasHalfByte = 0;
//   int halfByte = 0;
//   int pBuffer = 8;
//   int i = begin;
//   while (i < end - 1)
//   {
//     long long delta = data[i + 1] - data[i];
//     i++;
//     if (delta > 1e16 || delta < -1e16)
//     {
//       printf("-1-1-1\n");
//       return -1;
//     }
//     long long value = delta;
//     int length = 0;
//     int valueBase = (delta >= 0) ? 0 : -1;
//     for (int j = 0; j < unitSize; j++)
//     {
//       unit[unitSize - length] = value & 0xf;
//       value >>= 4;
//       length++;
//       if (value == valueBase && !((unit[unitSize - length + 1] & 0x8) == ((delta >= 0) ? 0x8 : 0x0)))
//       {
//         break;
//       }
//     }
//     unit[unitSize - length] = length;
//     int p = 0;
//     while (p <= length)
//     {
//       if (hasHalfByte)
//       {
//         buffer[pBuffer] = ((halfByte << 4) | unit[unitSize - length + p]);
//         pBuffer++;
//       }
//       else
//       {
//         halfByte = unit[unitSize - length + p];
//       }
//       hasHalfByte = !hasHalfByte;
//       p++;
//     }
//   }
//   if (hasHalfByte)
//   {
//     buffer[pBuffer] = (halfByte << 4);
//     pBuffer++;
//   }
//   return pBuffer;
//   // return bytes(buffer[:pBuffer])
// }

// int deserializeDataBlock(unsigned char *data, int length, long long *result)
// {
//   int pResult = 0;
//   if (length > 0)
//   {
//     long long offset = 0;
//     offset += data[0];
//     for (int i = 0; i < 7; i++)
//     {
//       offset <<= 8;
//       offset += data[i + 1];
//     }
//     result[pResult] = offset;
//     pResult++;
//     long long previous = offset;

//     int positionC = 8;
//     int pre = 1;

//     while (positionC < length)
//     {
//       int len = (pre ? ((data[positionC] >> 4) & 0x0f) : (data[positionC++] & 0x0f)) - 1;
//       pre = 1 - pre;
//       if (len >= 0)
//       {
//         long long value = ((pre ? ((data[positionC] >> 4) & 0x0f) : (data[positionC++] & 0x0f)) & 0xf);
//         pre = 1 - pre;
//         if ((value & 0x8) == 0x8)
//         {
//           value |= -16;
//         }
//         while (len > 0)
//         {
//           value <<= 4;
//           value |= ((pre ? ((data[positionC] >> 4) & 0x0f) : (data[positionC++] & 0x0f)) & 0xf);
//           pre = 1 - pre;
//           len -= 1;
//         }
//         previous += value;
//         result[pResult] = previous;
//         pResult++;
//       }
//     }
//   }
//   return pResult;
// }

// void mergeDataSection(long long *des, int pDest, long long *src, int pSrc, int size)
// {
//   memcpy(des + pDest, src + pSrc, size);
// }

// void convertNumpyContent(long long* timestamps, int timestampLength, int* channels, int channelLength) {
//   printf("fhjwoifhwaoufhjoawfen\n");
//   printf("%lld %lld %lld\n", timestamps[0], timestamps[100], timestamps[9999999]);
//   printf("%lld %lld %lld\n", channels[0], channels[100], channels[9999999]);
// }

// void histogram(long long* triggerList, int triggerLength, long long* signalList, int signalLength, int binCount, int divide, long long viewFrom, long long viewTo, int* result) {
//   double min = (double)(viewFrom);
//   double max = (double)(viewTo);
//   double binSize = (max - min) / binCount / divide;

//   if (triggerLength > 0 && signalList > 0) {
//     int preStartT = 0;
//     int sp = 0;
//     while (sp < signalLength) {
//       long long s = signalList[sp];
//       int cont = 1;
//       while (preStartT < triggerLength && cont) {
//         long long t = triggerList[preStartT];
//         long long delta = s - t;
//         if (delta > viewTo) {
//           preStartT++;
//         } else {
//           cont = 0;
//         }
//       }
//       int tIndex = preStartT;
//       cont = 1;
//       while (tIndex < triggerLength && cont) {
//         long long t = triggerList[tIndex];
//         long long delta = s - t;
//         if (delta >= viewFrom) {
//           // A valid delta.
//           double deltaDouble = (double)(delta);
//           if (deltaDouble < min) {
//           } else if (deltaDouble == max) {
//             result[binCount - 1]++;
//           } else if (deltaDouble > max) {
//           } else {
//             int bin = (int)((deltaDouble - min) / binSize) % binCount;
//             result[bin]++;
//           }
//           tIndex++;
//         } else {
//           cont = 0;          
//         }
//       }
//       sp++;
//     }
//   }
// }