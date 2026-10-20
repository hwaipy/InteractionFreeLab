#include "KR_yu.h"
#include <string>
#include "Xupper.h"
#include "Xlower.h"
#include "Lower.h"
#include "Up.h"
#include "Parameters.h"
#include "math.h"
using namespace std;

extern const double xi;//zhixindu
extern const double N;
extern const double f;
extern const double Ed;
extern const double d;
extern const string ty;
inline double Hs(double x)
{
	return (-(1.0 - x) * log(1.0 - x) / log(2.0) - x * log(x) / log(2.0));
}

double KR_yu(double * results)
{
	double miux, miuy, miuz, NZZ33, NZZ03, NZZ30, NZZ00, NZX00, NZX01, NZX02, NXZ00, NXZ10, NXZ20, NXX00, NXX01,
		NXX02, NXX10, NXX20, NXX11, NXX, Nt, NXX12, NXX21, NXX22;
	double nzz33, nzz03, nzz30, nzz00, nzx00, nzx01, nzx02, nxz00, nxz10, nxz20, nxx00, nxx01,
		nxx02, nxx10, nxx20, nxx11, mxx11, nxx12, nxx21, nxx22;
	double p0, px, py, pz, ep;

	p0 = results[0];
	px = results[1];
	py = results[2];
	pz = results[3] + results[4];
	ep = results[3] / pz; //Z基下的发射概率

	miux = results[5];
	miuy = results[6];
	miuz = results[7];

	Nt = results[8] + 0.000001;

	NZZ00 = (results[9] + 1e-10) * Nt;
	NZZ03 = (results[10] + 1e-10) * Nt;
	NZX00 = (results[11] + 1e-10) * Nt;
	NZX01 = (results[12] + 1e-10) * Nt;
	NZX02 = (results[13] + 1e-10) * Nt;

	NZZ30 = (results[14] + 1e-10) * Nt;
	NZZ33 = (results[15] + 1e-10) * Nt;

	NXZ00 = (results[19] + 1e-10) * Nt;
	NXX00 = (results[21] + 1e-10) * Nt;
	NXX01 = (results[22] + 1e-10) * Nt;
	NXX02 = (results[23] + 1e-10) * Nt;	 	  	 	

	NXZ10 = (results[24] + 1e-10) * Nt;
	NXX10 = (results[26] + 1e-10) * Nt;
	NXX11 = (results[27] + 1e-10) * Nt;

	NXZ20 = (results[29] + 1e-10) * Nt;
	NXX20 = (results[31] + 1e-10) * Nt;

	nzz00 = (results[34] + 1e-10);
	nzz03 = (results[35] + 1e-10);
	nzx00 = (results[36] + 1e-10);
	nzx01 = (results[37] + 1e-10);
	nzx02 = (results[38] + 1e-10);

	nzz30 = (results[39] + 1e-10);
	nzz33 = (results[40] + 1e-10);

	nxz00 = (results[44] + 1e-10);
	nxx00 = (results[46] + 1e-10);
	nxx01 = (results[47] + 1e-10);
	nxx02 = (results[48] + 1e-10);

	nxz10 = (results[49] + 1e-10);
	nxx10 = (results[51] + 1e-10);
	nxx11 = (results[52] + 1e-10);
	
	nxz20 = (results[54] + 1e-10);
	nxx20 = (results[56] + 1e-10);

	double frac = results[59] + 1e-10;
	NXX = NXX11 * frac;
	mxx11 = results[60] + 1e-10;

	double Q01x = Xlower(nzx01 + nxx01) / (NZX01 + NXX01);
	double Q01y = Xupper(nzx02 + nxx02) / (NZX02 + NXX02);
	double Hup = Xupper(nxx00 + nxz00 + nzx00) / (NXX00 + NXZ00 + NZX00);
	double Hlow = Xlower(nxx00 + nxz00 + nzx00) / (NXX00 + NXZ00 + NZX00);

	double s01 = 0.5 * (exp(-miuy) * miuy * miuy * Q01x - exp(-miux) * miux * miux * Q01y - (exp(-miux) * exp(-miuy) * miuy * miuy - exp(-miux) * exp(-miuy) * miux * miux) * Hup) / \
		(exp(-miux - miuy) * miux * miuy * miuy / 2.0 - exp(-miux - miuy) * miux * miux * miuy / 2.0);

	double Q10x = Xlower(nxz10 + nxx10) / (NXZ10 + NXX10);
	double Q10y = Xupper(nxz20 + nxx20) / (NXZ20 + NXX20);


	double s10 = 0.5 * (exp(-miuy) * miuy * miuy * Q10x - exp(-miux) * miux * miux * Q10y - (exp(-miux) * exp(-miuy) * miuy * miuy - exp(-miux) * exp(-miuy) * miux * miux) * Hup) / \
		(exp(-miux - miuy) * miux * miuy * miuy / 2.0 - exp(-miux - miuy) * miux * miux * miuy / 2.0);

	double Q0x = Xlower(nzx01 + nxx01 + nxz10 + nxx10) / (NZX01 + NXX01 + NXZ10 + NXX10);
	double Q0y = Xupper(nzx02 + nxx02 + nxz20 + nxx20) / (NZX02 + NXX02 + NXZ20 + NXX20);

	double s1 = 0.5 * (exp(-miuy) * miuy * miuy * Q0x - exp(-miux) * miux * miux * Q0y - (exp(-miux) * exp(-miuy) * miuy * miuy - exp(-miux) * exp(-miuy) * miux * miux) * Hup) / \
		(exp(-miux - miuy) * miux * miuy * miuy / 2.0 - exp(-miux - miuy) * miux * miux * miuy / 2.0);


	double NZ = NZZ03 + NZZ30 + NZZ33 + NZZ00;
	double n10 = NZ * ep * (1 - ep) * miuz * exp(-miuz) * s10;

	double n01 = NZ * ep * (1 - ep) * miuz * exp(-miuz) * s01;

	double n1 = NZ * ep * (1 - ep) * miuz * exp(-miuz) * s1 * 2.0;

	double n1b = Lower(n01 + n10);

	double nc0 = nzz03;
	double nc1 = nzz30;
	double nv = nzz00;
	double nd = nzz33;

	double ntb = nc0 + nc1 + nv + nd;
	double Eb = (nv + nd) / ntb;

	double ng = 0.0;
	if ((nc1 + nv) < (nd + nc0))
	{
		ng = nc1 / 2.0 + nv / 2.0;
	}
	else
	{
		ng = nc0 / 2.0 + nd / 2.0;
	}
	double nodd = (nc0 + nd) * (nc1 + nv) / (nc0 + nc1 + nv + nd);
	double u = ng / nodd;
	double qv = nc1 / (nc1 + nv);
	double qd = nc0 / (nc0 + nd);
	double ncc = qv * qd * ng;
	double nvd = (1.0 - qv) * (1.0 - qd) * ng;
	double E = nvd / (ncc + nvd);
	double nt = ncc + nvd;

	double n10L = Lower(u * n10);
	double n01L = Lower(u * n01);
	double nuL = Lower(n1 * u);// n10L + n01L;

	double nn2 = nuL * nuL / (u * (nc0 + nc1 + nv + nd)) * 0.5;
	nn2 = Lower(nn2) * 2.0;
	double kk = nuL - nn2;

	double ttt = sqrt(-log(xi) / 2.0 / nn2);
	if (xi >= 0.5)
	{
		ttt = 0;
	}
	double n01uL = nn2 * (n01L / nuL - ttt);
	double n10uL = nn2 * (n10L / nuL - ttt);
	if (n10uL < n01uL)
	{
		n01uL = n10uL;
	}

	double pu = n01uL / nn2;

	double n11l = Lower(nn2 * (1 - pu) * pu);


	double xi1 = xi;//
	double xi2 = 0.5;//
	double xi3 = xi;//
	double epr = xi;//
	double gamma2 = 2.33;
	double gamma3 = 6.36;/**/

	double r = -(nn2 + kk) * log(epr / 3.0 / kk / kk) / kk;
	if (xi > 0.5)
	{
		r = 0;
	}



	double Mbar = 1e20;
	double Mbars = 1e20;


	double Txx = 1;
	double e1 = 1;
	double e1u = 1.0;
	double e11u = 1.0;
	double miuax = miux;
	double miubx = miux;

	Txx = Xupper(mxx11, xi1) / (NXX);
	Hlow = Xlower(nxx00 + nxz00 + nzx00, xi1) / (NXX00 + NXZ00 + NZX00);
	e1 = (Txx - exp(-miuax - miubx) * Hlow / 2.0) / (exp(-miuax - miubx) * (miuax + miubx) * s1);

	if (e1 > 0.5)
	{
		e1 = 0.5;
	}
	Mbar = Up(nn2 * e1, xi1);
	double eep = Mbar / (nn2 - r);
	double EE = eep * (1.0 - eep);
	Mbars = Up((nn2 / 2.0 - r) * EE, xi3) + r;
	e11u = Mbars / n11l;

	double Rtemp = 0;
	double R = 0;
	if (s1 > 0 && e1 > 0.0 && e1 < 0.50 && e11u>0.0 && e11u < 0.5 && E>0 && E < 0.5 && s1 < 1.0) {
		Rtemp = 2.0 * (n11l * (1 - Hs(e11u)) - f * nt * Hs(E) + 5.0 * log2(xi)) / Nt; // +10.0 * log2(xi)
	}
	else
	{
		Rtemp = 0.0;

	}
	double n1after = n11l * 2.0;

	if (Rtemp > R)
	{
		R = Rtemp;
	}

	return R;
}
