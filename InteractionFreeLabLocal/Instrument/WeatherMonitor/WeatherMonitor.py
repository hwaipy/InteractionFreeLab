import urllib.request
from interactionfreepy import IFWorker
from datetime import datetime
import time
import pytz


class WeatherFetcher:
    collection = 'Weathers'
    maxTry = 10

    def __init__(self, location, locationAbbr, lon, lat, tzshift):
        self.location = location
        self.locationAbbr = locationAbbr
        self.lon = lon
        self.lat = lat
        self.tzshift = tzshift
        self.url = "http://www.7timer.info/bin/astro.php?lon={}&lat={}&lang=zh-CN&ac=0&unit=metric&tzshift={}".format(self.lon, self.lat, self.tzshift)

    def fetchOnce(self):
        response = urllib.request.urlopen(self.url)
        status = response.status
        if status != 200:
            raise RuntimeError('Bad response: {}'.format(status))
        content = response.read()
        return content

    @classmethod
    def fetchAll(cls, stations):
        results = []
        for station in stations:
            result = {
                'Location': station[0],
                'LocationAbbr': station[1],
                'Lon': station[2],
                'Lat': station[3],
                'TZShift': station[4],
                'Status': 'Error',
            }
            wf = WeatherFetcher(*station)
            for i in range(WeatherFetcher.maxTry):
                try:
                    content = wf.fetchOnce()
                    result['Status'] = 'OK'
                    result['Content'] = content
                    results.append(result)
                    break
                except BaseException as e:
                    pass
            print('done  for  ', station[0], '      ', results[-1])
        results.append({
            'Location': 'BadLocation',
            'LocationAbbr': 'BL',
            'Lon': 0,
            'Lat': 0,
            'TZShift': 0,
            'Status': 'Error',
        })
        return results


if __name__ == '__main__':
    stations = [
        ['Ali', 'AL', 80.026, 32.325, 0],
        ['Delingha', 'DLH', 97.727, 37.379, 0],
        ['Nanshan', 'NS', 87.177, 43.475, 0],
        ['Beijing', 'BJ', 116.274, 40.047, 0],
        ['Lijiang', 'LJ', 100.029, 26.694, 0],
        ['Shanghai', 'SH', 121.542, 31.126, 0],
        ['Weihai', 'WeiH', 122.051, 37.534, 0],
        # ['Wuhan', 'WuH', 114.410, 30.430, 0],
        # ['Dalian', 'DL', 121.618, 38.932, 0],
        ['Russia (Beijing Time)', 'RUS', 37.596, 55.711, 4],
        ['Xiamen', 'XM', 118.1, 24.5, 0],
        ['Fuzhou', 'FZ', 119.3, 26.1, 0],
        ['Qingdao', 'QD', 120.3, 36.1, 0],
        ['Changchun', 'CC', 125.4, 43.9, 0],
        ['Jinan', 'JN', 117.000, 36.400, 0],
    ]
    worker = IFWorker('tcp://172.16.60.200:224')
    storage = worker.Storage

    while True:
        results = WeatherFetcher.fetchAll(stations)
        worker.Storage.append('Weathers', results, datetime.now(pytz.timezone('Asia/Shanghai')).isoformat())
        time.sleep(3600 * 4)



