#include <stdio.h>
#include "main.h"
#include "KR_yu.h"
#include "Parameters.h"

int main()
{
	double O[4];
	// KR_yu(1, O);
	printf("%e\n", O[0]);
	// std::cout << O[1] << ", " << O[0] << "\n";
	return 0;
}

extern "C" double keyrate(double * results)
{
	double O[4];
	double kr = KR_yu(results);
	// printf("xi = %f\n", xi);
	// printf("kr = %e\n", kr);
	return kr;
	// return 1109092;
}