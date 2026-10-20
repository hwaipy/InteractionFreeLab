#include "Up.h"
#include "Parameters.h"
#include <math.h>
using namespace std;
double Up(double U)
{
	extern const double xi;
	double b = -log(xi / 2.0) / U;
	double low = 0.0;
	double up = 1000;

	if (xi >= 0.5)
	{
		return U;
	}

	if (up - (1.0 + up) * log(1.0 + up) + b > 0)
	{
		return 1000000.0 * U;
	}// the value of delta is larger than 1000
	double temp = 0;
	double f = 0;
	while (up - low >= 1.0e-10)
	{
		temp = (up + low) / 2.0;
		f = temp - (1.0 + temp) * log(1.0 + temp) + b;
		if (f > 0)
		{
			low = temp;
		}
		else
		{
			up = temp;
		}
	}
	return (1.0 + up) * U;
}
double Up(double U, double xii)
{
	//extern const double xi;

	if (xii >= 0.5)
	{
		return U;
	}

	if (U < 0.1)
	{
		return 10.0;
	}
	double b = -log(xii / 2.0) / U;
	double low = 0.0;
	double up = 1000;
	if (up - (1.0 + up) * log(1.0 + up) + b > 0)
	{
		return 1000000.0 * U;
	}// the value of delta is larger than 1000
	double temp = 0;
	double f = 0;
	while (up - low >= 1.0e-10)
	{
		temp = (up + low) / 2.0;
		f = temp - (1.0 + temp) * log(1.0 + temp) + b;
		if (f > 0)
		{
			low = temp;
		}
		else
		{
			up = temp;
		}
	}
	return (1.0 + up) * U;
}

