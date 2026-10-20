#include "Xlower.h"
#include "Parameters.h"
#include <math.h>
// #include<iostream>
using namespace std;
double Xlower(double X)
{
	extern const double xi;
	double b = -log(xi / 2.0);
	double low = 0.0;
	double up = 10.0;

	if (xi >= 0.5)
	{
		return X;
	}

	for (int i = 1; i != 4; i++)
	{
		if ((1.0 - 1.0 / (1.0 + up) - log(1.0 + up) + b / X) <= 0) {
			break;
		}
		else {
			up = up * 10.0;
		}
	}

	if ((1.0 - 1.0 / (1.0 + up) - log(1.0 + up) + b / X) > 0) {
		return 0.0;
	}
	while ((up - low) >= 1e-10) {
		double temp = (up + low) / 2.0;
		if ((1.0 - 1.0 / (1.0 + temp) - log(1.0 + temp) + b / X) <= 0)
			up = temp;
		else
		{
			low = temp;
		}
	}
	return (X / (1.0 + low));
}
double Xlower(double X, double xii)
{

	if (xii >= 0.5)
	{
		return X;
	}
	double b = -log(xii / 2.0);
	double low = 0.0;
	double up = 10.0;
	for (int i = 1; i != 4; i++)
	{
		if ((1.0 - 1.0 / (1.0 + up) - log(1.0 + up) + b / X) <= 0) {
			break;
		}
		else {
			up = up * 10.0;
		}
	}

	if ((1.0 - 1.0 / (1.0 + up) - log(1.0 + up) + b / X) > 0) {
		return 0.0;
	}
	while ((up - low) >= 1e-6) {
		double temp = (up + low) / 2.0;
		if ((1.0 - 1.0 / (1.0 + temp) - log(1.0 + temp) + b / X) <= 0)
			up = temp;
		else
		{
			low = temp;
		}
	}
	return (X / (1.0 + low));
}