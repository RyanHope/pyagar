#!/usr/bin/env python

import sys, os, platform

import argparse

import pygletreactor
pygletreactor.install()
from twisted.internet import reactor
from twisted.web.client import Agent, readBody
from twisted.web.http_headers import Headers
from zope.interface import implements

from twisted.internet.defer import succeed
from twisted.web.iweb import IBodyProducer

from twisted.python import log

import struct
import urllib

from autobahn.twisted.websocket import WebSocketClientProtocol, \
    WebSocketClientFactory, connectWS

import pprint

import json

from buffer import Buffer

def cbBody(body, callback):
    callback(body)

def cbResponse(response, callback, printHeaders=False):
    if printHeaders:
        log.msg(pprint.pformat(list(response.headers.getAllRawHeaders())))
    d = readBody(response)
    d.addCallback(cbBody, callback)
    return d

def cbShutdown(ignored):
    reactor.stop()

def printInfo(data):
    pprint.PrettyPrinter(indent=2).pprint(json.loads(data))

class AgarClientProtocol(WebSocketClientProtocol):

    def onConnect(self, response):
        log.msg("Connected to Server: {}".format(response.peer))
        self.buffer = Buffer()

    def onOpen(self):
        self.sendMessage(struct.pack("<BI",254,5), isBinary=True)
        self.sendMessage(struct.pack("<BI",255,2200049715), isBinary=True)
        self.sendMessage(struct.pack("<B%ds" % len(self.token),80,self.token), isBinary=True)

    def onMessage(self, payload, isBinary):
        self.buffer.fill(payload)
        packet = self.buffer.read_byte()
        self.parse_packet(packet)

    def parse_packet(self, opcode):
        b = self.buffer
        if opcode == 16:
            pass
        elif opcode == 18:
            pass
        elif opcode == 49:
            ladder = []
            amount = b.read_int()
            for i in range(0, amount):
                player_id = b.read_int()
                ladder.append((player_id,b.read_string()))
        elif opcode == 64:
            min_x = b.read_double()
            min_y = b.read_double()
            max_x = b.read_double()
            max_y = b.read_double()
        else:
            print opcode

    def onClose(self, wasClean, code, reason):
        log.msg('here 2')

class AgarClientFactory(WebSocketClientFactory):

    def buildProtocol(self, addr):
        log.msg("here !!!")
        proto = AgarClientProtocol()
        proto.token = self.token
        proto.factory = self
        return proto

def agarWS(data):
    iphost, token = data.split()
    log.msg(token)
    ip, port = iphost.split(':')
    port = int(port)
    log.msg("ws://%s:%d" % (ip, port))
    factory = AgarClientFactory("ws://%s:%d" % (ip, port), headers={'Origin':'http://agar.io'})
    factory.token = token
    connectWS(factory)

class StringProducer(object):
    implements(IBodyProducer)

    def __init__(self, body):
        self.body = body
        self.length = len(body)

    def startProducing(self, consumer):
        consumer.write(self.body)
        return succeed(None)

    def pauseProducing(self):
        pass

    def stopProducing(self):
        pass

if __name__ == '__main__':

    NAME = 'PyAgar'

    parser = argparse.ArgumentParser(description=NAME)
    parser.add_argument('--get-info', dest='getInfo', action='store_true', help='get server information')
    parser.add_argument('--region', dest='region', default='US-Atlanta', help='set server region')
    args = parser.parse_args()

    log.startLogging(sys.stdout)

    agent = Agent(reactor)

    if args.getInfo:
        d = agent.request('GET', 'http://m.agar.io/info', Headers({'User-Agent': [NAME]}), None)
        d.addCallback(cbResponse, printInfo)
        d.addBoth(cbShutdown)

    else:
        d = agent.request('POST', 'http://m.agar.io/', Headers({'User-Agent': [NAME]}), StringProducer('US-Atlanta'))
        d.addCallback(cbResponse, agarWS, True)

    reactor.run()
