import time
import ntplib
import os
import win32api

if __name__ == '__main__':
    print('NTP sync started.')
    while True:
        response = ntplib.NTPClient().request('172.16.60.200')
        tm_year, tm_mon, tm_mday, tm_hour, tm_min, tm_sec, tm_wday, tm_yday, tm_isdst = time.gmtime(int(response.tx_time))
        ms = int((response.tx_time - int(response.tx_time)) * 1000)
        win32api.SetSystemTime(tm_year, tm_mon, tm_wday, tm_mday, tm_hour, tm_min, tm_sec, ms)
        time.sleep(60)