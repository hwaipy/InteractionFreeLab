#include "encoder.h"

void setWaveformPattern(
    int * newRandomNumbers1,
    int * newRandomNumbers2,
    int newRandomNumberSize,
	int newWaveformPeriodLength
) {
	if (newRandomNumberSize > 40000000) {
		printf("Argument Error in setRandomNumbers: newRandomNumberSize should not exceed 40000000.");
		return;
	}
	randomNumberSize = newRandomNumberSize;
	waveformPeriodLength = newWaveformPeriodLength;
	for (int i = 0; i < randomNumberSize; i++) {
		randomNumbers1[i] = newRandomNumbers1[i];
		randomNumbers2[i] = newRandomNumbers2[i];
	}
}

void setWaveformUnits(int channel, unsigned short waveformUnits[], int size) {
	if (channel < 0 || channel > 1) {
		printf("Channel should be 0 or 1.");
		return;
	}
	unsigned short * units = channel == 0 ? waveformUnits1 : waveformUnits2;
	for (int i = 0; i < size; i++) {
		units[i] = waveformUnits[i];
	}
}

void setDelay(int channel, int delaySample) {
	switch (channel) {
		case 0: delaySample1 = delaySample; break;
		case 1: delaySample2 = delaySample; break;
		default: printf("Channel should be 0 or 1.");
	}
}

void generateWaveformData(long address, long length, unsigned char * buffer) {
	long waveformLength = (long)randomNumberSize * waveformPeriodLength;

	long waveformPosition1 = address - delaySample1;
	long waveformPosition2 = address - delaySample2;
	if (waveformPosition1 >= waveformLength) waveformPosition1 -= waveformLength;
	if (waveformPosition1 < 0) waveformPosition1 += waveformLength;
	if (waveformPosition2 >= waveformLength) waveformPosition2 -= waveformLength;
	if (waveformPosition2 < 0) waveformPosition2 += waveformLength;
	int iRN1 = (int)(waveformPosition1 / waveformPeriodLength);
	int iRN2 = (int)(waveformPosition2 / waveformPeriodLength);
	int positionOfPeriod1 = (int)(waveformPosition1 % waveformPeriodLength);
	int positionOfPeriod2 = (int)(waveformPosition2 % waveformPeriodLength);

	for (long p = 0; p < length; p++) {
		if (waveformPosition1 >= waveformLength) waveformPosition1 -= waveformLength;
		if (waveformPosition1 < 0) waveformPosition1 += waveformLength;
		if (waveformPosition2 >= waveformLength) waveformPosition2 -= waveformLength;
		if (waveformPosition2 < 0) waveformPosition2 += waveformLength;
		int rn1 = randomNumbers1[iRN1];
		int rn2 = randomNumbers2[iRN2];
		unsigned short w1 = waveformUnits1[(long)rn1 * waveformPeriodLength + positionOfPeriod1];
		unsigned short w2 = waveformUnits2[(long)rn2 * waveformPeriodLength + positionOfPeriod2];
		long pByte = p * 4;
		buffer[pByte] = (w1 & 0xFF);
		buffer[pByte + 1] = (w1 >> 8);
		buffer[pByte + 2] = (w2 & 0xFF);
		buffer[pByte + 3] = (w2 >> 8);
		waveformPosition1++;
		waveformPosition2++;
		positionOfPeriod1++;
		positionOfPeriod2++;
		if (positionOfPeriod1 >= waveformPeriodLength) {
			positionOfPeriod1 = 0;
			iRN1++;
			if (iRN1 >= randomNumberSize) iRN1 = 0;
		}
		if (positionOfPeriod2 >= waveformPeriodLength) {
			positionOfPeriod2 = 0;
			iRN2++;
			if (iRN2 >= randomNumberSize) iRN2 = 0;
		}
	}
}

void generateFullWaveformData(unsigned char * buffer) {
	generateWaveformData(0, (long)randomNumberSize * waveformPeriodLength, buffer);
}

// void generateWaveformData(unsigned char * buffer) {
// 	long waveformLength = (long)randomNumberSize * waveformPeriodLength;


