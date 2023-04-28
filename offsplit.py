#!/usr/bin/env python3

import sys

import urwid

import yaml


def get_time_str(seconds):
    hours = int(abs(seconds) / 3600)
    minutes = int(abs(seconds / 60) % 60)
    seconds = int(abs(seconds) % 60)

    if hours:
        return '%02d:%02d:%02d' % (hours, minutes, seconds)
    if minutes:
        return '%02d:%02d' % (minutes, seconds)

    return str(seconds)


def get_timer_display(progress, color='normal', sign=False):
    if progress is None:
        return (color, '-')

    progress_text = get_time_str(progress)
    if sign:
        progress_text = ('+' if progress >= 0 else '-') + progress_text

    return (color, progress_text)


class Split(urwid.WidgetWrap):
    def __init__(self, name, color, build, description, stats, gold=None, pb=None, pb_start=None, progress=None, progress_start=None):
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

        color = 'hilight'
        for part in self.description.split('|'):
            color = 'hilight' if color == 'normal' else 'normal'
            text.append((color, part))
        self.description_widget = urwid.Text(text)
        self.stats = stats
        self.stats_widget = urwid.Text('\n'.join(f'{key} {value}' for key, value in self.stats.items()), align='right')

        # PB
        self.pb = pb
        self.gold = gold
        self.pb_start = pb_start or (None if self.pb is None else 0)

        # Run
        self.progress = progress
        self.progress_start = progress_start or (None if self.progress is None else 0)
        self.time_widget = urwid.Text('', align='right')
        self.current_widget = urwid.Text('', align='right')
        self.update(current=False)

        self.view = urwid.Columns(
            [
                ('weight', 4, self.name_widget),
                ('weight', 8, self.description_widget),
                ('weight', 2, self.stats_widget),
                ('weight', 2, self.time_widget),
                ('weight', 1, self.current_widget),
            ],
        )
        self.view = urwid.Padding(self.view, ('fixed left', 1), ('fixed right', 5))
        self.view = urwid.AttrWrap(self.view, 'body')
        self.view = urwid.LineBox(self.view)
        self.view = urwid.AttrWrap(self.view, 'line')

        super().__init__(self.view)

    @property
    def time(self):
        if self.progress is None or self.progress_start is None:
            return None

        return self.progress - self.progress_start

    def reset(self):
        if self.time is not None and (self.gold is None or self.time < self.gold):
            self.gold = self.time

        self.progress = self.progress_start = None

    def update(self, current=True):
        if self.time is not None:
            if not current and self.gold is not None and self.time < self.gold:
                color = 'gold'
            elif self.pb and self.progress > (self.pb_start + self.pb):
                color = 'red'
            else:
                color = 'green'

        # PB time
        text = [get_timer_display((self.pb_start + self.pb) if self.pb is not None else None)]
        if self.progress is not None and (not current or self.time > (self.gold or 0) or self.pb is None or self.progress >= (self.pb_start + self.pb)):
            text.append('\n',)
            text.append(get_timer_display(self.progress - (0 if self.pb is None else (self.pb_start + self.pb)), color, sign=True))

        self.time_widget.set_text(text)

        text = [get_timer_display(self.gold, color='gold')]
        if self.progress is not None:
            text.append('\n')
            text.append(get_timer_display(self.time, color))
        self.current_widget.set_text(text)

    def stop(self):
        self.update(current=False)


