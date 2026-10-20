from interactionfreepy import IFWorker

# ip = '10.1.1.1'
ip = '172.16.60.200'  # 实验室外
# ip = '192.168.25.5'
# ip = 'interactionfree.cn'  # 研究院外
worker = IFWorker(endpoint=f'tcp://{ip}:224')
worker_timeoutset = IFWorker(endpoint=f'tcp://{ip}:224', timeout=1)


