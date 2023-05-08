#!/usr/bin/env python3

import colorsys
import os
import sys
import time
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

import urwid

import yaml

try:
    from termcolor import colored
except ImportError:
    def colored(text, *args, **kwargs):
        return text


def get_big_timer(progress):
    digits = [
        "00000111112222233333444445555566666777778888899999  !!::..",
        ".^^.  .|  .^^. .^^. .  | |^^^ .^^  ^^^| .^^. .^^.   |     ",
        "|  |   |    .^   .^ |..| |..  |..    ][ ^..^ ^..|   | ^   ",
        "|  |   |  .^   .  |    |    | |  |   |  |  |    |   ^ ^   ",
        " ^^   ^^^ ^^^^  ^^     ^ ^^^   ^^    ^   ^^   ^^    ^   ^ ",
    ]
    uchars = {
        '[': chr(0x258C),
        ']': chr(0x2590),
        '|': chr(0x2588),
        '.': chr(0x2584),
        '^': chr(0x2580),
    }
    text = get_time_str(progress)
    display = '\n'
    for line in digits[1:]:
        for digit in text:
            for idx, char in enumerate(digits[0]):
                if char == digit:
                    display += uchars.get(line[idx], line[idx])
        display += '\n'
    return display


def get_time_str(ts):
    hours = int(abs(ts) / 3600)
    minutes = int(abs(ts / 60) % 60)
    seconds = int(abs(ts) % 60)

    if hours:
        return '%02d:%02d:%02d' % (hours, minutes, seconds)
    if minutes:
        return '%02d:%02d' % (minutes, seconds)

    return '%.1f' % abs(ts)


def get_timer_display(progress, color='normal', sign=False):
    if progress is None:
        return (color, '-')

    progress_text = get_time_str(progress)
    if sign:
        progress_text = ('+' if progress >= 0 else '-') + progress_text

    return (color, progress_text)


