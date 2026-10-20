#include <stdio.h>

int randomNumbers1[40000000];
int randomNumbers2[40000000];
int randomNumberSize;
int waveformPeriodLength;
unsigned short waveformUnits1[10000];
unsigned short waveformUnits2[10000];
int delaySample1;
int delaySample2;

// void setRandomNumbers(int * newRandomNumbers, int newRandomNumberSize, int newWaveformPeriodLength);
void setWaveformPattern(int * newRandomNumbers1, int * newRandomNumbers2, int newRandomNumberSize, int newWaveformPeriodLength);

void setWaveformUnits(int channel, unsigned short waveformUnits[], int size);

void setDelay(int channel, int delaySample);

void generateWaveformData(long address, long length, unsigned char * buffer);

void generateFullWaveformData(unsigned char * buffer);