// 	long waveformPosition1 = -delaySample1;
// 	long waveformPosition2 = -delaySample2;
// 	if (waveformPosition1 >= waveformLength) waveformPosition1 -= waveformLength;
// 	if (waveformPosition1 < 0) waveformPosition1 += waveformLength;
// 	if (waveformPosition2 >= waveformLength) waveformPosition2 -= waveformLength;
// 	if (waveformPosition2 < 0) waveformPosition2 += waveformLength;
// 	int iRN1 = (int)(waveformPosition1 / waveformPeriodLength);
// 	int iRN2 = (int)(waveformPosition2 / waveformPeriodLength);
// 	int positionOfPeriod1 = (int)(waveformPosition1 % waveformPeriodLength);
// 	int positionOfPeriod2 = (int)(waveformPosition2 % waveformPeriodLength);

// 	for (long p = 0; p < waveformLength; p++) {
// 		if (waveformPosition1 >= waveformLength) waveformPosition1 -= waveformLength;
// 		if (waveformPosition1 < 0) waveformPosition1 += waveformLength;
// 		if (waveformPosition2 >= waveformLength) waveformPosition2 -= waveformLength;
// 		if (waveformPosition2 < 0) waveformPosition2 += waveformLength;
// 		int rn1 = randomNumbers[iRN1];
// 		int rn2 = randomNumbers[iRN2];
// 		unsigned short w1 = waveformUnits1[(long)rn1 * waveformPeriodLength + positionOfPeriod1];
// 		unsigned short w2 = waveformUnits2[(long)rn2 * waveformPeriodLength + positionOfPeriod2];
// 		long pByte = p * 4;
// 		buffer[pByte] = (w1 & 0xFF);
// 		buffer[pByte + 1] = (w1 >> 8);
// 		buffer[pByte + 2] = (w2 & 0xFF);
// 		buffer[pByte + 3] = (w2 >> 8);
// 		waveformPosition1++;
// 		waveformPosition2++;
// 		positionOfPeriod1++;
// 		positionOfPeriod2++;
// 		if (positionOfPeriod1 >= waveformPeriodLength) {
// 			positionOfPeriod1 = 0;
// 			iRN1++;
// 			if (iRN1 >= randomNumberSize) iRN1 = 0;
// 		}
// 		if (positionOfPeriod2 >= waveformPeriodLength) {
// 			positionOfPeriod2 = 0;
// 			iRN2++;
// 			if (iRN2 >= randomNumberSize) iRN2 = 0;
// 		}
// 	}
// }




	// for (int i = 0; i < randomNumberSize; i++) {
	// 	long waveformPosition1 = (long)i * waveformPeriodLength + delaySample1;
	// 	int rn = randomNumbers[i];
	// 	long waveformUnitPosition = (long)rn * waveformPeriodLength;
	// 	for (int j = 0; j < waveformPeriodLength; j++) {
	// 		unsigned short w1 = waveformUnits1[waveformUnitPosition + j];
	// 		long p1 = waveformPosition1 + j;
	// 		if (p1 >= waveformLength) p1 -= waveformLength;
	// 		if (p1 < 0) p1 += waveformLength;
	// 		buffer[p1 * 4] = (w1 & 0xFF);
	// 		buffer[p1 * 4 + 1] = (w1 >> 8);
	// 	}
	// }
	// for (int i = 0; i < randomNumberSize; i++) {
	// 	long waveformPosition2 = (long)i * waveformPeriodLength + delaySample2;
	// 	int rn = randomNumbers[i];
	// 	long waveformUnitPosition = (long)rn * waveformPeriodLength;
	// 	for (int j = 0; j < waveformPeriodLength; j++) {
	// 		unsigned short w2 = waveformUnits2[waveformUnitPosition + j];
	// 		long p2 = waveformPosition2 + j;
	// 		if (p2 >= waveformLength) p2 -= waveformLength;
	// 		if (p2 < 0) p2 += waveformLength;
	// 		buffer[p2 * 4 + 2] = (w2 & 0xFF);
	// 		buffer[p2 * 4 + 3] = (w2 >> 8);
	// 	}
	// }
	