#!/usr/bin/env python

from __future__ import division

import re

import sys, os, platform
os.environ['PYGLET_SHADOW_WINDOW']="0"

abspath = os.path.abspath(__file__)
dname = os.path.dirname(abspath)
os.chdir(dname)

import argparse

import pygletreactor
pygletreactor.install()
from twisted.internet import reactor
from twisted.web.client import Agent, readBody
from twisted.web.http_headers import Headers
from zope.interface import implements

from twisted.internet.defer import succeed
from twisted.web.iweb import IBodyProducer

# from twisted.python import log

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
from pyglet import font, text, resource, clock
#from pyglet.image.codecs.png import PNGImageDecoder

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
        print pprint.pformat(list(response.headers.getAllRawHeaders()))
    d = readBody(response)
    d.addCallback(cbBody, callback)
    return d

def cbShutdown(ignored):
    reactor.stop()

def printInfo(data):
    pprint.PrettyPrinter(indent=2).pprint(json.loads(data))

class AgarClientProtocol(WebSocketClientProtocol):

    def __init__(self, spectate, *args, **kwargs):
        WebSocketClientProtocol.__init__(self, *args, **kwargs)
        self.player = Player()
        self.ingame = False
        self.re_pattern = re.compile(u'[^\u0000-\uD7FF\uE000-\uFFFF]', re.UNICODE)
        self.spectate = spectate

    def onConnect(self, response):
        self.buffer = Buffer()

    def onOpen(self):
        b = self.buffer

        b.write_byte(254)
        b.write_uint(5)
        b.flush_protocol(self)

        b.write_byte(255)
        b.write_uint(154669603)
        b.flush_protocol(self)

        b.write_byte(80)
        b.write_string(self.token)
        b.flush_protocol(self)

        self.player.reset()
        self.player.world.reset()
        self.player.nick = "PuffTheMagic"

        if self.spectate:
            self.send_spectate()
        else:
            self.send_respawn()

    def send_respawn(self):
        self.spectate = False
        b = self.buffer
        b.write_byte(0)
        b.write_string(self.player.nick.encode('utf-16le'))
        b.flush_protocol(self)

    def send_spectate(self):
        self.spectate = True
        b = self.buffer
        b.write_byte(1)
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

    def setInGame(self, opcode):
        if opcode in [16,17,32,49,50,64]:
            self.ingame =True

    def parse_packet(self, opcode):
        #print ("===========",opcode,"===========")
        b = self.buffer
        self.setInGame(opcode)

        if opcode == 16:
            preys = []
            for i in range(0, b.read_short()):
                hunter, prey = b.read_uint(), b.read_uint()
                preys.append(prey)
                if prey in self.player.own_ids:
                    if len(self.player.own_ids) <= 1:
                        #self.send_spectate()
                        print "DEAD!!!!!!!!!!!!!!!!"
                        #self.subscriber.on_death()
                    self.player.own_ids.remove(prey)
                if prey in self.player.world.cells:
                    #self.subscriber.on_cell_removed(cid=prey)
                    del self.player.world.cells[prey]
                    self.game.gameLayer.sprite_batch.remove(self.game.gameLayer.sprites[prey].img)
                    self.game.gameLayer.sprite_pool.append(self.game.gameLayer.sprites[prey])
                    del self.game.gameLayer.sprites[prey]
                    if prey in self.game.gameLayer.names:
                        self.game.gameLayer.remove(self.game.gameLayer.names[prey])
                        self.game.gameLayer.name_pool.append(self.game.gameLayer.names[prey])
                        del self.game.gameLayer.names[prey]
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
                #name = self.re_pattern.sub(u'\uFFFD', name)
                # self.subscriber.on_cell_info(cid=id, x=cx, y=cy, size=csize, name=cname, color=color, is_virus=is_virus, is_agitated=is_agitated)
                if id not in self.player.world.cells:
                    self.player.world.create_cell(id)
                    self.game.gameLayer.sprites[id] = self.game.gameLayer.sprite_pool.pop()
                    self.game.gameLayer.sprites[id].cid = id
                    self.game.gameLayer.sprites[id].set_type(virus=virus)
                    self.game.gameLayer.sprites[id].set_name(name)
                    self.game.gameLayer.sprite_batch.add(self.game.gameLayer.sprites[id].img)
                    if name != '':
                        self.game.gameLayer.names[id] = self.game.gameLayer.name_pool.pop()
                        self.game.gameLayer.names[id].element.text = name
                        self.game.gameLayer.add(self.game.gameLayer.names[id],z=1000)
                self.player.world.cells[id].update(cid=id, x=x, y=y, size=size, name=name, color=color, is_virus=virus, is_agitated=agitated)
            for i in range(0, b.read_uint()):
                id = b.read_uint()
                if id in self.player.world.cells:
                    #self.subscriber.on_cell_removed(cid=id)
                    del self.player.world.cells[id]
                    if id in self.player.own_ids:
                        self.player.own_ids.remove(id)
                    self.game.gameLayer.sprite_batch.remove(self.game.gameLayer.sprites[id].img)
                    self.game.gameLayer.sprite_pool.append(self.game.gameLayer.sprites[id])
                    del self.game.gameLayer.sprites[id]
                    if id in self.game.gameLayer.names:
                        self.game.gameLayer.remove(self.game.gameLayer.names[id])
                        self.game.gameLayer.name_pool.append(self.game.gameLayer.names[id])
                        del self.game.gameLayer.names[id]
            if self.player.is_alive:
                self.player.cells_changed()
            self.game.gameLayer.recalculate()
            # names_batch = BatchNode()
            for id in self.player.world.cells:
                pos = self.game.gameLayer.world_to_screen_pos(self.player.world.cells[id].pos)
                self.game.gameLayer.sprites[id].size = int(self.game.gameLayer.world_to_screen_size(self.player.world.cells[id].size)*2)
                if self.game.gameLayer.sprites[id].size == 0:
                    pass
                else:
                    #print ("SHIT!!", id, self.player.world.cells[id].name, id in preys)
                    self.game.gameLayer.sprites[id].img.color = self.player.world.cells[id].color2
                    self.game.gameLayer.sprites[id].set_position(pos)
                    self.game.gameLayer.sprites[id].set_scale(self.game.gameLayer.sprites[id].size/425.)
                    if id in self.game.gameLayer.names:
                        self.game.gameLayer.names[id].position = pos
                        ns = 2+int(self.game.gameLayer.sprites[id].size/(len(self.player.world.cells[id].name)+1))
                        if ns < 6: ns = 6
                        d = ns - self.game.gameLayer.names[id].element._get_font_size()
                        if d > 1 or d < -1:
                            self.game.gameLayer.names[id].element._set_font_size(ns)


                # sz = self.player.world.cells[id].size/16
                # if self.player.world.cells[id].name != '' and sz > 6:
                #     text.Label(self.player.world.cells[id].name, font_size=sz, font_name='DejaVu Mono', x=pos.x, y=pos.y, color=(255, 255, 255, 255), anchor_x='center', anchor_y='center', batch=names_batch.batch)
            # if self.game.gameLayer.names_batch in self.game.gameLayer.get_children():
            #     self.game.gameLayer.remove(self.game.gameLayer.names_batch)
            # self.game.gameLayer.names_batch = names_batch
            # self.game.gameLayer.add(self.game.gameLayer.names_batch)
            maxmass = self.game.gameLayer.score
            for id in self.player.own_ids:
                if self.player.world.cells[id].mass > maxmass:
                    maxmass = self.player.world.cells[id].mass
            self.game.gameLayer.score = maxmass
            if self.game.gameLayer.scoreSprite in self.game.gameLayer.get_children():
                self.game.gameLayer.remove(self.game.gameLayer.scoreSprite)
            diff = int(self.game.gameLayer.screen[1]*.01)
            self.game.gameLayer.scoreSprite = Label("%d" % int(self.game.gameLayer.score), position=(diff, self.game.gameLayer.screen[1]-diff), font_name='DejaVu Mono', font_size=18, bold=True, color=(0, 0, 0, 128), anchor_x='left', anchor_y='top')
            self.game.gameLayer.add(self.game.gameLayer.scoreSprite)
            #self.game.gameLayer.send_mouse()
            print len(self.game.gameLayer.sprite_pool)

        elif opcode == 17:
            x = b.read_float()
            y = b.read_float()
            scale = b.read_float()
            self.player.center.set(x, y)
            self.player.scale = scale
            # self.subscriber.on_spectate_update(
            #     pos=self.player.center, scale=scale)

        elif opcode == 18:
            #self.subscriber.on_clear_cells()
            self.player.world.cells.clear()
            self.player.own_ids.clear()
            self.player.cells_changed()
            for id in self.game.gameLayer.sprites:
                self.game.gameLayer.sprite_batch.remove(self.game.gameLayer.sprites[id].img)
                self.game.gameLayer.sprite_pool.append(self.game.gameLayer.sprites[id])
            self.game.gameLayer.sprites.clear()
            for id in self.game.gameLayer.names:
                self.game.gameLayer.remove(self.game.gameLayer.names[id])
                self.game.gameLayer.name_pool.append(self.game.gameLayer.names[id])
            self.game.gameLayer.names.clear()

        elif opcode == 32:
            id = b.read_uint()
            if not self.player.is_alive:  # respawned
                self.player.own_ids.clear()
                #self.subscriber.on_respawn()
            # server sends empty name, assumes we set it here
            if id not in self.player.world.cells:
                self.player.world.create_cell(id)
                self.game.gameLayer.sprites[id] = self.game.gameLayer.sprite_pool.pop()
                self.game.gameLayer.sprites[id].cid = id
                self.game.gameLayer.sprites[id].set_type(virus=False)
                self.game.gameLayer.sprites[id].set_name(self.player.nick)
                self.game.gameLayer.sprite_batch.add(self.game.gameLayer.sprites[id].img)
                self.game.gameLayer.names[id] = self.game.gameLayer.name_pool.pop()
                self.game.gameLayer.names[id].element.text = self.player.nick
                self.game.gameLayer.add(self.game.gameLayer.names[id],z=1000)
                # self.game.gameLayer.names[id] = self.game.gameLayer.names[id] = Label("", font_name='DejaVu Mono', font_size=6, bold=True, color=(255, 255, 255, 255), anchor_x='center', anchor_y='center')
                # self.game.gameLayer.add(self.game.gameLayer.names[id])
            # self.world.cells[cid].name = self.player.nick
            self.player.own_ids.add(id)
            self.player.cells_changed()
            self.game.gameLayer.score = 0
            #self.subscriber.on_own_id(cid=id)

        elif opcode == 49:
            leaderboard_names = []
            for i in range(0, b.read_uint()):
                id, name = b.read_uint(), b.read_string16()#.encode('utf-8','ignore')
                if name == '':
                    name = 'An unnamed cell'
                self.game.gameLayer.leaders[i].text = "%d. %s" % (i+1,name[:20])
                # text.Label("%d. %s" % (i+1,name[:20]), font_size=14, font_name='DejaVu Mono', x=self.game.gameLayer.screen[0]-160, y=self.game.gameLayer.screen[1]-40-30-i*22, color=(255, 255, 255, 255),
                #        anchor_x='center', anchor_y='top', width=150, batch=leaders_batch.batch)
                # leaderboard_names.append((id, name))
            # if self.game.gameLayer.leaders_batch in self.game.gameLayer.get_children():
            #     self.game.gameLayer.remove(self.game.gameLayer.leaders_batch)
            # self.game.gameLayer.leaders_batch = leaders_batch
            # self.game.gameLayer.add(self.game.gameLayer.leaders_batch, z=100)
            # #self.subscriber.on_leaderboard_names(leaderboard=leaderboard_names)
            self.player.world.leaderboard_names = leaderboard_names

        elif opcode == 64:
            left = b.read_double()
            top = b.read_double()
            right = b.read_double()
            bottom = b.read_double()
            #self.subscriber.on_world_rect(left=left, top=top, right=right, bottom=bottom)
            self.player.world.top_left = Vec(top, left)
            self.player.world.bottom_right = Vec(bottom, right)
            if len(self.buffer.input) > 0:
                game_mode = b.read_uint()
                server_string = b.read_string16()
                #self.subscriber.on_server_version(number=game_mode, text=server_version)

        elif opcode == 240:
            l =  b.read_uint()
            s = b.read_string8()
            print (240, l, s)
        else:
            raise Exception("UNHANDLED OPCODE!", opcode)
        if len(self.buffer.input) > 0:
            raise Exception('LEFTOVER PAYLOAD!')

    def onClose(self, wasClean, code, reason):
        self.ingame = False

