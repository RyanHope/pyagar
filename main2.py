#!/usr/bin/env python

from __future__ import division

import re, exceptions

import sys, argparse

from twisted.internet import reactor
from twisted.internet.task import LoopingCall
from twisted.internet.defer import succeed
from twisted.web.client import Agent, readBody
from twisted.web.http_headers import Headers
from twisted.web.iweb import IBodyProducer
from zope.interface import implements

import struct, urllib
from autobahn.twisted.websocket import WebSocketClientProtocol, \
    WebSocketClientFactory, connectWS

import os
os.environ['SDL_VIDEO_WINDOW_POS'] = 'center'

from OpenGL.GL import *
from OpenGL.GLU import *

import pygame
from pygame.locals import *
import pygl2d

from vec import Vec
from world import Player

from buffer import Buffer

import pprint, json

def cbBody(body, callback):
    callback(body)

def cbResponse(response, callback, printHeaders=False):
    if printHeaders:
        print pprint.pformat(list(response.headers.getAllRawHeaders()))
    d = readBody(response)
    d.addCallback(cbBody, callback)
    return d

def cbShutdown(reason):
    print reason
    reactor.stop()

def printInfo(data):
    pprint.PrettyPrinter(indent=2).pprint(json.loads(data))

class AgarClientProtocol(WebSocketClientProtocol):

    def __init__(self, *args, **kwargs):
        WebSocketClientProtocol.__init__(self, *args, **kwargs)
        self.player = Player()
        self.ingame = False
        self.re_pattern = re.compile(u'[^\u0000-\uD7FF\uE000-\uFFFF]', re.UNICODE)

    def onConnect(self, response):
        self.buffer = Buffer()

    def onOpen(self, spectate=False):
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

        if spectate:
            self.send_spectate()
        else:
            self.send_respawn()

    def send_respawn(self):
        b = self.buffer
        b.write_byte(0)
        b.write_string(self.player.nick.encode('utf-16le'))
        b.flush_protocol(self)

    def send_spectate(self):
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
            self.ingame = True

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
                        print "DEAD!!!!!!!!!!!!!!!!"
                    self.player.own_ids.remove(prey)
                if prey in self.player.world.cells:
                    del self.player.world.cells[prey]
                    self.game.glcell_pool.append(self.game.glcells[prey])
                    del self.game.glcells[prey]
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
                    print ("SKIN URL FOUND !!!!!",skin_url)
                else:
                    skin_url = ''
                name = b.read_string16()
                name = self.re_pattern.sub(u'\uFFFD', name)
                if id not in self.player.world.cells:
                    self.player.world.create_cell(id)
                    self.game.glcells[id] = self.game.glcell_pool.pop()
                    self.game.glcells[id].cid = id
                    self.game.glcells[id].set_type(virus=virus)
                    self.game.glcells[id].set_name(name)
                self.player.world.cells[id].update(cid=id, x=x, y=y, size=size, name=name, color=color, is_virus=virus, is_agitated=agitated, skin_url=skin_url)
            for i in range(0, b.read_uint()):
                id = b.read_uint()
                if id in self.player.world.cells:
                    del self.player.world.cells[id]
                    if id in self.player.own_ids:
                        self.player.own_ids.remove(id)
                    self.game.glcell_pool.append(self.game.glcells[id])
                    del self.game.glcells[id]
            if self.player.is_alive:
                self.player.cells_changed()
            self.game.recalculate()
            for id in self.player.world.cells:
                pos = self.game.world_to_screen_pos(self.player.world.cells[id].pos)
                self.game.glcells[id].size = int(self.game.world_to_screen_size(self.player.world.cells[id].size)*2)
                if self.game.glcells[id].size==0:
                    print ("SIZE 0", self.player.world.cells[id].name, self.player.world.cells[id].size)
                else:
                    color = self.player.world.cells[id].color2
                    self.game.glcells[id].img.scale(self.game.glcells[id].size/425.)
                    self.game.glcells[id].img.colorize(color[0],color[1],color[2],255)
                    self.game.glcells[id].pos = pos
                    sz = int(self.game.glcells[id].size/8.0)
                    if sz < 12: sz = 12
                    if sz > 62: sz = 62
                    if sz != self.game.glcells[id].font:
                        self.game.glcells[id].font = sz
                        self.game.glcells[id].label.font = self.game.glcells[id].fonts[self.game.glcells[id].font]
                        self.game.glcells[id].label_shadow.font = self.game.glcells[id].fonts[self.game.glcells[id].font]
                        self.game.glcells[id].label.change_text(self.game.glcells[id].name)
                        self.game.glcells[id].label_shadow.change_text(self.game.glcells[id].name)
                # if self.player.world.cells[id].name != '' and sz > 6:
            self.game.update()
            self.game.send_mouse()

        elif opcode == 17:
            x = b.read_float()
            y = b.read_float()
            scale = b.read_float()
            self.player.center.set(x, y)
            self.player.scale = scale

        elif opcode == 18:
            self.clear_all()

        elif opcode == 32:
            id = b.read_uint()
            if not self.player.is_alive:  # respawned
                self.player.own_ids.clear()
            # server sends empty name, assumes we set it here
            if id not in self.player.world.cells:
                self.player.world.create_cell(id)
                self.game.glcells[id] = self.game.glcell_pool.pop()
                self.game.glcells[id].cid = id
                self.game.glcells[id].set_type(virus=False)
                self.game.glcells[id].set_name(self.player.nick)
            else:
                print "HUH?????????????"
            self.player.own_ids.add(id)
            self.player.cells_changed()

        elif opcode == 49:
            leaderboard_names = []
            for i in range(0, b.read_uint()):
                id, name = b.read_uint(), b.read_string16()
                if name == '':
                    name = 'An unnamed cell'
                leaderboard_names.append((id, name))
            self.player.world.leaderboard_names = leaderboard_names

        elif opcode == 64:
            left = b.read_double()
            top = b.read_double()
            right = b.read_double()
            bottom = b.read_double()
            self.player.world.top_left = Vec(top, left)
            self.player.world.bottom_right = Vec(bottom, right)
            if len(self.buffer.input) > 0:
                game_mode = b.read_uint()
                server_string = b.read_string16()

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

    def clear_all(self):
        self.player.world.cells.clear()
        self.player.own_ids.clear()
        self.player.cells_changed()
        self.game.glcells.clear()