class MainWindow(urwid.WidgetWrap):
    palette = [
        ('body',            'white',        'black'),

        ('header',          'white',        'dark blue'),
        ('header normal',   'white',        'dark blue',    'bold'),
        ('header green',    'black',        'dark green',   'bold'),
        ('header red',      'white',        'dark red',     'bold'),
        ('header paused',   'black',        'yellow',       'bold'),


        ('footer',          'yellow',       'dark blue'),
        ('footer key',      'black',        'light gray'),
        ('footer error',    'dark red',     'dark blue'),
        ('footer msg',      'light green',  'dark blue'),

        ('line',            'white',        'black'),
        ('focus line',      'yellow',       'black'),
        ('hilight',         'light green',  'black'),
        ('boss',            'light red',    'black'),
        ('build',           'dark magenta', 'black'),

        ('normal',          'light gray',   'black'),
        ('green',           'light green',  'black'),
        ('red',             'light red',    'black'),
        ('gold',            'yellow',       'black'),
    ]
    focus_map = {
        'line':     'focus line',
        'split':    'focus split',
    }

    footer_text = [
        ' ',
        ('footer key', 'ENTER'),
        ' start/split',
        ' ',
        ('footer key', 'SPACE'),
        ' pause',
        ' ',
        ('footer key', 'R'),
        ' reset',
        ' ',
        ('footer key', 'S'),
        ' save',
        ' ',
        ('footer key', 'G'),
        ' save golds',
        ' ',
        ('footer key', 'Q'),
        ' quit',
    ]

    def __init__(self, controller):
        self.controller = controller

        self.stats = urwid.Text('', align='center')
        self.timer = urwid.Text('Elapsed: 0', align='center')
        self.pb = urwid.Text('PB: 0', align='center')
        self.header = urwid.AttrWrap(urwid.Columns([self.stats, self.pb, self.timer]), 'header')
        self.message_widget = urwid.AttrWrap(urwid.Text('', align='center'), 'footer msg')

        self.footer = urwid.AttrWrap(
            urwid.Columns([
                ('weight', 2, urwid.Text(self.footer_text)),
                ('weight', 2, self.message_widget),
                ('weight', 1, urwid.Text(f'{controller.run_path} [{controller.route_path}]', align='right')),
            ]),
            'footer'
        )
        self.splits = urwid.SimpleFocusListWalker([])
        self.listbox = urwid.ListBox(self.splits)
        self.view = urwid.Frame(urwid.AttrWrap(self.listbox, 'body'), header=self.header, footer=self.footer)

        super().__init__(self.view)

    def error(self, message, color='footer error'):
        self.message_widget.set_text((color, message))

    def message(self, message, color='footer msg'):
        self.message_widget.set_text((color, message))

    def add_split(self, split):
        self.splits.append(urwid.AttrMap(split, 'split', self.focus_map))

    def set_enabled(self, enabled):
        if enabled:
            self.focus_map['line'] = 'focus line'
        else:
            self.focus_map.pop('line', None)

        for split in self.splits:
            split._invalidate()


