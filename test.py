import pyglet
import string, random

w = pyglet.window.Window()
b = pyglet.graphics.Batch()

l = pyglet.text.Label("abc", font_size=w.height,
                          batch=b,
                          x=w.width/2, y=w.height/2,
                          anchor_x="center", anchor_y="center")

def change_label():
    l.text = "".join([random.choice(string.ascii_letters) for x in range(3)])
    l.font_size=random.randint(72,144)

def update(n):
    change_label()

@w.event
def on_draw():
    w.clear()
    b.draw()

pyglet.clock.schedule(update)
pyglet.app.run()
