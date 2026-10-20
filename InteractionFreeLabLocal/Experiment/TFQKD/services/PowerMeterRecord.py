if __name__ == '__main__':
    from interactionfreepy import IFWorker, IFLoop
    import math
    import time
    from datetime import datetime

    worker = IFWorker('tcp://192.168.25.5:1061')

    while True:
        result = {}
        try:
            result['Alice'] = worker.TF_PowerMeter_Alice.readPower()
        except BaseException as e:
            result['Alice'] = [math.nan, math.nan]
        try:
            result['Bob'] = worker.TF_PowerMeter_Bob.readPower()
        except BaseException as e:
            result['Bob'] = [math.nan, math.nan]
        try:
            result['Senders'] = worker.TF_PowerMeter_Senders.readPower()
        except BaseException as e:
            result['Senders'] = [math.nan, math.nan]
        
        worker.Storage.append('PowerMeterRecord', result, fetchTime=time.time())
        print(datetime.now(), result)
        time.sleep(1)