class Segment(urwid.WidgetWrap):
    def __init__(
        self,
        id,
        name,
        color,
        build,
        description,
        stats,
        gold=None,
        pb=None,
        pb_start=None,
        progress=None,
        progress_start=None
    ):
        # Route meta data
        self.id = id
        self.name = name
        self.name_widget = urwid.Text(self.name, align='center')
        self.color = color
        if color:
            self.name_widget = urwid.AttrWrap(self.name_widget, color)
        self.build = build or []
        self.description = description
        text = []
        for b in self.build:
            text.append(('build', b + '\n'))

        color = 'normal'
        for part in self.description.split('|'):
            text.append((color, part))
            color = 'hilight' if color == 'normal' else 'normal'
        self.description_widget = urwid.Text(text)
        self.stats = stats
        self.stats_widget = urwid.Text('\n'.join(f'{key} {value}' for key, value in self.stats.items()), align='right')

        # PB
        self.pb = pb
        self.gold = gold
        self.pb_start = pb_start or (None if self.pb is None else 0.0)

        # Run
        self.progress = progress
        self.progress_start = progress_start or (None if self.progress is None else 0.0)
        self.time_widget = urwid.Text('', align='right')
        self.duration_widget = urwid.Text('', align='right')
        self.gold_widget = urwid.Text('', align='right')
        self.diff_widget = urwid.Text('', align='right')

        self.update(current=False)

        self.view = urwid.Columns(
            [
                ('weight', 8, self.name_widget),
                ('weight', 16, self.description_widget),
                ('weight', 4, self.stats_widget),
                ('weight', 2, self.time_widget),
                ('weight', 2, self.duration_widget),
                ('weight', 2, self.gold_widget),
                ('weight', 2, urwid.Padding(self.diff_widget, ('fixed right', 1))),
            ],
        )
        self.view = urwid.AttrWrap(self.view, 'body')

        super().__init__(self.view)

    @property
    def duration(self):
        """
        Current duration of the segment.
        """
        if self.progress is None or self.progress_start is None:
            return None

        return self.progress - self.progress_start

    def reset(self):
        """
        Reset the segment.

        It saves gold if any.
        """
        if self.duration is not None and (self.gold is None or self.duration < self.gold):
            self.gold = self.duration

        self.progress = self.progress_start = None

    def update(self, current=True):
        """
        Update display of the segment.

        :param current: if True, it is the current played segment
        :type current: bool
        """
        # PB time and diff with current time
        color = 'normal'
        if self.duration is not None:
            if not current and (self.gold is None or self.duration < self.gold):
                color = 'gold'
            elif self.pb is not None:
                if self.progress > (self.pb_start + self.pb):
                    color = 'behind gain' if self.duration < self.pb else 'behind loss'
                else:
                    color = 'ahead gain' if self.duration < self.pb else 'ahead loss'

        text = [get_timer_display((self.pb_start + self.pb) if self.pb is not None else None)]
        if self.progress is not None and (not current or self.duration > (self.gold or 0.0) or self.pb is None or self.progress >= (self.pb_start + self.pb)):
            text.append('\n',)
            text.append(get_timer_display(self.progress - (0.0 if self.pb is None else (self.pb_start + self.pb)), color, sign=True))

        self.time_widget.set_text(text)

        # Segment duration
        text = [get_timer_display(self.pb)]
        if self.progress is not None:
            text.append('\n')
            if (self.gold is None or self.duration < self.gold) and not current:
                color = 'gold'
            elif self.pb is not None:
                if self.duration > self.pb:
                    color = 'behind gain' if self.progress < (self.pb_start + self.pb) and current else 'behind loss'
                else:
                    color = 'ahead gain' if not current or self.gold is None or self.progress < self.gold else 'ahead loss'
            else:
                color = 'normal'
            text.append(get_timer_display(self.duration, color))
        self.duration_widget.set_text(text)

        # Segment gold
        self.gold_widget.set_text(get_timer_display(self.gold, color='fixed gold'))

        # Diff between gold and pb/current duration
        text = []
        if self.gold is not None:
            if self.pb is not None:
                if self.pb == self.gold:
                    text.append(('fixed gold', '0'))
                else:
                    text.append(get_timer_display(self.pb - self.gold, sign=True, color='diff'))
            if self.duration is not None:
                text.append('\n')
                text.append(get_timer_display(self.duration - self.gold, sign=True, color='gold' if self.duration < self.gold and not current else 'diff'))

        self.diff_widget.set_text(text or '')

    def stop(self):
        self.update(current=False)