class AgarClientFactory(WebSocketClientFactory):

    def buildProtocol(self, addr):
        proto = AgarClientProtocol(self.game.args.spectate)
        proto.token = self.token
        proto.game = self.game
        self.game.gameLayer.proto = proto
        proto.factory = self
        return proto

def agarWS(data, game):
    iphost, token = data.split()
    ip, port = iphost.split(':')
    port = int(port)
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

class CellSprite(object):

    def __init__(self, imgs):
        self.imgs = imgs
        self.pos = Vec(0, 0)
        self.scale = -1
        self.cid = None
        self.name = ' '
        self.is_virus = -1
        self.size = 0
        self.font = 12
        self.img = None

    def set_name(self, name):
        if name != self.name:
            self.name = name

    def set_type(self, virus=False):
        if virus != self.is_virus:
            self.is_virus = virus
            if self.is_virus:
                self.img = Sprite(self.imgs["virus"])
            else:
                self.img = Sprite(self.imgs["cell"])

    def set_scale(self, scale):
        if scale != self.scale:
            self.scale = scale
            self.img._set_scale(self.scale)

    def set_position(self, pos):
        if pos.x!=self.pos.x or pos.y!=self.pos.y:
            self.pos = pos
            self.img._set_position(self.pos)

class AgarLayer(ColorLayer, pyglet.event.EventDispatcher):

    is_event_handler = True

    def __init__(self):
        self.screen = director.get_window_size()
        super(AgarLayer, self).__init__(255, 255, 255, 255, self.screen[0], self.screen[1])
        #self.position = ((self.screen[0]-self.screen[1])/2,0)
        self.imgs = {
            'cell': resource.image("cell.png"),
            'virus': resource.image("virus.png"),
            'agitated': resource.image("agitated.png")
        }
        self.circles = []
        self.sprite_pool = [CellSprite(self.imgs) for _ in xrange(2500)]
        self.sprites = {}
        self.name_pool = [Label("", font_name='DejaVu Mono', font_size=6, bold=True, color=(255, 255, 255, 255), anchor_x='center', anchor_y='center') for _ in xrange(500)]
        self.names = {}
        self.score = 0
        # self.leaders = []
        self.win_size = Vec(self.screen[0], self.screen[1])
        self.screen_center = self.win_size / 2
        self.screen_scale = 1
        self.world_center = Vec(0, 0)
        self.mouse_pos = Vec(0, 0)
        self.movement_delta = Vec()
        # self.names_batch = BatchNode()
        # self.add(self.names_batch)
        self.leaders_batch = BatchNode()
        diff = int(self.screen[1]*.01)
        text.Label("Leaderboard", font_size=24, font_name='DejaVu Mono Bold', x=self.screen[0]-160, y=self.screen[1]-30, bold=True, color=(255, 255, 255, 255),
               anchor_x='center', anchor_y='top', width=150, batch=self.leaders_batch.batch)
        self.leaders = [text.Label("%d. An unnamed cell" % (i+1), font_size=14, font_name='DejaVu Mono', x=self.screen[0]-160, y=self.screen[1]-40-30-i*22, color=(255, 255, 255, 255),
               anchor_x='center', anchor_y='top', width=150, batch=self.leaders_batch.batch) for i in xrange(10)]
        self.add(self.leaders_batch, z=100)

        self.sprite_batch = BatchNode()
        self.add(self.sprite_batch)
        self.scoreSprite = None
        self.proto = None
        leaderBG = ColorLayer(0,0,0,64,280,280)
        leaderBG.position = (self.screen[0]-300,self.screen[1]-300)
        self.add(leaderBG,z=50)
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
        if self.proto and self.proto.ingame: self.send_mouse()
    #     for c in self.circles:
    #         c.render()
    #     # for b in self.border:
    #     #     b.render()

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
        if self.proto and self.proto.ingame:
            x, y = director.get_virtual_coordinates(x, y)
            self.mouse_pos = Vec(x, y)
            pos_world = self.screen_to_world_pos(self.mouse_pos)
            self.movement_delta = pos_world - self.proto.player.center
            #self.send_mouse()

    def on_mouse_press(self, x, y, button, modifiers):
        if self.proto and self.proto.ingame:
            x, y = director.get_virtual_coordinates(x, y)
            if button == pyglet.window.mouse.MIDDLE:
                #self.send_mouse()
                self.proto.send_shoot()
                return True
            elif button == pyglet.window.mouse.RIGHT:
                #self.send_mouse()
                self.proto.send_split()
                return True

    def send_mouse(self):
        target = self.proto.player.center + self.movement_delta
        self.proto.send_target(*target)

    def on_key_press(self, symbol, modifiers):
        if symbol == key.Q and (modifiers & key.MOD_ACCEL):
            reactor.callFromThread(reactor.stop)
            return True
        elif symbol == key.R and self.proto and self.proto.ingame:
            self.proto.send_respawn()
            return True
        elif symbol == key.S and self.proto and self.proto.ingame:
            self.proto.send_spectate()
            return True
        elif symbol == key.W and self.proto and self.proto.ingame:
            #self.send_mouse()
            self.proto.send_shoot()
            return True
        elif symbol == key.SPACE and self.proto and self.proto.ingame:
            #self.send_mouse()
            self.proto.send_split()
            return True

