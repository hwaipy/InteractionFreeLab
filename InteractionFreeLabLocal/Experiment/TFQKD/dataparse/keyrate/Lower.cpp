#include "Lower.h"
#include "Parameters.h"
#include <math.h>
using namespace std;
double Lower(double U)
{
	extern const double xi;
	double b = -log(xi / 2.0) / U;
	double low = 0.0;
	double up = 0.9999;

	if (xi >= 0.5)
	{
		return U;
	}

	if (up + (1 - up) * log(1 - up) - b < 0)
	{
		return 0.0;
	}//the value of delta is too close to 1
	double temp = 0;
	double f = 0;
	while (up - low >= 1.0e-6)
	{
		temp = (up + low) / 2.0;
		f = temp + (1.0 - temp) * log(1.0 - temp) - b;
		if (f > 0)
		{
			up = temp;
		}
		else
		{
			low = temp;
		}
	}
	return (1.0 - up) * U;
}
double Lower(double U, double xii)
{
	if (xii >= 0.5)
	{
		return U;
	}

	if (U < 2)
	{
		return 0.0;
	}
	//extern const double xi;
	double b = -log(xii / 2.0) / U;
	double low = 0.0;
	double up = 0.9999;
	if (up + (1 - up) * log(1 - up) - b < 0)
	{
		return 0.0;
	}//the value of delta is too close to 1
	double temp = 0;
	double f = 0;
	while (up - low >= 1.0e-6)
	{
		temp = (up + low) / 2.0;
		f = temp + (1.0 - temp) * log(1.0 - temp) - b;
		if (f > 0)
		{
			up = temp;
		}
		else
		{
			low = temp;
		}
	}
	return (1.0 - up) * U;
}
