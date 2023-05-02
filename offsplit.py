#!/usr/bin/env python3

import colorsys
import sys
import time

import urwid

import yaml


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

        self.footer = urwid.AttrWrap(
            urwid.Columns([
                ('weight', 4, self.keys_widget),
                ('weight', 2, self.message_widget),
                ('weight', 1, urwid.Text(f'{controller.run_path} [{controller.route_path}]', align='right')),
            ]),
            'footer'
        )
        self.segments = urwid.SimpleFocusListWalker([])
        self.listbox = urwid.ListBox(self.segments)
        self.view = urwid.Frame(urwid.AttrWrap(self.listbox, 'body'), header=header, footer=self.footer)

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


class Spliter:
    def __init__(self, route_path, run_path):
        self.route_path = route_path
        self.run_path = run_path
        self.view = MainWindow(self)
        self.current_segment_idx = -1
        self.segments = []
        self.progress = 0.0
        self.paused = True
        self.pressed_key = None
        self.pressed_key_time = None

        self.run_route = {}
        self.route = {}

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

    def main(self):
        try:
            with open(self.route_path, 'r', encoding='utf-8') as fp:
                self.route = yaml.safe_load(fp)['route']
        except OSError as e:
            print(f'Unable to open {self.route_path}: {e.strerror}', file=sys.stderr)
            return 1

        try:
            with open(self.run_path, 'r', encoding='utf-8') as fp:
                self.run_route = yaml.safe_load(fp)['route']
        except OSError:
            # Probably a new run
            self.run_route = [
                {
                    'name': route['name'],
                    'color': route.get('color'),
                    'build': route.get('build'),
                    'description': route['description'],
                    'stats': route.get('stats', {}),
                    'gold': route.get('gold', route.get('bpt', None)),
                    'pb': route.get('duration', route.get('time', route.get('pb'))),
                }
                for route in self.route
            ]

        pb_start = None
        progress_start = None
        for i, s in enumerate(self.run_route):
            # retrocompat
            if 'duration' not in s:
                s['duration'] = s.get('time')
            if 'gold' not in s:
                s['gold'] = s.get('bpt')
            if 'gold' not in self.route[i]:
                self.route[i]['gold'] = self.route[i].get('bpt')

            segment = Segment(
                s['name'],
                s.get('color'),
                s.get('build'),
                s['description'],
                s.get('stats', {}),
                s.get('gold', self.route[i].get('gold')),
                s.get('pb', self.route[i].get('pb')),
                pb_start,
                None if s.get('duration') is None else ((progress_start or 0.0) + s.get('duration')),
                None if s.get('duration') is None else progress_start or (0.0 if s.get('duration') else progress_start)
            )
            self.segments.append(segment)
            self.view.add_segment(segment)
            if segment.pb is not None:
                pb_start = (pb_start or 0.0) + segment.pb

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
            color = '#' + ''.join('%02x' % int(i * 256) for i in colorsys.hsv_to_rgb(h, s, v))
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
        self.view.pb.set_text(['\n', '\n', 'PB: ', get_timer_display(pb, color)])

        text = []
        for key, func in self.keys.items():
            color = 'footer key'
            if self.pressed_key == key:
                color += ' active'

            if key == ' ':
                key = 'SPACE'

            text.append((color, key.upper()))
            text.append('\xa0')
            text.append((func.__doc__ or '').strip().replace(' ', '\xa0'))
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

    def resume(self):
        """resume"""
        progress = 0.0
        for idx, segment in enumerate(self.segments):
            if segment.duration is None:
                self.paused = True
                self.current_segment_idx = idx-1

                self.focus()
                self.update()
                return

            progress += segment.duration

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
        self.save(self.run_path)

    def save_pb(self):
        """save PB"""
        self.save(self.route_path, golds=True)

    def save(self, path, golds=False):
        try:
            with open(path, 'w', encoding='utf-8') as fp:
                route = []
                for segment in self.segments:
                    route.append({
                        'name': segment.name,
                        'description': segment.description,
                        'pb': segment.pb,
                        'gold': segment.duration if golds and segment != self.current_segment and segment.duration and (segment.gold is None or segment.duration < segment.gold) else segment.gold,
                        'duration': segment.duration,
                        'color': segment.color,
                        'stats': segment.stats,
                        'build': segment.build,
                    })
                yaml.dump({'route': route}, fp)
        except OSError as e:
            self.view.error(f'Unable to save to {path}: {e.strerror}')
        else:
            self.view.message(f'Run saved in {path}')

    def save_golds(self):
        """save golds"""
        try:
            with open(self.route_path, 'w', encoding='utf-8') as fp:
                for i, s in enumerate(self.route):
                    segment = self.segments[i]
                    if segment.duration is None:
                        continue

                    gold = s.get('gold', s.get('bpt'))
                    if gold is None or segment.duration < gold:
                        s['gold'] = segment.duration

                yaml.dump({'route': self.route}, fp)
        except OSError as e:
            self.view.error(f'Unable to save to {self.route_path}: {e.strerror}')
        else:
            self.view.message(f'Golds saved in {self.route_path}')

    def quit(self):
        """quit"""
        raise urwid.ExitMainLoop()

    keys = {
        'enter': split,
        ' ': pause,
        'r': reset,
        's': save_run,
        'p': save_pb,
        'g': save_golds,
        'b': resume,
        'q': quit,
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
    if len(sys.argv) < 3 or sys.argv[1] in ('-h', '--help'):
        print(f'{sys.argv[0]} [route] [run]')
        sys.exit(0)

    sys.exit(Spliter(sys.argv[1], sys.argv[2]).main())
