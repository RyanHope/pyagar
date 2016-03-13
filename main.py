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
import time
import math

from autobahn.twisted.websocket import WebSocketClientProtocol, \
    WebSocketClientFactory, connectWS

import pprint

import json

import pyglet
from pyglet.window import key
from cocos.director import director
from cocos.layer import ColorLayer

from scene import Scene
from primitives import Circle
from handler import Handler

from vec import Vec
from world import Player

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

    def __init__(self, *args, **kwargs):
        WebSocketClientProtocol.__init__(self, *args, **kwargs)
        self.player = Player()
        self.ingame = False

    def onConnect(self, response):
        log.msg("Connected to Server: {}".format(response.peer))
        self.buffer = Buffer()

    def onOpen(self):
        b = self.buffer

        b.write_byte(254)
        b.write_int(5)
        b.flush_protocol(self)

        b.write_byte(255)
        b.write_int(2200049715)
        b.flush_protocol(self)

        b.write_byte(80)
        b.write_string(self.token)
        b.flush_protocol(self)

        self.player.reset()
        self.player.world.reset()
        self.player.nick = "PuffTheMagic"

        b.write_byte(0)
        b.write_string(self.player.nick)
        b.flush_protocol(self)

    def onMessage(self, payload, isBinary):
        self.buffer.fill(payload)
        packet = self.buffer.read_byte()
        self.parse_packet(packet)

    def parse_packet(self, opcode):
        #print ("===========",opcode,"===========")
        b = self.buffer
        if opcode == 16:
            for i in range(0, b.read_short()):
                hunter, prey = b.read_uint(), b.read_uint()
                if prey in self.player.own_ids:
                    if len(self.player.own_ids) <= 1:
                        pass#self.subscriber.on_death()
                    self.player.own_ids.remove(prey)
                if prey in self.player.world.cells:
                    #self.subscriber.on_cell_removed(cid=prey)
                    del self.player.world.cells[prey]
            while True:
                id = b.read_uint()
                if id == 0: break
                x = b.read_int()
                y = b.read_int()
                size = b.read_short()
                color = (b.read_byte(), b.read_byte(), b.read_byte())
                flag = b.read_byte()
                virus = (flag & 1)
                agitated = (flag & 16)
                if (flag & 2):
                    skip = b.read_uint()
                    b.skip(skip)
                elif (flag & 4):
                    skin_url = b.read_string8()
                else:
                    skin_url = ''
                name = b.read_string16()
                # self.subscriber.on_cell_info(cid=id, x=cx, y=cy, size=csize, name=cname, color=color, is_virus=is_virus, is_agitated=is_agitated)
                if id not in self.player.world.cells:
                    self.player.world.create_cell(id)
                self.player.world.cells[id].update(cid=id, x=x, y=y, size=size, name=name, color=color, is_virus=virus, is_agitated=agitated)
            cells = self.player.world.cells
            for i in range(0, b.read_uint()):
                id = b.read_uint()
                if id in cells:
                    #self.subscriber.on_cell_removed(cid=id)
                    del cells[id]
                    if id in self.player.own_ids:
                        self.player.own_ids.remove(id)
            if self.player.is_alive:
                self.player.cells_changed()
            circles = []
            self.game.gameLayer.recalculate()
            for cell in sorted(self.player.world.cells.values(), reverse=True):
                pos = self.game.gameLayer.world_to_screen_pos(cell.pos)
                w = self.game.gameLayer.world_to_screen_size(cell.size)
                #print((cell.pos.x,cell.pos.y),(pos.x,pos.y),cell.size,w)
                circles.append(Circle(pos.x, pos.y, width=w, color=(cell.color[0],cell.color[1],cell.color[2],1)))
            self.game.gameLayer.circles = circles
        elif opcode == 18:
            #self.subscriber.on_clear_cells()
            self.player.world.cells.clear()
            self.player.own_ids.clear()
            self.player.cells_changed()
        elif opcode == 32:
            id = b.read_uint()
            if not self.player.is_alive:  # respawned
                self.player.own_ids.clear()
                #self.subscriber.on_respawn()
            # server sends empty name, assumes we set it here
            if id not in self.player.world.cells:
                self.player.world.create_cell(id)
            # self.world.cells[cid].name = self.player.nick
            self.player.own_ids.add(id)
            self.player.cells_changed()
            #self.subscriber.on_own_id(cid=id)
        elif opcode == 49:
            leaderboard_names = []
            for i in range(0, b.read_uint()):
                id, name = b.read_uint(), b.read_string16()
                leaderboard_names.append((id, name))
            #self.subscriber.on_leaderboard_names(leaderboard=leaderboard_names)
            self.player.world.leaderboard_names = leaderboard_names
        elif opcode == 64:
            left = b.read_double()
            top = b.read_double()
            right = b.read_double()
            bottom = b.read_double()
            #self.subscriber.on_world_rect(left=left, top=top, right=right, bottom=bottom)
            self.player.world.top_left = Vec(top, left)
            self.player.world.bottom_right = Vec(bottom, right)
            #print ("#################",self.player.world.top_left.x,self.player.world.top_left.y)
            #print ("#################",self.player.world.bottom_right.x,self.player.world.bottom_right.y)
            if len(self.buffer.input) > 0:
                game_mode = b.read_uint()
                server_string = b.read_string16()
                #self.subscriber.on_server_version(number=game_mode, text=server_version)
        else:
            raise Exception("UNHANDLED OPCODE!", opcode)
        if len(self.buffer.input) > 0:
            raise Exception('LEFTOVER PAYLOAD!')

    def onClose(self, wasClean, code, reason):
        pass

