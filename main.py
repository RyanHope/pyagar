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
        self.sendMessage(struct.pack("<BI",254,5), isBinary=True)
        self.sendMessage(struct.pack("<BI",255,2200049715), isBinary=True)
        self.sendMessage(struct.pack("<B%ds" % len(self.token),80,self.token), isBinary=True)

    def read_string(self, input):
        string = ''
        while True:
            if len(input) < 2:
                break

            charBytes = input[:2]
            input = input[2:]

            charCode = int.from_bytes(charBytes, byteorder='little')

            if charCode == 0:
                break

            char = chr(charCode)
            string += char
        return string

    def onMessage(self, payload, isBinary):
        opcode = struct.unpack("<B",payload[0])[0]
        datalen = len(payload[1:])
        print (opcode, datalen)
        if opcode == 18: # Reset all cells
            pass
        elif opcode == 64: # Game area size
            min_x, min_y, max_x, max_y = struct.unpack("<dddd", payload[1:33])
            log.msg((min_x, min_y, max_x, max_y))
            if datalen > 35:
                game_mode = struct.unpack("<I", payload[33:37])[0]
                log.msg(game_mode)
            if datalen > 36:
                offset = datalen-36
                server_version = struct.unpack("<%ds" % offset, payload[37:(37+offset)])[0].decode('utf-16')
                log.msg(server_version)
        elif opcode == 49: # FFA Leaderboard
            offset = 1
            cnt = struct.unpack("<I", payload[offset:(offset+4)])[0]
            offset += 4
            leaders = []
            for i in xrange(cnt):
                id = struct.unpack("<I", payload[offset:(offset+4)])[0]
                offset += 4
                print("leaders",i,id)
        elif opcode == 16: # World update
            pass
            # offset = 1
            # cnt_eats = struct.unpack("<H", payload[offset:(offset+2)])[0]
            # log.msg(cnt_eats)
            # offset += 2
            # eats = []
            # for _ in xrange(cnt_eats):
            #     eats.append((struct.unpack("<II", payload[offset:(offset+8)])))
            #     offset+=8
            # print eats
            # updates = []
            # while True:
            #     player_id = struct.unpack("<I", payload[offset:(offset+4)])[0]
            #     offset += 4
            #     if player_id !=0:
            #         x, y, size, r, g, b, flags = struct.unpack("<IIHBBBB", payload[offset:(offset+14)])
            #         print (x, y, size, r, g, b, flags)
            #         offset += 14
            #         if flags & 0x02:
            #             skip4 = struct.unpack("<I", payload[offset:(offset+4)])[0]
            #             print ("skip4",skip4)
            #             offset = offset + skip4 + 4
            #         #     offset += 4
            #         # elif flags & 0x04:
            #         #     offset += 8
            #         # elif flags & 0x08:
            #         #     offset += 16
            #         name = struct.unpack("<32s", payload[offset:(offset+32)])[0]
            #         print name.decode('utf-16')



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