class MainWindow(urwid.WidgetWrap):
    default_bg = '#2f3542'
    selection_bg = '#485460'
    footer_bg = '#1e2431'
    ahead_gain = '#2ed573'
    ahead_loss = '#7bed9f'
    behind_gain = '#ff6b81'
    behind_loss = '#ff4757'
    label = '#a4b0be'
    idle = '#1e90ff'
    text = '#f1f2f6'
    gold = '#eccc68'

    hilight = '#70a1ff'

    palette = [
        # title             foreground      background      spec      256-fg     256bg
        ('body',            'white',        'black',        '',       text,      default_bg),
        ('focus body',      'white',        'black',        '',       text,      selection_bg),

        ('header',          'white',        'dark blue',    'bold',   'white',   idle),
        ('header normal',   'white',        'dark blue',    'bold',   'white',   idle),
        ('header green',    'black',        'dark green',   'bold',   selection_bg, ahead_gain),
        ('header red',      'white',        'dark red',     'bold',   text,      behind_loss),
        ('header paused',   'black',        'yellow',       'bold',   selection_bg, gold),

        ('footer',          'yellow',       'dark blue',    '',       idle,      footer_bg),
        ('footer key',      'black',        'light gray',   '',       label,     selection_bg),
        ('footer key active',   'black',    'dark green',   '',       label,     '#1a7a41'),
        ('footer error',    'dark red',     'dark blue',    '',       '',        footer_bg),
        ('footer msg',      'light green',  'dark blue',    '',       '',        footer_bg),

        ('table head',      'white',        'black',        '',       'white',   default_bg),

        ('line',            'light gray',   'black',        '',       label,     default_bg),
        ('focus line',      'yellow',       'black',        '',       gold,      selection_bg),
        ('hilight',         'light green',  'black',        '',       hilight,   default_bg),
        ('focus hilight',   'light green',  'black',        '',       hilight,   selection_bg),
        ('boss',            'light red',    'black',        'bold',   '#ffa502', default_bg),
        ('focus boss',      'light red',    'black',        'bold',   '#ffa502', selection_bg),
        ('build',           'dark magenta', 'black',        '',       'white',   default_bg),
        ('focus build',     'dark magenta', 'black',        '',       'white',   selection_bg),

        ('diff',            'dark magenta', 'black',        '',       '#a4b0be', default_bg),
        ('focus diff',      'dark magenta', 'black',        '',       '#a4b0be', selection_bg),
        ('normal',          'light gray',   'black',        '',       '',        default_bg),
        ('focus normal',    'white',        'black',        'bold',   'white',   selection_bg),
        ('ahead gain',      'light green',  'black',        'bold',   ahead_gain,   default_bg),
        ('focus ahead gain','light green',  'black',        'bold',   ahead_gain,   selection_bg),
        ('ahead loss',      'light green',  'black',        '',       ahead_loss,   default_bg),
        ('focus ahead loss','light green',  'black',        '',       ahead_loss,   selection_bg),
        ('behind gain',     'light red',    'black',        'bold',   behind_gain,  default_bg),
        ('focus behind gain','light red',   'black',        'bold',   behind_gain,  selection_bg),
        ('behind loss',     'light red',    'black',        '',       behind_loss,  default_bg),
        ('focus behind loss','light red',   'black',        '',       behind_loss,  selection_bg),
        ('fixed gold',      'yellow',       'black',        '',       gold,       default_bg),
        ('green',           'light green',  'black',        '',       ahead_gain,   default_bg),
        ('focus green',     'light green',  'black',        'bold',   ahead_gain,   selection_bg),
        ('red',             'light red',    'black',        '',       behind_loss,  default_bg),
        ('focus red',       'light red',    'black',        'bold',   behind_loss,  selection_bg),
        ('fixed gold',      'yellow',       'black',        '',       gold,       default_bg),
        ('focus fixed gold',    'yellow',   'black',        'bold',   gold,       selection_bg),
        ('gold',            'yellow',       'black',        '',       gold,       default_bg),
        ('focus gold',      'yellow',       'black',        'bold',   gold,       selection_bg),
    ]
    focus_map = {
        'line':         'focus line',
        'segment':      'focus segment',
        'body':         'focus body',
        'normal':       'focus normal',
        'ahead gain':   'focus ahead gain',
        'ahead loss':   'focus ahead loss',
        'behind gain':  'focus behind gain',
        'behind loss':  'focus behind loss',
        'green':        'focus green',
        'red':          'focus red',
        'gold':         'focus gold',
        'fixed gold':   'focus fixed gold',
        'diff':         'focus diff',
        'hilight':      'focus hilight',
        'boss':         'focus boss',
        'build':        'focus build',
    }

    def __init__(self, controller):
        self.controller = controller

        self.stats = urwid.Text('', align='center')
        self.timer = urwid.Text('', align='right')
        self.pb = urwid.Text('', align='center')
        self.header = urwid.AttrWrap(urwid.Columns([self.stats, self.pb, self.timer]), 'header')
        self.table_head = urwid.Columns(
            [
                ('weight', 8, urwid.Text('')),
                ('weight', 16, urwid.Text('')),
                ('weight', 4, urwid.Text('')),
                ('weight', 2, urwid.Text('Time', align='right')),
                ('weight', 2, urwid.Text('Sgmt', align='right')),
                ('weight', 2, urwid.Text('Gold', align='right')),
                ('weight', 2, urwid.Padding(urwid.Text('Diff', align='right'), ('fixed right', 1))),
            ],
        )
        header = urwid.AttrWrap(urwid.Pile([self.header, self.table_head, urwid.Divider('─')]), 'table head')

        self.message_widget = urwid.AttrWrap(urwid.Text('', align='center'), 'footer msg')
        self.keys_widget = urwid.Text('')
        self.run_widget = urwid.Text('', align='right')

        self.footer = urwid.AttrWrap(
            urwid.Columns([
                ('weight', 4, self.keys_widget),
                ('weight', 2, self.message_widget),
                ('weight', 1, self.run_widget),
            ]),
            'footer'
        )
        self.segments = urwid.SimpleFocusListWalker([])
        self.listbox = urwid.ListBox(self.segments)
        self.view = urwid.Frame(self.listbox, header=header, footer=self.footer)

        super().__init__(self.view)

    def error(self, message, color='footer error'):
        self.message_widget.set_text((color, message))

    def message(self, message, color='footer msg'):
        self.message_widget.set_text((color, message))

    def add_segment(self, segment):
        self.segments.append(urwid.AttrMap(segment, 'segment', self.focus_map))
        self.segments.append(urwid.AttrMap(urwid.Divider('─'), 'line'))

    def set_enabled(self, enabled):
        for key in self.focus_map:
            if enabled:
                self.focus_map[key] = 'focus ' + key
            else:
                self.focus_map[key] = key

        for segment in self.segments:
            segment._invalidate()


