#!/usr/bin/env python3

import os
import sys
from pathlib import Path

import urwid

import yaml


def get_time_str(ts):
    hours = int(abs(ts) / 3600)
    minutes = int(abs(ts / 60) % 60)
    seconds = int(abs(ts) % 60)

    if hours:
        return '%dh %02dm %02ds' % (hours, minutes, seconds)
    if minutes:
        return '%dm %02ds' % (minutes, seconds)

    return '%ds' % abs(ts)


class Route(urwid.WidgetWrap):
    def __init__(self, path):
        self.path = path

        with open(path, 'r', encoding='utf-8') as fp:
            self.route = yaml.safe_load(fp)

        self.game = self.route['game']
        self.name = self.route['name']
        self.text_widget = urwid.SelectableIcon('', 1)
        self.view = urwid.AttrMap(self.text_widget, 'route', MainWindow.focus_map)

        super().__init__(self.view)

    def set_selected(self, selected):
        text = []
        if selected:
            text.append(' * ')
        else:
            text.append('   ')
        text += [
            ('route game', self.game),
            ' – ',
            ('route name', self.name)
        ]
        self.text_widget.set_text(text)


class Run(urwid.WidgetWrap):
    def __init__(self, path):
        self.path = path
        self.name = path.stem

        with open(path, 'r', encoding='utf-8') as fp:
            self.run = yaml.safe_load(fp)

        self.duration = 0.0
        try:
            segments = self.run['segs'].values()
        except KeyError:
            segments = self.run['run']

        for seg in segments:
            if seg['duration'] is None:
                self.duration = None
                break
            self.duration += seg['duration']

        self.who = path.parts[1]
        self.rank_widget = urwid.Text('', align='left')
        self.name_widget = urwid.Text(self.name, align='left')
        self.who_widget = urwid.Text(self.who, align='left')
        self.view = urwid.Columns(
            [
                ('weight', 1, urwid.Padding(self.rank_widget, ('fixed left', 1))),
                ('weight', 4, self.name_widget),
                ('weight', 4, self.who_widget),
                ('weight', 4, urwid.Text(get_time_str(self.duration or 0))),
                ('weight', 4, urwid.Text(self.run['updated'].strftime('%d %b %Y'))),
            ],
        )

        super().__init__(self.view)


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

        ('table head',      'light gray',   'black',        '',       label,     default_bg),

        ('route',           'white',        'black',        '',       'white',   default_bg),
        ('run',             'white',        'black',        '',       'white',   default_bg),
        ('run0',            'white',        'black',        '',       'white',   default_bg),
        ('run1',            'white',        'black',        '',       'white',   selection_bg),
        ('focus run',       'white',        'black',        '',       'white',   default_bg),
        ('focus route',     'white',        'black',        '',       'white',   selection_bg),
        ('route name',      'dark blue',    'black',        '',       idle,      default_bg),
        ('focus route name','dark blue',    'black',        '',       idle,      selection_bg),
        ('route game',      'light green',  'black',        '',       ahead_gain,default_bg),
        ('focus route game','light green',  'black',        '',       ahead_gain,selection_bg),
    ]
    focus_map = {
        'route':         'focus route',
        'route name':    'focus route name',
        'route game':    'focus route game',
    }

    def __init__(self, controller):
        self.controller = controller

        self.title = urwid.Text('Leaderboard', align='center')
        self.header = urwid.AttrMap(self.title, 'header')

        self.routes = urwid.SimpleFocusListWalker([])
        self.routes_listbox = urwid.ListBox(self.routes)
        self.runs = urwid.SimpleListWalker([])
        self.runs_listbox = urwid.ListBox(self.runs)
        self.table_head = urwid.Columns(
            [
                ('weight', 1, urwid.Padding(urwid.Text('#'), ('fixed left', 1))),
                ('weight', 4, urwid.Text('Run name')),
                ('weight', 4, urwid.Text('Player')),
                ('weight', 4, urwid.Text('Time')),
                ('weight', 4, urwid.Text('Date')),
            ],
        )
        self.view = urwid.Frame(
            urwid.Columns(
                [
                    ('weight', 1, urwid.AttrMap(self.routes_listbox, 'route')),
                    ('weight', 2, urwid.AttrMap(urwid.Pile([
                        ('pack', urwid.AttrMap(self.table_head, 'table head')),
                        ('pack', urwid.Divider('─')),
                        urwid.AttrMap(self.runs_listbox, 'run')
                    ]), 'route'))
                ],
                dividechars=1
            ),
            header=self.header
        )
        self.view = urwid.AttrMap(self.view, None, 'focus')

        super().__init__(self.view)


class Leaderboard:
    def __init__(self):
        self.view = MainWindow(self)
        self.loop = urwid.MainLoop(self.view, self.view.palette, unhandled_input=self.unhandled_input)
        self.loop.screen.set_terminal_properties(colors=2**24)

    def main(self):
        routes = []
        for root, _, files in os.walk('routes'):
            for name in files:
                if not name.endswith('.yml'):
                    continue

                route = Route(Path(root) / name)
                routes.append(route)

        for route in sorted(routes, key=lambda r: r.game + r.name):
            self.view.routes.append(urwid.AttrMap(route, 'route', 'focus route'))

        self.select()

        self.loop.run()

    def select(self):
        route = None
        for idx, r in enumerate(self.view.routes):
            if self.view.routes.focus == idx:
                route = r.base_widget
                r.base_widget.set_selected(True)
            else:
                r.base_widget.set_selected(False)

        self.view.runs.clear()
        runs = []
        for root, _, files in os.walk('runs'):
            for name in files:
                if not name.endswith('.yml') or name == 'pb.yml':
                    continue

                run = Run(Path(root) / name)
                if run.run['route'] != str(route.path) or run.duration is None:
                    continue

                runs.append(run)

        for rank, run in enumerate(sorted(runs, key=lambda r: r.duration)):
            run.rank_widget.set_text(str(rank + 1))
            self.view.runs.append(urwid.AttrMap(run, 'run%d' % (rank % 2)))

    def unhandled_input(self, k):
        if k == 'q':
            raise urwid.ExitMainLoop()

        if k == 'enter':
            return self.select()


if __name__ == '__main__':
    sys.exit(Leaderboard().main())
