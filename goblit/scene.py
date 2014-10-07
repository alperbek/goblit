import pygame.mouse
from pygame.cursors import load_xbm

from .loaders import load_image
from .hitmap import HitMap
from . import clock
from . import scripts


room_bg = None
objects = []

ACTORS = {}
object_scripts = {}
hitmap = None


class Cursor:
    pointer = None

    @classmethod
    def load(cls):
        cls.DEFAULT = pygame.mouse.get_cursor()
        cls.POINTER = load_xbm('data/hand.xbm', 'data/hand-mask.xbm')

    @classmethod
    def _set(cls, pointer):
        if cls.pointer != pointer:
            pygame.mouse.set_cursor(*pointer)
            cls.pointer = pointer

    @classmethod
    def set_default(cls):
        cls._set(cls.DEFAULT)

    @classmethod
    def set_pointer(cls):
        cls._set(cls.POINTER)


class ScriptError(Exception):
    """A state problem means a script step can't play."""


class ScriptPlayer:
    def __init__(self, script, clock, on_finish=None):
        self.clock = clock
        self.stack = []
        self.skippable = False  # If we can safely skip the delay
        self.on_finish = on_finish
        self.play_subscript(script)

    @property
    def script(self):
        return self.stack[-1][0]

    @property
    def step(self):
        return self.stack[-1][1]

    @step.setter
    def step(self, v):
        self.stack[-1][1] = v

    @property
    def waiting(self):
        return self.stack[-1][2]

    @waiting.setter
    def waiting(self, v):
        self.stack[-1][2] = v

    def play_subscript(self, script):
        self.stack.append([script, 0, None])
        self.next()

    def end_subscript(self):
        self.stack.pop()

    def next(self):
        if self.step >= len(self.script.contents):
            if len(self.stack) > 1:
                self.end_subscript()
                if not self.waiting:
                    self.do_next()
            else:
                self.on_finish()
            return
        self.skippable = False
        instruction = self.script.contents[self.step]
        self.step += 1
        op = type(instruction).__name__.lower()
        handler = getattr(self, 'do_' + op, None)
        try:
            if not handler:
                raise ScriptError("No handler for op %s" % op)
            handler(instruction)
        except ScriptError as e:
            print(e.args[0])
            self.do_next()
        except Exception:
            import traceback
            traceback.print_exc()
            self.do_next()

    def skip(self):
        if self.skippable:
            self.clock.unschedule(self.cancel_line)
            self.clock.unschedule(self.next)
            close_bubble()
            self.next()

    def speak_to(self, target):
        if self.waiting and self.waiting.verb == 'Speak to %s' % target:
            self.do_next()

    def do_next(self):
        self.schedule_next(0)

    def schedule_next(self, delay=2):
        self.clock.schedule(self.next, delay)

    def cancel_line(self):
        close_bubble()
        self.next()

    def do_line(self, line):
        actor = ACTORS.get(line.character)
        if not actor:
            raise ScriptError("Actor %s is not on set" % line.character)
        say(actor, line.line)
        self.clock.schedule(self.cancel_line, 3)
        self.skippable = True

    def do_pause(self, pause):
        self.schedule_next()
        self.skippable = True

    def do_action(self, action):
        self.waiting = action

    def do_stagedirection(self, d):
        actor = ACTORS.get(d.character)
        if not actor:
            raise ScriptError("Actor %s is not on set" % d.character)
        handler = actor.stage_directions.get(d.verb)
        if not handler:
            raise ScriptError(
                "Unsupported stage direction %r for %s" % (d.verb, d.character)
            )
        if d.object:
            object = ACTORS.get(d.object)
            if not object:
                raise ScriptError("%s is not on set" % d.object)
            handler(actor, object)
        else:
            handler(actor)
        self.do_next()

    def do_directive(self, directive):
        name = directive.name
        handler = getattr(self, 'directive_' + name, None)
        if not handler:
            raise ScriptError("No handler for directive %s" % name)
        handler(directive)

    def directive_onclick(self, directive):
        object_scripts[directive.data.strip()] = directive
        self.do_next()


bubble = None


def say(actor, text):
    global bubble
    from .actors import SpeechBubble
    bubble = SpeechBubble(text, actor)


def close_bubble():
    global bubble
    bubble = None


# Script player
player = None


def load():
    global room_bg, hitmap, player
    room_bg = load_image('room')
    from .actors import Goblit, Tox
    ACTORS['GOBLIT'] = Goblit((100, 400))
    ACTORS['WIZARD TOX'] = Tox((719, 339), initial='sitting-at-desk')

    # goblit.say("Blimey, it's cold in here")
    hitmap = HitMap.from_svg('hit-areas')
    Cursor.load()

    s = scripts.parse_file('script.txt')
    player = ScriptPlayer(s, clock)


def on_mouse_down(pos, button):
    if button == 3 and player.skippable:
        player.skip()
        return

    if button == 1 and player.waiting:
        for name, a in ACTORS.items():
            if a.bounds.collidepoint(pos):
                player.speak_to(name)
                break
        r = hitmap.region_for_point(pos)
        if r:
            if r in object_scripts:
                player.play_subscript(object_scripts[r])
                return


def on_mouse_move(pos, rel, buttons):
    global bubble

    if not player.waiting:
        return

    from .actors import FontBubble
    r = hitmap.region_for_point(pos)
    if r:
        Cursor.set_pointer()
        bubble = FontBubble('Look at %s' % r, pos=(480, 440))
    else:
        Cursor.set_default()
        bubble = None


def update(dt):
    clock.tick(dt)


def draw(screen):
    screen.blit(room_bg, (0, 0))
    rh = room_bg.get_height()
    sw, sh = screen.get_size()
    screen.fill((0, 0, 0), pygame.Rect(0, rh, sw, sh - rh))

    drawables = list(ACTORS.values()) + objects
    for o in drawables:
        o.draw(screen)
    if bubble:
        bubble.draw(screen)