#include "Xupper.h"
#include "Parameters.h"
#include <math.h>
// #include <iostream>
using namespace std;
double Xupper(double X)
{
	extern const double xi;
	double b = -log(xi / 2.0);
	double low = 0.0;
	double up = 0.9999;
	if (xi >= 0.5)
	{
		return X;
	}

	if ((1.0 - 1.0 / (1.0 - up) - log(1.0 - up) + b / X) > 0) {
		return 100000.0 * X;
	}
	while ((up - low) >= 1e-9) {
		double temp = (up + low) / 2.0;
		if ((1.0 - 1.0 / (1.0 - temp) - log(1.0 - temp) + b / X) <= 0)
			up = temp;
		else
		{
			low = temp;
		}
	}
	return (X / (1.0 - low));
}
double Xupper(double X, double xii)
{

	if (xii >= 0.5)
	{
		return X;
	}
	double b = -log(xii / 2.0);
	double low = 0.0;
	double up = 0.9999;

	if ((1.0 - 1.0 / (1.0 - up) - log(1.0 - up) + b / X) > 0) {
		return 1000.0 * X;
	}
	while ((up - low) >= 1e-6) {
		double temp = (up + low) / 2.0;
		if ((1.0 - 1.0 / (1.0 - temp) - log(1.0 - temp) + b / X) <= 0)
			up = temp;
		else
		{
			low = temp;
		}
	}
	return (X / (1.0 - low));
}