class PyAgar(object):
    title = "PyAgar"
    def __init__(self, args):
        self.args = args

        pyglet.resource.path.append(os.path.join(dname,'resources'))
        pyglet.resource.reindex()
        pyglet.font.add_file('resources/DejaVuSans.ttf')
        pyglet.font.add_file('resources/unifont.ttf')

        director.set_show_FPS(False)
        w = director.init(fullscreen=True, caption=self.title, visible=True, resizable=True)

        # width = director.window.width
        # height = director.window.height
        # wnew, hnew = int(width * .75), int(height * .75)
        # director.window.set_fullscreen(False)
        # director.window.set_size(wnew, hnew)
        # w.set_location((width-wnew)/2, (height-hnew)/2)

        director.window.pop_handlers()
        director.window.push_handlers(Handler())

        self.gameScene = Scene()
        self.gameLayer = AgarLayer()
        self.gameScene.add(self.gameLayer)

        director.replace(self.gameScene)

        director.window.set_visible(True)

if __name__ == '__main__':

    NAME = 'PyAgar'

    parser = argparse.ArgumentParser(description=NAME)
    parser.add_argument('--get-info', dest='getInfo', action='store_true', help='get server information')
    parser.add_argument('--region', dest='region', default='US-Atlanta', help='set server region')
    parser.add_argument('--spectate', dest='spectate', action='store_true', help='start in spectate mode')
    args = parser.parse_args()

    # log.startLogging(sys.stdout)

    agent = Agent(reactor)

    if args.getInfo:
        d = agent.request('GET', 'http://m.agar.io/info', Headers({'User-Agent': [NAME]}), None)
        d.addCallback(cbResponse, printInfo)
        d.addBoth(cbShutdown)

    else:
        game = PyAgar(args)
        d = agent.request('POST', 'http://m.agar.io/', Headers({'User-Agent': [NAME]}), StringProducer('US-Atlanta:experimental'))
        d.addCallback(cbResponse, lambda x: agarWS(x, game), True)

    reactor.run()