class AgarClientFactory(WebSocketClientFactory):

    def buildProtocol(self, addr):
        proto = AgarClientProtocol()
        proto.token = self.token
        proto.game = self.game
        self.game.gameLayer.player = proto.player
        proto.factory = self
        return proto

def agarWS(data, game):
    iphost, token = data.split()
    log.msg(token)
    ip, port = iphost.split(':')
    port = int(port)
    log.msg("ws://%s:%d" % (ip, port))
    factory = AgarClientFactory("ws://%s:%d" % (ip, port), headers={'Origin':'http://agar.io'})
    factory.token = token
    factory.game = game
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
        self.screen = director.get_window_size()
        super(AgarLayer, self).__init__(255, 255, 255, 255, self.screen[0], self.screen[1])
        #self.position = ((self.screen[0]-self.screen[1])/2,0)
        self.circles = []
        self.win_size = Vec(self.screen[0], self.screen[1])
        self.screen_center = self.win_size / 2
        self.screen_scale = 1
        self.world_center = Vec(0, 0)

    def draw(self):
       super(AgarLayer, self).draw()
       for c in self.circles:
           c.render()

    def recalculate(self):
        #alloc = self.drawing_area.get_allocation()
        #self.win_size.set(alloc.width, alloc.height)
        #self.screen_center = self.win_size / 2
        if self.player:  # any client is focused
            #print("HERE 1")
            window_scale = max(self.win_size.x / self.screen[0], self.win_size.y / self.screen[1])
            self.screen_scale = self.player.scale * window_scale
            self.world_center = self.player.center
            self.world = self.player.world
            #print (self.world.size.x,self.world.size.y,self.world_center.x,self.world_center.y)
        elif self.world.size:
            #print("HERE 2")
            self.screen_scale = min(self.win_size.x / self.world.size.x,
                                    self.win_size.y / self.world.size.y)
            self.world_center = self.world.center
        else:
            #print("HERE 3")
            # happens when the window gets drawn before the world got updated
            self.screen_scale = 1
            self.world_center = Vec(0, 0)

    def world_to_screen_pos(self, world_pos):
        return (world_pos - self.world_center) \
            .imul(self.screen_scale).iadd(self.screen_center)

    def world_to_screen_size(self, world_size):
        return world_size * self.screen_scale

    def on_key_press( self, symbol, modifiers):
        if symbol == key.Q and (modifiers & key.MOD_ACCEL):
            reactor.callFromThread(reactor.stop)
            return True

class PyAgar(object):
    title = "PyAgar"
    def __init__(self):
        director.set_show_FPS(False)
        w = director.init(fullscreen=True, caption=self.title, visible=True, resizable=True)

        width = director.window.width
        height = director.window.height
        wnew, hnew = int(width * .75), int(height * .75)
        director.window.set_fullscreen(False)
        director.window.set_size(wnew, hnew)
        w.set_location((width-wnew)/2, (height-hnew)/2)

        director.window.pop_handlers()
        director.window.push_handlers(Handler())

        self.gameScene = Scene()
        self.gameLayer = AgarLayer()
        self.gameScene.add(self.gameLayer)

        director.replace(self.gameScene)

        director.window.set_visible(True)
        # director.window.set_fullscreen(True)
        # director.window.set_fullscreen(False)

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
        d.addCallback(cbResponse, lambda x: agarWS(x, game), True)

    reactor.run()
