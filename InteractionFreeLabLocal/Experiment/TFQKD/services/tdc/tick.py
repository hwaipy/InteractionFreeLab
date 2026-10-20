import time


class Tick:
    def __init__(self) -> None:
        self.mark = time.time()
        self.on = False

t = None

def getTick():
    global t
    if t == None:
        t = Tick()
    return t

def tick(msg):
    now = time.time()
    if getTick().on:
        print(f'TICK: {(now - getTick().mark) * 1000:.2f} ms ({msg})')
    getTick().mark = now

def turnOn():
    getTick().on = True

def turnOff():
    getTick().on = False