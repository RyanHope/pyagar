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
from pyglet import font, text, resource

from cocos.director import director
from cocos.layer import ColorLayer
from cocos.text import Label
from cocos.batch import BatchNode
from cocos.sprite import *

from scene import Scene
from primitives import Circle, Line
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
        b.write_uint(5)
        b.flush_protocol(self)

        b.write_byte(255)
        b.write_uint(2200049715)
        b.flush_protocol(self)

        b.write_byte(80)
        b.write_string(self.token)
        b.flush_protocol(self)

        self.player.reset()
        self.player.world.reset()
        self.player.nick = "PuffTheMagic"

        self.send_respawn()

    def send_respawn(self):
        b = self.buffer
        b.write_byte(0)
        b.write_string(self.player.nick.encode('utf-16'))
        b.flush_protocol(self)

    def send_target(self, x, y, cid=0):
        b = self.buffer
        b.write_byte(16)
        b.write_int(x)
        b.write_int(y)
        b.write_uint(cid)
        b.flush_protocol(self)

    def send_split(self):
        b = self.buffer
        b.write_byte(17)
        b.flush_protocol(self)

    def send_shoot(self):
        b = self.buffer
        b.write_byte(21)
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
            self.game.gameLayer.recalculate()
            if self.game.gameLayer.names_batch in self.game.gameLayer.get_children():
                self.game.gameLayer.remove(self.game.gameLayer.names_batch)
            for s in self.game.gameLayer.sprites:
                if s in self.game.gameLayer.get_children():
                    self.game.gameLayer.remove(s)
            names_batch = BatchNode()
            sprites = []
            for cell in sorted(self.player.world.cells.values(), reverse=True):
                pos = self.game.gameLayer.world_to_screen_pos(cell.pos)
                w = self.game.gameLayer.world_to_screen_size(cell.size)
                #circles.append(Circle(pos.x, pos.y, width=w, color=(cell.color[0],cell.color[1],cell.color[2],1)))
                img = 'cell.png'
                if cell.is_virus:
                    img = 'virus.png'
                elif cell.is_agitated:
                    img = 'agitated.png'
                s = Sprite(resource.image(img),position=pos,color=cell.color2,scale=w/425.)
                self.game.gameLayer.add(s)
                sprites.append(s)
                text.Label(cell.name, font_size=14, x=pos.x, y=pos.y, color=(32, 32, 32, 255),
                       anchor_x='center', anchor_y='center', batch=names_batch.batch)
            self.game.gameLayer.sprites = sprites
            self.game.gameLayer.names_batch = names_batch
            self.game.gameLayer.add(self.game.gameLayer.names_batch)
            #self.game.gameLayer.circles = circles
            self.game.gameLayer.send_mouse()
            # self.game.gameLayer.init()
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
            leaders_batch = BatchNode()
            leaderboard_names = []
            for i in range(0, b.read_uint()):
                id, name = b.read_uint(), b.read_string16()
                diff = self.game.gameLayer.screen[0] - int(self.game.gameLayer.screen[0]*.99)
                text.Label("%d. %s" % (i+1,name), font_size=14, x=self.game.gameLayer.screen[0]-diff, y=self.game.gameLayer.screen[1]-diff-i*17, color=(32, 32, 32, 255),
                       anchor_x='right', anchor_y='center', batch=leaders_batch.batch)
                leaderboard_names.append((id, name))
            if self.game.gameLayer.leaders_batch in self.game.gameLayer.get_children():
                self.game.gameLayer.remove(self.game.gameLayer.leaders_batch)
            self.game.gameLayer.leaders_batch = leaders_batch
            self.game.gameLayer.add(self.game.gameLayer.leaders_batch)
            #self.subscriber.on_leaderboard_names(leaderboard=leaderboard_names)
            self.player.world.leaderboard_names = leaderboard_names
            # self.game.gameLayer.leaders = []
            # offset = 0
            # for l in self.game.gameLayer.leaders:
            #     self.game.gameLayer.remove(l)
            # for id,name in leaderboard_names:
            #     self.game.gameLayer.leaders.append(Label(name, position=(800,800+offset), font_name='', font_size=14, color=(0, 0, 0, 255), anchor_x='right', anchor_y='center'))
            #     offset -= 25
            # for l in self.game.gameLayer.leaders:
            #     self.game.gameLayer.add(l)

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
        self.game.gameLayer.proto = proto
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
        self.sprites = []
        # self.leaders = []
        self.win_size = Vec(self.screen[0], self.screen[1])
        self.screen_center = self.win_size / 2
        self.screen_scale = 1
        self.world_center = Vec(0, 0)
        self.mouse_pos = Vec(0, 0)
        self.movement_delta = Vec()
        self.names_batch = BatchNode()
        self.leaders_batch = BatchNode()
        # self.border = []

    # def init(self):
    #     wl, wt = self.world_to_screen_pos(self.proto.player.world.top_left)
    #     wr, wb = self.world_to_screen_pos(self.proto.player.world.bottom_right)
    #     print(wl,wt,wr,wb)
    #     border = []
    #     border.append(Line((wl,wt),(wr,wt),stroke=5))
    #     border.append(Line((wl,wb),(wr,wb),stroke=5))
    #     border.append(Line((wl,wt),(wl,wb),stroke=5))
    #     border.append(Line((wr,wt),(wr,wb),stroke=5))
    #     self.border = border

    def draw(self):
        super(AgarLayer, self).draw()
        for c in self.circles:
            c.render()
        # for b in self.border:
        #     b.render()

    def recalculate(self):
        #alloc = self.drawing_area.get_allocation()
        #self.win_size.set(alloc.width, alloc.height)
        #self.screen_center = self.win_size / 2
        if self.proto.player:  # any client is focused
            #print("HERE 1")
            window_scale = max(self.win_size.x / self.screen[0], self.win_size.y / self.screen[1])
            self.screen_scale = self.proto.player.scale * window_scale
            self.world_center = self.proto.player.center
            self.world = self.proto.player.world
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

    def screen_to_world_pos(self, screen_pos):
        return (screen_pos - self.screen_center) \
            .idiv(self.screen_scale).iadd(self.world_center)

    def on_mouse_motion(self, x, y, dx, dy):
        x, y = director.get_virtual_coordinates(x, y)
        self.mouse_pos = Vec(x, y)
        pos_world = self.screen_to_world_pos(self.mouse_pos)
        self.movement_delta = pos_world - self.proto.player.center
        self.send_mouse()

    def send_mouse(self):
        target = self.proto.player.center + self.movement_delta
        self.proto.send_target(*target)

    def on_key_press(self, symbol, modifiers):
        if symbol == key.Q and (modifiers & key.MOD_ACCEL):
            reactor.callFromThread(reactor.stop)
            return True
        elif symbol == key.W :
            self.proto.send_shoot()
            return True
        elif symbol == key.R :
            self.proto.send_respawn()
            return True
        elif symbol == key.SPACE:
            self.proto.send_split()
            return True

class PyAgar(object):
    title = "PyAgar"
    def __init__(self):

        pyglet.resource.path.append('resources')
        pyglet.resource.reindex()

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

        director.window.set_fullscreen(True)
        director.window.set_fullscreen(False)
        director.window.set_visible(True)

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
        d = agent.request('POST', 'http://m.agar.io/', Headers({'User-Agent': [NAME]}), StringProducer('EU-London'))
        d.addCallback(cbResponse, lambda x: agarWS(x, game), True)

    reactor.run()
