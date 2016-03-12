#!/usr/bin/env python

import sys, os, platform

import argparse

import pygletreactor
pygletreactor.install()
from twisted.internet import reactor
from twisted.web.client import Agent, readBody
from twisted.web.http_headers import Headers

from twisted.python import log

import struct

from autobahn.twisted.websocket import WebSocketClientProtocol, \
    WebSocketClientFactory, connectWS

import pprint

import json

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

    def onOpen(self):
        log.msg('here 0')
        self.sendMessage(struct.pack("<BI",254,5), isBinary=True)
        self.sendMessage(struct.pack("<BI",255,2200049715), isBinary=True)
        log.msg(self.token)
        self.sendMessage(struct.pack("<B%ds" % len(self.token),80,self.token), isBinary=True)

    def onMessage(self, payload, isBinary):
        log.msg(struct.unpack("<B",payload[0]))

    def onClose(self, wasClean, code, reason):
        log.msg('here 2')

class AgarClientFactory(WebSocketClientFactory):

    def buildProtocol(self, addr):
        log.msg("here !!!")
        proto = AgarClientProtocol()
        proto.token = self.token
        proto.factory = self
        return proto

def connectWS(data):
    iphost, token = data.split()
    log.msg(token)
    ip, port = iphost.split(':')
    port = int(port)
    log.msg("ws://%s:%d" % (ip, port))
    factory = AgarClientFactory("ws://%s:%d" % (ip, port), headers={'Origin':'http://agar.io'})
    factory.token = token
    #factory.setSessionParameters(origin='http://agar.io')
    reactor.connectTCP(ip, port, factory)
    #connectWS(factory)

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
        d = agent.request('GET', 'http://m.agar.io/', Headers({'User-Agent': [NAME]}), None)
        d.addCallback(cbResponse, connectWS, True)

    reactor.run()