class AgarClientFactory(WebSocketClientFactory):

    def buildProtocol(self, addr):
        proto = AgarClientProtocol()
        proto.token = self.token
        proto.game = self.game
        self.game.proto = proto
        proto.factory = self
        reactor.callLater(0, self.game.run)
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

class GLCell(object):

    def __init__(self, fonts, imgs):
        self.fonts = fonts
        self.imgs = imgs
        self.pos = Vec(0, 0)
        self.cid = None
        self.name = ' '
        self.is_virus = -1
        self.size = 0
        self.font = 12
        self.img = None
        self.label_shadow = None
        self.label = None

    def set_name(self, name):
        if name != self.name:
            self.name = name
            try:
                self.label_shadow = pygl2d.font.RenderText(self.name, [0, 0, 0], self.fonts[self.font])
                self.label = pygl2d.font.RenderText(self.name, [255, 255, 255], self.fonts[self.font])
            except exceptions.UnicodeError:
                print map(ord,self.name)
                sys.exit(1)

    def set_type(self, virus=False):
        if virus != self.is_virus:
            self.is_virus = virus
            if self.is_virus:
                self.img = pygl2d.image.Image(self.imgs["virus"])
            else:
                self.img = pygl2d.image.Image(self.imgs["cell"])

    def draw(self):
        if self.size > 1:
            x, y = self.pos
            if self.img:
                self.img.draw([int(x-self.img.image.get_width()/2),int(y-self.img.image.get_height()/2)])
            if len(self.name) > 0 and self.label and self.label_shadow:
                self.label_shadow.draw([int(x-self.label.ren.get_width()/2+1),int(y-self.label.ren.get_height()/2+1)])
                self.label.draw([int(x-self.label.ren.get_width()/2),int(y-self.label.ren.get_height()/2)])