@dataclass
class Run:
    path: str
    route: str
    created: datetime
    updated: datetime
    segs: dict

    @property
    def name(self):
        return Path(self.path).stem

    @classmethod
    def load(cls, path):
        with open(path, 'r', encoding='utf-8') as fp:
            d = yaml.safe_load(fp)

        d['path'] = path
        if 'segs' not in d:
            d['segs'] = {}

        if 'run' in d:
            route = Route.load(d['route'])
            for idx, seg in enumerate(route.route):
                d['segs'][seg['id']] = d['run'][idx]
            d.pop('run')

        return Run(**d)

    @classmethod
    def from_route(cls, path, route):
        segs = {}
        for segment in route.route:
            segs[segment['id']] = {'pb': None, 'duration': None, 'gold': None}
        return Run(
            path,
            route.path,
            created=None,
            updated=None,
            segs=segs
        )

    @classmethod
    def from_pb(cls, path, pb):
        segs = {}
        for id, segment in pb.segs.items():
            segs[id] = {'pb': segment['duration'], 'duration': None, 'gold': segment['gold']}
        return Run(
            path,
            pb.route,
            created=datetime.now(),
            updated=datetime.now(),
            segs=segs,
        )

    def get_route(self):
        return Route.load(self.route)

    def iter_segments(self):
        route = self.get_route()

        pb_start = None
        progress_start = None
        for route_seg in route.route:
            try:
                run_seg = self.segs[route_seg['id']]
            except KeyError:
                # This is probably a new segment in the route that was not
                # present in the run/pb.
                run_seg = {'pb': None, 'duration': None, 'gold': None}

            segment = Segment(
                route_seg['id'],
                route_seg['name'],
                route_seg.get('color'),
                route_seg.get('build'),
                route_seg['description'],
                route_seg.get('stats', {}),
                run_seg['gold'],
                run_seg['pb'],
                pb_start,
                None if run_seg.get('duration') is None else ((progress_start or 0.0) + run_seg.get('duration')),
                None if run_seg.get('duration') is None else progress_start or (0.0 if run_seg.get('duration') else progress_start)
            )
            yield segment

            if segment.pb is not None:
                pb_start = (pb_start or 0.0) + segment.pb

            if segment.duration is not None:
                progress_start = (progress_start or 0.0) + segment.duration

    def save(self):
        d = asdict(self)
        d.pop('path')

        with open(self.path, 'w', encoding='utf-8') as fp:
            yaml.dump(d, fp)

    @classmethod
    def iter_runs(cls, path):
        for root, _, files in os.walk(path):
            for f in files:
                if f.endswith('.yml'):
                    yield Run.load(os.path.join(root, f))


