#!/usr/bin/env python

import sys, os, platform
os.environ['PYGLET_SHADOW_WINDOW']="0"

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

import pyglet
from cocos.director import director
from cocos.layer import ColorLayer
from scene import Scene

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
            eats = []
            for i in range(0, b.read_short()):
                hunter, prey = b.read_int(), b.read_int()
                eats.append((hunter, prey))
            # log.msg(("World Update|Eats", eats))
            while True:
                id = b.read_int()
                if id == 0: break
                x = b.read_int()
                y = b.read_int()
                size = b.read_short()
                color = (b.read_byte(), b.read_byte(), b.read_byte())
                flag = b.read_byte()
                virus = (flag & 1)
                agitated = (flag & 16)
                if (flag & 2):
                    skip = b.read_int()
                    b.skip(skip)
                elif (flag & 4):
                    skin_url = b.read_string8()
                else:
                    skin_url = ''
                name = b.read_string16()
                # log.msg(("World Update|Update", x, y, size, color, virus, agitated, skin_url, name))
            removals = []
            for i in range(0, b.read_int()):
                removals.append(b.read_int())
            # log.msg(("World Update|Removals", removals))
        elif opcode == 18:
            pass
        elif opcode == 49:
            ladder = []
            for i in range(0, b.read_int()):
                ladder.append((b.read_int(),b.read_string16()))
            # log.msg(("FFA Leaderboard", ladder))
        elif opcode == 64:
            left = b.read_double()
            top = b.read_double()
            right = b.read_double()
            bottom = b.read_double()
            # log.msg(("Game size area", left, top, right, bottom))
            if len(self.buffer.input) > 0:
                game_mode = b.read_int()
                # log.msg(("Game mode", game_mode))
                if len(self.buffer.input) > 0:
                    server_string = b.read_string16()
                    # log.msg(("Server string", server_string))
        else:
            raise Exception("UNHANDLED OPCODE", opcode)
        if len(self.buffer.input) > 0:
            raise Exception('Leftover payload!')

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

class AgarLayer(ColorLayer, pyglet.event.EventDispatcher):

    is_event_handler = True

    def __init__(self):
        screen = director.get_window_size()
        print ("!!!!",screen)
        super(AgarLayer, self).__init__(255, 255, 255, 255, screen[1], screen[1])

class PyAgar(object):
    title = "PyAgar"
    def __init__(self):
        director.set_show_FPS(False)
        director.init(fullscreen=True, caption=self.title, visible=True, resizable=True)

        self.gameScene = Scene()
        self.gameLayer = AgarLayer()
        self.gameScene.add(self.gameLayer)

        director.replace(self.gameScene)

        width = director.window.width
        height = director.window.height
        print (width, height)
        print (director.get_window_size())
        director.window.set_fullscreen(False)
        director.window.set_size(int(width * .75), int(height * .75))
        print (int(width * .75), int(height * .75))
        print (director.get_window_size())
        director.window.set_visible(True)
        # director.window.set_fullscreen(True)



if __name__ == '__main__':

    NAME = 'PyAgar'

    parser = argparse.ArgumentParser(description=NAME)
    parser.add_argument('--get-info', dest='getInfo', action='store_true', help='get server information')
    parser.add_argument('--region', dest='region', default='US-Atlanta', help='set server region')
    args = parser.parse_args()

    log.startLogging(sys.stdout)

    game = PyAgar()

    agent = Agent(reactor)

    if args.getInfo:
        d = agent.request('GET', 'http://m.agar.io/info', Headers({'User-Agent': [NAME]}), None)
        d.addCallback(cbResponse, printInfo)
        d.addBoth(cbShutdown)

    else:
        d = agent.request('POST', 'http://m.agar.io/', Headers({'User-Agent': [NAME]}), StringProducer('US-Atlanta'))
        d.addCallback(cbResponse, agarWS, True)

    reactor.run()
