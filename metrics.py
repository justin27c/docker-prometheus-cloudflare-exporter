#!/usr/bin/env python
from prometheus_client import start_http_server, Metric, REGISTRY
import json
import requests
import sys
import time
import os

AUTH_EMAIL = os.environ.get('AUTH_EMAIL')
AUTH_KEY = os.environ.get('AUTH_KEY')
SERVICE_PORT = int(os.environ.get('SERVICE_PORT'))
ZONE = os.environ.get('ZONE')


class MetricsCollector(object):
  def __init__(self):
    self.processargs()

    self.zone = ZONE
    self.endpoint = 'https://api.cloudflare.com/client/v4/'
    self.headers = {'X-Auth-Key': AUTH_KEY, 'X-Auth-Email': AUTH_EMAIL, 'Content-Type': 'application/json'}
    self.zoneid = self.getzoneid()
    print('Started scrape service for zone *%s* using key [%s...]' % (self.zone, AUTH_KEY[0:6]))
    print('Metrics are available at http://thishost:%s/' % SERVICE_PORT)


  # TODO: realy process here, instead of a mere check for existence.
  def processargs(self):
    required_vars = {'AUTH_EMAIL', 'AUTH_KEY', 'SERVICE_PORT', 'ZONE'}
    fail = False
    for key in required_vars:
        if os.environ.get(key) is None:
            print('Missing value for %s' % key)
            fail = True
    if fail:
        sys.exit()


  def getdatafromcf(self, url):
    return json.loads(requests.get(url, headers=self.headers).content.decode('UTF-8'))


  def getzoneid(self):
    r = self.getdatafromcf(url=self.endpoint+'zones?name='+self.zone)
    return r['result'][0]['id']


  def collect(self):
    response = self.getdatafromcf(url=self.endpoint+'zones/'+self.zoneid+'/analytics/colos?since=-30&continuous=true')
    if not response['success']:
        print('Failed to get information from cloudflare')
        return


    for sample in response['result']:
        """
        Since we're about to fetch 30 minutes worth of data, settle with the
        last sample and process only that. Please note that this means a serious
        5 minutes delay in stats.
        """
        serie = sample['timeseries'][-1]
        window = serie['since'] + ' ' + serie['until']
        metric = Metric('cloudflare_pop', 'Cloudflare global Point of Presence stats, window '+window, 'summary')
        metric.add_sample('cloudflare_pop', value=1, labels={'colo_id': sample['colo_id']})
        yield metric

        cachedr = serie['requests']['cached']
        uncachedr = serie['requests']['uncached']
        metric = Metric('cloudflare_pop_requests', 'Incoming requests', 'gauge')
        metric.add_sample('cloudflare_pop_requests', value=cachedr, labels={'colo_id': sample['colo_id'], 'requests_type': 'cached'})
        metric.add_sample('cloudflare_pop_requests', value=uncachedr, labels={'colo_id': sample['colo_id'], 'requests_type': 'uncached'})
        yield metric

        cachedbw = serie['bandwidth']['cached']
        uncachedbw = serie['bandwidth']['uncached']
        metric = Metric('cloudflare_pop_bandwidth', 'Bandwidth used in bytes', 'gauge')
        metric.add_sample('cloudflare_pop_bandwidth', value=cachedbw, labels={'colo_id': sample['colo_id'], 'bandwidth_type': 'cached'})
        metric.add_sample('cloudflare_pop_bandwidth', value=uncachedbw, labels={'colo_id': sample['colo_id'], 'bandwidth_type': 'uncached'})
        yield metric

        metric = Metric('cloudflare_pop_threats', 'Threats', 'gauge')
        threats = serie['threats']['all']
        metric.add_sample('cloudflare_pop_threats', value=threats, labels={'colo_id': sample['colo_id']})

        metric = Metric('cloudflare_pop_http_response', 'HTTP responses', 'gauge')
        for http_status, value in serie['requests']['http_status'].items():
            metric.add_sample('cloudflare_pop_http_response', value=value, labels={'colo_id': sample['colo_id'], 'http_status': http_status})
        yield metric

        metric = Metric('cloudflare_pop_threat_type', 'Threat types seen', 'gauge')
        for threat, value in serie['threats']['type'].items():
            metric.add_sample('cloudflare_pop_threat_type', value=value, labels={'colo_id': sample['colo_id'], 'threat': threat})
        yield metric


if __name__ == '__main__':
  start_http_server(SERVICE_PORT)
  REGISTRY.register(MetricsCollector())

  while True: time.sleep(1)