@dataclass
class Route:
    ROUTES_DIR = 'routes'

    path: str
    game: str
    name: str
    route: list

    @classmethod
    def load(cls, path):
        with open(path, 'r', encoding='utf-8') as fp:
            d = yaml.safe_load(fp)

        d['path'] = path
        return Route(**d)

    def save(self):
        d = asdict(self)
        d.pop('path')

        with open(self.path, 'w', encoding='utf-8') as fp:
            yaml.dump(d, fp)

    @classmethod
    def iter_routes(cls):
        for root, _, files in os.walk(cls.ROUTES_DIR):
            for f in files:
                if f.endswith('.yml'):
                    yield Route.load(os.path.join(root, f))


class Spliter:
    def __init__(self):
        self.pb = None
        self.route = None
        self.run = None

        self.view = MainWindow(self)
        self.current_segment_idx = -1
        self.segments = []
        self.progress = 0.0
        self.paused = True
        self.debug = False
        self.pressed_key = None
        self.pressed_key_time = None

        self.loop = urwid.MainLoop(self.view, self.view.palette, unhandled_input=self.unhandled_input)
        self.loop.screen.set_terminal_properties(colors=2**24)

    @property
    def current_segment(self):
        if self.current_segment_idx < 0:
            return None

        return self.segments[self.current_segment_idx]

    @property
    def previous_segment(self):
        if self.current_segment_idx < 1:
            return None

        return self.segments[self.current_segment_idx-1]

    def iter_routes(self):
        for root, _, files in os.walk('routes'):
            for f in files:
                if f.endswith('.yml'):
                    yield Route.load(os.path.join(root, f))

    def main(self):
        if len(sys.argv) < 2 or sys.argv[1] in ('-h', '--help'):
            print(f'{sys.argv[0]} RUN_DIR [RUN_ID]', file=sys.stderr)
            return 1

        run_dir = Path(sys.argv[1])

        if not (run_dir / 'pb.yml').exists():
            print('No runs in %s. Do you want to create it? (Y/n)' % colored(run_dir, 'yellow'), end=' ', flush=True)
            if sys.stdin.readline().strip() in ('N', 'n'):
                return 0

            routes = []
            for idx, r in enumerate(Route.iter_routes()):
                print(' %s %s − %s' % (colored(idx, 'magenta'), colored(r.game, 'green'), colored(r.name, 'blue')))
                routes.append(r)

            while self.route is None:
                print('What route do you want to use?', end=' ', flush=True)
                i = sys.stdin.readline().strip()
                try:
                    self.route = routes[int(i)-1]
                except (ValueError, TypeError):
                    if i == 'q':
                        return 0
                except IndexError:
                    continue

            try:
                os.makedirs(run_dir)
            except FileExistsError:
                pass

            self.pb = Run.from_route(run_dir / 'pb.yml', self.route)
            self.pb.save()
        else:
            self.pb = Run.load(run_dir / 'pb.yml')
            self.route = self.pb.get_route()

            print('Loaded route %s − %s' % (colored(self.route.game, 'green'), colored(self.route.name, 'blue')))

        run_path = None
        if len(sys.argv) < 3:
            runs = []
            for r in sorted(Run.iter_runs(run_dir), key=lambda r: r.updated):
                if r.name == 'pb':
                    print(' %s %s' % (colored('%-10s' % r.name, 'magenta', attrs=['bold']), r.updated))
                else:
                    print(' %s %s' % (colored('%-10s' % r.name, 'magenta'), r.updated))
                runs.append(r)

            while run_path is None:
                print('Enter name of the route, or new one to create it:', end=' ', flush=True)
                run_path = sys.stdin.readline().strip()
        else:
            run_path = sys.argv[2]

        if Path(run_path).exists():
            self.run = Run.load(run_path)
        elif Path(run_dir / run_path).with_suffix('.yml').exists():
            self.run = Run.load(Path(run_dir / run_path).with_suffix('.yml'))
        elif run_path.endswith('.yml'):
            self.run = Run.from_pb(run_path, self.pb)
        else:
            self.run = Run.from_pb(Path(run_dir / run_path).with_suffix('.yml'), self.pb)

        self.view.run_widget.set_text(f'{self.run.path}')

        progress_start = None
        for segment in self.run.iter_segments():
            self.segments.append(segment)
            self.view.add_segment(segment)

            if segment.duration is not None:
                progress_start = (progress_start or 0.0) + segment.duration

        if progress_start is not None:
            self.progress = progress_start

        self.view.set_enabled(False)
        self.update()

        self.loop.set_alarm_in(0.1, self.tick)
        self.loop.run()

        return 0

    def tick(self, loop=None, user_data=None):
        try:
            # blink golds
            ts = time.time()
            h = 0.125
            s = 0.59
            v = 1 - 0.7 * abs(0.5 - (ts % 1))
            color = '#' + ''.join('%02x' % int(i * 255) for i in colorsys.hsv_to_rgb(h, s, v))
            self.loop.screen.register_palette_entry('gold', 'yellow', 'black', '', color, '#2f3542')
            self.loop.screen.clear()

            # reset display of pressed key after 0.1s
            if self.pressed_key and self.pressed_key_time + 0.1 < time.time():
                self.pressed_key = None
                self.update()

            if self.paused:
                return

            self.progress += 0.1
            if self.current_segment:
                self.current_segment.progress = self.progress

            self.update()
        finally:
            self.loop.set_alarm_in(0.1, self.tick)

    def update(self):
        if self.current_segment:
            self.current_segment.update()

        if not self.current_segment:
            color = 'header'
        elif self.paused:
            color = 'header paused'
        elif self.previous_segment and self.previous_segment.pb is not None and self.previous_segment.progress > self.previous_segment.pb_start + self.previous_segment.pb:
            color = 'header red'
        elif self.current_segment:
            if self.current_segment.pb is not None and self.current_segment.progress > self.current_segment.pb_start + self.current_segment.pb:
                color = 'header red'
            else:
                color = 'header green'
        else:
            color = 'header normal'

        self.view.header.set_attr_map({None: color})

        sob = 0.0
        bpt = 0.0
        pb = 0.0
        for segment in self.segments:
            sob += min(segment.duration if segment.duration is not None and segment != self.current_segment else (segment.gold or 0.0), segment.gold or 0.0)
            if segment == self.current_segment:
                bpt += max(segment.duration if segment.duration is not None else (segment.gold or 0.0), segment.gold or 0.0)
            elif segment.duration is not None:
                bpt += segment.duration
            else:
                bpt += segment.gold or 0.0
            pb += segment.pb or 0.0

        text = ['\n', '\n']
        text.append('Sum of Best:        ')
        text.append(get_timer_display(sob, color))
        text.append('\n')
        text.append('Best Possible Time: ')
        text.append(get_timer_display(bpt, color))
        self.view.stats.set_text(text)

        self.view.timer.set_text(get_big_timer(self.progress))
        self.view.pb.set_text(
            [
                '\n',
                f'{self.route.game} – {self.route.name}',
                '\n',
                '\n',
                'PB: ', get_timer_display(pb, color),
                '\n',
                self.pb.created.strftime('%Y-%m-%d %H:%M') if self.pb.created else ''
            ]
        )

        text = []
        for key, func in self.keys.items():
            doc = func.__doc__ or ''
            if not doc:
                continue

            color = 'footer key'
            if self.pressed_key == key:
                color += ' active'

            if key == ' ':
                key = 'SPACE'

            text.append((color, key.upper()))
            text.append('\xa0')
            text.append((doc).strip().replace(' ', '\xa0'))
            text.append(' ')

        self.view.keys_widget.set_text(text)

    def go_next_segment(self):
        if self.current_segment:
            self.current_segment.stop()

        self.current_segment_idx += 1

        if self.current_segment_idx >= len(self.segments):
            self.stop()
            return False

        self.current_segment.progress_start = self.progress
        self.current_segment.progress = self.progress

        return True

    def reset(self):
        """reset"""
        self.paused = True
        for segment in self.segments:
            segment.reset()
            segment.update(current=False)
        self.stop()
        self.progress = 0.0
        self.update()

    def start(self):
        self.reset()

        self.view.set_enabled(True)
        self.paused = False
        self.progress = 0.0
        self.current_segment_idx = 0
        self.current_segment.progress = 0.0
        self.current_segment.progress_start = 0.0
        self.update()

    def resume_segment(self, idx):
        self.paused = True
        self.current_segment_idx = idx-1

        self.focus()
        self.update()

    def resume(self):
        """resume"""
        progress = 0.0
        for idx, segment in enumerate(self.segments):
            if segment.duration is None:
                self.resume_segment(idx)
                return

            progress += segment.duration

        self.resume_segment(len(self.segments))

    def stop(self):
        self.view.set_enabled(False)
        self.current_segment_idx = -1
        self.paused = True
        self.update()

    def focus(self):
        self.view.set_enabled(True)

        if self.current_segment_idx >= 0:
            self.view.listbox.set_focus(self.current_segment_idx*2, 'above')
            self.view.listbox.set_focus_valign('middle')

    def pause(self):
        """pause"""
        if not self.current_segment:
            self.pressed_key = None
            return

        self.paused = not self.paused

        self.update()

    def split(self):
        """start/split"""
        if not self.current_segment:
            self.start()
        elif not self.go_next_segment():
            return

        self.focus()

    def save_run(self):
        """save run"""
        self.run.updated = datetime.now()
        self.run.segs = {
            segment.id: {
                'duration': segment.duration,
                'pb': segment.pb,
                'gold': segment.gold,
            }
            for segment in self.segments
        }
        self.run.save()
        self.view.message(f'Run saved in {self.run.path}')

    def save_pb(self):
        """save PB"""
        self.pb.created = datetime.now()
        self.pb.updated = datetime.now()
        self.pb.segs = {
            segment.id:
            {
                'duration': segment.duration,
                'pb': segment.pb,
                'gold': segment.duration if segment != self.current_segment and segment.duration and (segment.gold is None or segment.duration < segment.gold) else segment.gold,
            }
            for segment in self.segments
        }
        self.pb.save()
        self.view.message(f'PB saved in {self.pb.path}')

    def save_golds(self):
        """save golds"""
        self.pb.updated = datetime.now()
        for segment in self.segments:
            gold = self.pb.segs[segment.id]['gold']
            if segment.duration and gold is None or segment.duration < gold:
                self.pb.segs[segment.id]['gold'] = segment.duration

        self.pb.save()
        self.view.message(f'Golds saved in {self.pb.path}')

    def quit(self):
        """quit"""
        raise urwid.ExitMainLoop()

    def toggle_debug(self):
        self.debug = not self.debug

        for seg in self.segments:
            if self.debug:
                seg.name_widget.set_text([seg.name, '\n', seg.id])
            else:
                seg.name_widget.set_text(seg.name)

    keys = {
        'enter': split,
        ' ': pause,
        'r': reset,
        's': save_run,
        'p': save_pb,
        'g': save_golds,
        'b': resume,
        'q': quit,
        'd': toggle_debug,
    }

    def unhandled_input(self, k):
        if isinstance(k, tuple):
            # do not handle pointer
            return

        self.pressed_key = k
        self.pressed_key_time = time.time()

        func = self.keys.get(k.lower())
        if func:
            func(self)

        self.update()


if __name__ == '__main__':
    try:
        sys.exit(Spliter().main())
    except KeyboardInterrupt:
        sys.exit(0)
