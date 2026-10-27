"""Read live delays and measure RPC/sample age from a separate Python process.

python RealTimeTDCDelayClient.py --endpoint tcp://127.0.0.1:2240 --seconds 10
Use the TDC server's LAN IP instead of 127.0.0.1 from another machine.
Sample ages use wall clocks; synchronize both machines before comparing ages.
"""
import argparse
import json
import statistics
import time

from interactionfreepy import IFWorker


def distribution(values):
  if not values:
    return None
  ordered = sorted(values)
  position = (len(ordered) - 1) * .95
  lower = int(position)
  upper = min(lower + 1, len(ordered) - 1)
  return {
    'count': len(values), 'mean': statistics.mean(values),
    'median': statistics.median(values),
    'p95': ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower),
    'max': ordered[-1],
  }


def run(endpoint, service, seconds, poll, timeout):
  worker = IFWorker(endpoint, timeout=timeout)
  remote = worker.blockingInvoker(service, timeout=timeout)
  rpcTimes, offerAges, fetchAges, processingTimes = [], [], [], []
  sequences = set()
  missed = 0
  previous = None
  startedAt = time.time()
  deadline = time.perf_counter() + seconds
  try:
    while time.perf_counter() < deadline:
      begin = time.perf_counter()
      rows = remote.getRecent(1, delayOnly=True)
      receivedAt = time.time()
      elapsed = (time.perf_counter() - begin) * 1000
      rpcTimes.append(elapsed)
      if rows:
        row = rows[-1]
        sequence = row['Sequence']
        if row['OfferTime'] >= startedAt and previous is not None and sequence < previous:
          raise RuntimeError('RealTimeTDC restarted during measurement')
        if row['OfferTime'] >= startedAt and sequence not in sequences:
          if previous is not None:
            missed += sequence - previous - 1
          previous = sequence
          sequences.add(sequence)
          offerAge = (receivedAt - row['OfferTime']) * 1000
          fetchAge = (receivedAt - row['FetchTime']) * 1000
          offerAges.append(offerAge)
          fetchAges.append(fetchAge)
          if row['ProcessingTime'] is not None:
            processingTimes.append(row['ProcessingTime'] * 1000)
          print(json.dumps({
            'sequence': sequence, 'delay_ps': row['Delays'],
            'rpc_ms': elapsed, 'offer_to_client_ms': offerAge,
            'fetch_to_client_ms': fetchAge,
          }), flush=True)
      time.sleep(max(0, min(poll, deadline - time.perf_counter())))
  finally:
    worker.close()
  summary = {
    'samples': len(sequences), 'missed_between_received_samples': missed,
    'rpc_ms': distribution(rpcTimes),
    'offer_to_client_ms': distribution(offerAges),
    'fetch_to_client_ms': distribution(fetchAges),
    'processing_ms': distribution(processingTimes),
  }
  print(json.dumps({'summary': summary}), flush=True)
  return summary


if __name__ == '__main__':
  parser = argparse.ArgumentParser(description=__doc__)
  parser.add_argument('--endpoint', default='tcp://127.0.0.1:2240')
  parser.add_argument('--service', default='RealTimeTDC')
  parser.add_argument('--seconds', type=float, default=10)
  parser.add_argument('--poll', type=float, default=.01)
  parser.add_argument('--timeout', type=float, default=5)
  args = parser.parse_args()
  if min(args.seconds, args.poll, args.timeout) <= 0:
    parser.error('--seconds, --poll and --timeout must be positive')
  run(args.endpoint, args.service, args.seconds, args.poll, args.timeout)