class Spliter:
    def __init__(self, route_path, run_path):
        self.route_path = route_path
        self.run_path = run_path
        self.view = MainWindow(self)
        self.current_split_idx = -1
        self.splits = []
        self.counter = 0
        self.progress = 0
        self.paused = True

        self.run_route = {}
        self.route = {}

        self.loop = urwid.MainLoop(self.view, self.view.palette, unhandled_input=self.unhandled_input)

    @property
    def current_split(self):
        if self.current_split_idx < 0:
            return None

        return self.splits[self.current_split_idx]

    @property
    def previous_split(self):
        if self.current_split_idx < 1:
            return None

        return self.splits[self.current_split_idx-1]

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

                for split in self.run_route:
                    if 'time' not in split:
                        split['time'] = split['pb']
                        split.pop('pb')
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
                    'pb': route.get('time', route.get('pb')),
                }
                for route in self.route
            ]

        pb_start = None
        progress_start = None
        for i, s in enumerate(self.run_route):
            split = Split(
                s['name'],
                s.get('color'),
                s.get('build'),
                s['description'],
                s.get('stats', {}),
                s.get('gold', s.get('bpt', self.route[i].get('bpt', self.route[i].get('gold')))),
                s.get('pb', self.route[i].get('pb')),
                pb_start,
                None if s.get('time') is None else ((progress_start or 0) + s.get('time')),
                None if s.get('time') is None else progress_start or (0 if s.get('time') else progress_start)
            )
            self.splits.append(split)
            self.view.add_split(split)
            if split.pb is not None:
                pb_start = (pb_start or 0) + split.pb

            if split.time is not None:
                progress_start = (progress_start or 0) + split.time

        if progress_start is not None:
            self.progress = progress_start

        self.view.set_enabled(False)
        self.update()

        self.loop.set_alarm_in(1, self.tick)
        self.loop.run()

        return 0

    def tick(self, loop=None, user_data=None):
        try:
            if self.paused:
                return

            self.progress += 1
            if self.current_split:
                self.current_split.progress = self.progress

            self.update()
        finally:
            self.loop.set_alarm_in(1, self.tick)

    def update(self):
        if self.current_split:
            self.current_split.update()

        if not self.current_split:
            color = 'header'
        elif self.paused:
            color = 'header paused'
        elif self.previous_split and self.previous_split.pb is not None and self.previous_split.progress > self.previous_split.pb_start + self.previous_split.pb:
            color = 'header red'
        elif self.current_split:
            if self.current_split.pb is not None and self.current_split.progress > self.current_split.pb_start + self.current_split.pb:
                color = 'header red'
            else:
                color = 'header green'
        else:
            color = 'header normal'

        self.view.header.set_attr_map({None: color})

        sob = 0
        bpt = 0
        pb = 0
        for split in self.splits:
            sob += min(split.time if split.time is not None else (split.gold or 0), split.gold or 0)
            if split == self.current_split:
                bpt += max(split.time if split.time is not None else (split.gold or 0), split.gold or 0)
            elif split.time is not None:
                bpt += split.time
            else:
                bpt += split.gold or 0
            pb += split.pb or 0

        text = []
        text.append('Sum of Best:        ')
        text.append(get_timer_display(sob, color))
        text.append('\n')
        text.append('Best Possible Time: ')
        text.append(get_timer_display(bpt, color))
        self.view.stats.set_text(text)

        self.view.timer.set_text(['Elapsed: ', get_timer_display(self.progress, color)])
        self.view.pb.set_text(['PB: ', get_timer_display(pb, color)])

    def go_next_split(self):
        if self.current_split:
            self.current_split.stop()

        self.current_split_idx += 1

        if self.current_split_idx >= len(self.splits):
            self.stop()
            return False

        self.current_split.progress_start = self.progress
        self.current_split.progress = self.progress

        return True

    def reset(self):
        self.paused = True
        for split in self.splits:
            split.reset()
            split.update(current=False)
        self.stop()
        self.progress = 0
        self.update()

    def start(self):
        self.reset()

        self.view.set_enabled(True)
        self.paused = False
        self.progress = 0
        self.current_split_idx = 0
        self.current_split.progress = 0
        self.current_split.progress_start = 0
        self.update()

    def stop(self):
        self.view.set_enabled(False)
        self.current_split_idx = -1
        self.paused = True
        self.update()

    def pause(self):
        if not self.current_split:
            return

        self.paused = not self.paused
        self.view.message('---PAUSED---' if self.paused else '')

        self.update()

    def unhandled_input(self, k):
        if k == 'enter':
            if not self.current_split:
                self.start()
            elif not self.go_next_split():
                return

            self.view.set_enabled(True)
            self.view.listbox.set_focus(self.current_split_idx, 'above')
            self.view.listbox.set_focus_valign('middle')

            self.update()

        if k == ' ':
            self.pause()

        if k == 'r':
            self.reset()

        if k in ('p', 's'):
            path = self.run_path if k == 's' else self.route_path
            try:
                with open(path, 'w', encoding='utf-8') as fp:
                    route = []
                    for split in self.splits:
                        route.append({
                            'name': split.name,
                            'description': split.description,
                            'pb': split.pb,
                            'gold': split.gold,
                            'time': split.time,
                            'color': split.color,
                            'stats': split.stats,
                            'build': split.build,
                        })
                    yaml.dump({'route': route}, fp)
            except OSError as e:
                self.view.error(f'Unable to save to {path}: {e.strerror}')
            else:
                self.view.message(f'Run saved in {path}')

        if k == 'g':
            try:
                with open(self.route_path, 'w', encoding='utf-8') as fp:
                    for i, s in enumerate(self.route):
                        split = self.splits[i]
                        if split.time is None:
                            continue

                        gold = s.get('gold', s.get('bpt'))
                        if gold is None or split.time < gold:
                            s['gold'] = split.time

                    yaml.dump({'route': self.route}, fp)
            except OSError as e:
                self.view.error(f'Unable to save to {self.route_path}: {e.strerror}')
            else:
                self.view.message(f'Golds saved in {self.route_path}')

        if k in ('q', 'Q'):
            raise urwid.ExitMainLoop()


if __name__ == '__main__':
    if len(sys.argv) < 3 or sys.argv[1] in ('-h', '--help'):
        print(f'{sys.argv[0]} [route] [run]')
        sys.exit(0)

    sys.exit(Spliter(sys.argv[1], sys.argv[2]).main())