class PyAgar(object):

    def __init__(self, args):
        self.fps = 60
        pygame.display.init()
        pygame.font.init()
        mode_list = pygame.display.list_modes()
        for mode in mode_list:
            print mode
        self.screen_size = mode_list[0]
        self.screen = pygame.display.set_mode(self.screen_size, pygame.FULLSCREEN | pygame.DOUBLEBUF | pygame.OPENGL)
        pygl2d.display.init_gl()

        self.win_size = Vec(self.screen_size[0], self.screen_size[1])
        self.screen_center = self.win_size / 2
        self.screen_scale = 1
        self.world_center = Vec(0, 0)
        self.mouse_pos = Vec(0, 0)
        self.movement_delta = Vec()
        self.proto = None
        self.clock = pygame.time.Clock()
        self.fonts = {}
        for i in range(8,64):
            self.fonts[i] = pygame.font.SysFont("Courier New", i, bold=True)
        self.fps_display = pygl2d.font.RenderText("", [0, 0, 0], self.fonts[16])

        self.pool_size = 2500
        self.imgs= {
            'cell':pygame.image.load("resources/cell.png"),
            'virus':pygame.image.load("resources/virus.png")
            }
        self.glcell_pool = [GLCell(self.fonts, self.imgs) for _ in xrange(self.pool_size)]
        self.glcells = {}

    def run(self):
        self.lc = LoopingCall(self.refresh)
        cleanupD = self.lc.start(1.0 / self.fps)
        cleanupD.addCallbacks(self.quit)

    def update(self):
        self.clock.tick()
        self.fps_display.change_text(str(int(self.clock.get_fps())) + " fps")
        self.draw()
        print len(self.glcell_pool)

    def quit(self, lc):
        pygame.quit()
        reactor.stop()

    def refresh(self):
        self.process_input()

    def send_mouse(self):
        target = self.proto.player.center + self.movement_delta
        self.proto.send_target(*target)

    def process_input(self):
        for event in pygame.event.get():
            if self.proto and self.proto.ingame:
                if event.type == pygame.MOUSEMOTION:
                    self.mouse_pos = Vec(event.pos[0], event.pos[1])
                    pos_world = self.screen_to_world_pos(self.mouse_pos)
                    self.movement_delta = pos_world - self.proto.player.center
                elif event.type == pygame.KEYDOWN:
                    if event.key == K_w:
                        self.proto.send_shoot()
                    elif event.key == K_SPACE:
                        self.proto.send_split()
                    elif event.key == K_r:
                        self.proto.send_respawn()
                    elif event.key == K_s:
                        if not self.proto.player.is_alive:
                            self.proto.clear_all()
                            self.proto.send_spectate()
                elif event.type == pygame.MOUSEBUTTONDOWN:
                    if event.button == 1:
                        self.proto.send_split()
                    elif event.button == 3:
                        self.proto.send_shoot()
            if event.type == pygame.KEYDOWN and event.key == K_ESCAPE:
                self.lc.stop()
            elif event.type == pygame.QUIT:
                self.lc.stop()

    def draw(self):
        pygl2d.display.begin_draw(self.screen_size)
        pygl2d.draw.rect([0, 0, self.screen_size[0], self.screen_size[1]], [255, 255, 255])
        for id in self.glcells:
            self.glcells[id].draw()
        self.fps_display.draw([10, 10])
        pygl2d.display.end_draw()

    def recalculate(self):
        if self.proto.player:
            window_scale = max(self.win_size.x / self.screen_size[0], self.win_size.y / self.screen_size[1])
            self.screen_scale = self.proto.player.scale * window_scale
            self.world_center = self.proto.player.center
            self.world = self.proto.player.world
        elif self.world.size:
            self.screen_scale = min(self.win_size.x / self.world.size.x,
                                    self.win_size.y / self.world.size.y)
            self.world_center = self.world.center
        else:
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

if __name__ == '__main__':

    NAME = 'PyAgar'

    parser = argparse.ArgumentParser(description=NAME)
    parser.add_argument('--get-info', dest='getInfo', action='store_true', help='get server information')
    parser.add_argument('--region', dest='region', default='US-Atlanta', help='set server region')
    args = parser.parse_args()

    game = PyAgar(args)

    agent = Agent(reactor)

    if args.getInfo:
        d = agent.request('GET', 'http://m.agar.io/info', Headers({'User-Agent': [NAME]}), None)
        d.addCallback(cbResponse, printInfo)
        d.addBoth(cbShutdown)
    else:
        d = agent.request('POST', 'http://m.agar.io/', Headers({'User-Agent': [NAME]}), StringProducer('US-Atlanta:experimental'))
        d.addCallback(cbResponse, lambda x: agarWS(x, game), True)

    reactor.run()
