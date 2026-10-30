"""Transcribed published numbers, not generated/fitted key-rate targets.
Array indices on both axes: [vacuum, nu, mu]; X intensities are doubled.
"""
import numpy as np
from model import Source


def prx2025():
    result=[]
    zrows=[ [0,0,19], [912,220,3885], [13639,1452,36123],
            [899,204,3799], [1256956,558753,392658], [18607910,3638570,3674645],
            [14166,1557,34656], [19087863,4080155,3665849], [281215881,26646030,34412624] ]
    xrows=[ [0,0,0], [624375,299088,200568], [13488265,12774216,17723656],
            [641524,264452,190050], [53991,50269,44713], [2969156,651638,1159813],
            [145543908,14008155,16903994], [3059991,734656,1132510], [9037747,863571,1502874] ]
    # 101 km X(2mu,0) is visually ambiguous in PDF text extraction; this value
    # is retained as transcribed and flagged in references.json; excluded from
    # an assertion of full reproduction until checked against PDF rendering.
    exrows=[ [0,0,0], [312187.5,149544,100284], [6744132.5,6387108,8861828],
             [320762,132226,95025], [14808,14377,13583], [1342262,286390,531537],
             [72771954,7004077.5,8451997], [1386915,317844,516815], [2412570,239806,441223] ]
    for i,(d,mu,nu,pm,pn,n,r) in enumerate(zip([101,202,403],[.266,.234,.292],[.016,.020,.018],[.206,.185,.199],[.227,.303,.325],[.7e12,1e12,1e14],[8.91e-5,5.76e-6,4.37e-8])):
        z=np.array(zrows,float)[:,i].reshape(3,3); x=np.array(xrows,float)[:,i].reshape(3,3)
        ze=np.zeros((3,3)); ze[1:,1:]=np.array([[ [766,249,5186][i],[5760,883,26099][i]],[[5999,991,25314][i],[9756,1096,29609][i]]])
        result.append(dict(id=f'prx2025_{d}',source=Source(mu,nu,pm,pn),counts=dict(z=z,x=x,xe=np.array(exrows,float)[:,i].reshape(3,3),ze=ze,n_slots=n),published_rate=r,clock_hz=1.25e9*7/8,distance=d,loss=[19.2,38.4,76.5][i]))
    return result


def field2024():
    result=[]
    for i in range(2):
        a=Source(*[(.3609,.036,.25,.25),(.148,.0032,.12,.25)][i])
        b=Source(*[(.3337,.0343,.25,.25),(.68,.0541,.25,.25)][i])
        z=[[[3,948,8955],[966,908463,8833952],[9238,9078513,88377993]],
           [[184,4830,58189],[2986,1064193,13334537],[63256,23581217,294929141]]][i]
        ze=[[[0,0,0],[0,947,4998],[0,5021,9020]],[[0,0,0],[0,3376,24738],[0,32318,42930]]][i]
        x=[[[3,459106,43376782],[465156,57045,1642605],[46652989,1757516,5549824]],
           [[184,881145,138310497],[331330,54259,3058876],[162706031,5389093,9113959]]][i]
        xe=[[[1.5,229101,21607575],[231874,19683,732276],[23313611,788350,1882646]],
            [[92,444240,69704510],[166966,19282,1427742],[81983904,2608963,3468649]]][i]
        sz=[[[823590,5944932],[5959809,43019763]],[[969782,6510179],[18596822,124841146]]][i]
        result.append(dict(id=['field2024_symmetric','field2024_asymmetric'][i],alice=a,bob=b,
            counts=dict(z=np.array(z,float),ze=np.array(ze,float),x=np.array(x,float),xe=np.array(xe,float),n_slots=2e12),
            published_single_z=np.array(sz),published_phase=[.3131,.3152][i],published_bits=[5477255,13899131][i],
            published_bps=[1217.17,3088.69][i],clock_hz=444.83e6,
            eta_a=[5.767e-3,7.523e-2][i]*.72,eta_b=[6.004e-3,5.723e-3][i]*.72))
    return result


def prl2023():
    rows=[]
    for i,d in enumerate([101,202,304,407]):
        rows.append(dict(id=f'prl2023_{d}',distance=d,
            n_slots=[5.07e11,2.10e12,6.33e12,7.66e13][i],
            single_z=[1.07e8,5.03e7,4.51e6,6.02e6][i],phase=[.2474,.2571,.3370,.3468][i],
            z=[207389568,108781949,14657476,16100111][i],ze=[64238,20550,5494,23545][i],
            p_click=[6.35e-3,1.13e-3,1.89e-4,5e-5][i],lmax=[500,1000,2000,2000][i],
            pair_rate=[2.46e-3,4.29e-4,4.42e-5,4.21e-6][i],
            published_rate_per_two_slots=[7.75e-5,9.34e-6,8.65e-8,3.46e-9][i],
            published_bps=[1.72e4,2.08e3,19.2,.769][i]))
    return rows
