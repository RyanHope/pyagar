#!/usr/bin/env python

from __future__ import division

import sys, argparse

from twisted.internet import reactor
from twisted.internet.task import LoopingCall
from twisted.internet.defer import succeed
from twisted.web.client import Agent, readBody
from twisted.web.http_headers import Headers
from twisted.web.iweb import IBodyProducer
from twisted.python import log
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
        log.msg(pprint.pformat(list(response.headers.getAllRawHeaders())))
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
                if id not in self.player.world.cells:
                    self.player.world.create_cell(id)
                    self.game.glcells[id] = GLCell(id, name, virus)
                self.player.world.cells[id].update(cid=id, x=x, y=y, size=size, name=name, color=color, is_virus=virus, is_agitated=agitated, skin_url=skin_url)
            for i in range(0, b.read_uint()):
                id = b.read_uint()
                if id in self.player.world.cells:
                    del self.player.world.cells[id]
                    if id in self.player.own_ids:
                        self.player.own_ids.remove(id)
                    del self.game.glcells[id]
            if self.player.is_alive:
                self.player.cells_changed()
            self.game.recalculate()
            for id in self.player.world.cells:
                pos = self.game.world_to_screen_pos(self.player.world.cells[id].pos)
                w = int(self.game.world_to_screen_size(self.player.world.cells[id].size)*2)
                color = self.player.world.cells[id].color2
                self.game.glcells[id].img.scale(w/425.)
                self.game.glcells[id].img.colorize(color[0],color[1],color[2],255)
                self.game.glcells[id].pos = pos

        elif opcode == 17:
            x = b.read_float()
            y = b.read_float()
            scale = b.read_float()
            self.player.center.set(x, y)
            self.player.scale = scale

        elif opcode == 18:
            self.player.world.cells.clear()
            self.player.own_ids.clear()
            self.player.cells_changed()
            self.game.glcells.clear()

        elif opcode == 32:
            id = b.read_uint()
            if not self.player.is_alive:  # respawned
                self.player.own_ids.clear()
            # server sends empty name, assumes we set it here
            if id not in self.player.world.cells:
                self.player.world.create_cell(id)
                self.game.glcells[id] = GLCell(id, self.player.nick, False)
            else:
                print "HUH?????????????"
            self.player.own_ids.add(id)
            self.player.cells_changed()

        elif opcode == 49:
            leaderboard_names = []
            for i in range(0, b.read_uint()):
                id, name = b.read_uint(), b.read_string16()#.encode('utf-8','ignore')
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

class GLCell(object):

    def __init__(self, cid, name, is_virus):
        self.pos = Vec(0, 0)
        self.cid = cid
        self.name = name
        self.is_virus = is_virus
        if self.is_virus:
            self.img = pygl2d.image.Image("resources/virus.png")
        else:
            self.img = pygl2d.image.Image("resources/cell.png")

    def draw(self):
        x, y = self.pos
        self.img.draw([int(x-self.img.image.get_width()/2),int(y-self.img.image.get_height()/2)])

class PyAgar(object):

    def __init__(self, args):
        self.fps = 30
        pygame.display.init()
        pygame.font.init()
        mode_list = pygame.display.list_modes()
        for mode in mode_list:
            print mode
        self.screen_size = mode_list[2]
        self.screen = pygame.display.set_mode(self.screen_size, pygame.DOUBLEBUF | pygame.OPENGL)
        pygl2d.display.init_gl()

        self.glcells = {}

        self.win_size = Vec(self.screen_size[0], self.screen_size[1])
        self.screen_center = self.win_size / 2
        self.screen_scale = 1
        self.world_center = Vec(0, 0)
        self.mouse_pos = Vec(0, 0)
        self.movement_delta = Vec()
        self.proto = None

    def run(self):
        self.lc = LoopingCall(self.refresh)
        cleanupD = self.lc.start(1.0 / self.fps)
        cleanupD.addCallbacks(self.quit)

    def quit(self, lc):
        pygame.quit()
        reactor.stop()

    def refresh(self):
        self.process_input()
        self.draw()
        if self.proto.ingame: self.send_mouse()

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

    #log.startLogging(sys.stdout)

    game = PyAgar(args)

    agent = Agent(reactor)

    if args.getInfo:
        d = agent.request('GET', 'http://m.agar.io/info', Headers({'User-Agent': [NAME]}), None)
        d.addCallback(cbResponse, printInfo)
        d.addBoth(cbShutdown)
    else:
        d = agent.request('POST', 'http://m.agar.io/', Headers({'User-Agent': [NAME]}), StringProducer('US-Atlanta'))
        d.addCallback(cbResponse, lambda x: agarWS(x, game), True)

    reactor.run()
