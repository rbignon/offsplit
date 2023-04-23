#!/usr/bin/env python3

import yaml
import urwid


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
    def __init__(self, name, description, stats, start=0, bpt=0, pb=0, color=None, build=None):
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
        self.stats_widget = urwid.Text('\n'.join('%s %s' % (key, value) for key, value in self.stats.items()), align='right')
        self.start = start
        self.bpt = bpt
        self.pb = pb
        self.new_bpt = bpt
        self.new_pb = pb
        self.progress = 0
        self.progress_start = start
        self.time_widget = urwid.Text('', align='right')
        self.current_widget = urwid.Text('', align='right')
        self.reset()

        #vline = urwid.AttrWrap(urwid.SolidFill('\u2502'), 'line')
        self.view = urwid.Columns(
            [
                ('weight', 4, self.name_widget),
                #('fixed', 1, vline),
                ('weight', 8, self.description_widget),
                #('fixed', 1, vline),
                ('weight', 2, self.stats_widget),
                #('fixed', 1, vline),
                ('weight', 2, self.time_widget),
                ('weight', 1, self.current_widget),
            ],
        )
        self.view = urwid.Padding(self.view, ('fixed left', 1), ('fixed right', 5))
        self.view = urwid.AttrWrap(self.view, 'body')
        self.view = urwid.LineBox(self.view)
        self.view = urwid.AttrWrap(self.view, 'line')

        super().__init__(self.view)

    def reset(self):
        self.time_widget.set_text(get_timer_display((self.start + self.pb) if self.pb else None))
        self.current_widget.set_text([get_timer_display(self.bpt, color='gold')])

    def update(self, display_all=False, color=None):
        text = [get_timer_display((self.start + self.pb) if self.pb else None)]
        #text.append('\n')
        #text += [str(self.progress), ' ', str(self.start), ' ', str(self.pb), ' ', str(self.bpt)]
        if display_all or self.progress - self.progress_start > self.bpt or self.progress >= (self.start + self.pb):
            text.append('\n',)
            if not color:
                if self.progress < (self.start + self.pb):
                    color = 'green'
                else:
                    color = 'red'
            text.append(get_timer_display(self.progress - (self.start + self.pb), color, sign=True))

        self.time_widget.set_text(text)

        if not color:
            if self.progress > self.start + self.pb:
                color = 'red'
            else:
                color = 'green'
        self.current_widget.set_text([get_timer_display(self.bpt), '\n', get_timer_display(self.progress - self.progress_start, color)])

    def stop(self):
        color = None
        self.new_pb = self.progress - self.progress_start
        if not self.bpt or self.new_pb < self.bpt:
            self.new_bpt = self.new_pb
            color = 'gold'

        self.update(display_all=True, color=color)


class MainWindow(urwid.WidgetWrap):
    palette = [
        ('body', 'white', 'black'),
        #('focus', 'light gray', 'dark blue', 'standout'),
        ('header', 'yellow', 'dark blue', 'standout'),
        ('footer', 'black', 'light gray'),
        ('footer key', 'yellow', 'dark blue'),
        ('hilight', 'light green', 'black'),
        ('line',         'white',      'black', 'standout'),
        ('focus line',   'yellow', 'black', 'standout'),
        ('boss',         'light red',      'black'),
        ('build',        'dark magenta',           'black'),

        ('title normal',   'white', 'dark blue', 'bold'),
        ('title green',    'light green', 'dark blue', 'bold'),
        ('title red',      'light red', 'dark blue', 'bold'),
        ('title paused',   'yellow', 'dark blue', 'bold'),

        ('normal',       'white', 'black'),
        ('green',        'light green', 'black'),
        ('red',          'light red', 'black'),
        ('gold',         'yellow', 'black'),
    ]
    focus_map = {
        'line': 'focus line',
        'split': 'focus split',
    }

    footer_text = [
        '     ',
        ('footer key', 'ENTER'),
        ': start/split',
        '     ',
        ('footer key', 'SPACE'),
        ': pause',
        '     ',
        ('footer key', 'R'),
        ': reset',
        '     ',
        ('footer key', 'S'),
        ': save',
        '     ',
        ('footer key', 'G'),
        ': save golds only',
        '     ',
        ('footer key', 'Q'),
        ': quit',
    ]

    def __init__(self, controller):
        self.controller = controller

        self.stats = urwid.Text('', align='center')
        self.timer = urwid.Text('Elapsed: 0', align='center')
        self.pb = urwid.Text('PB: 0', align='center')
        self.header = urwid.AttrWrap(urwid.Columns([self.stats, self.pb, self.timer]), 'header')

        self.footer = urwid.AttrWrap(urwid.Text(self.footer_text), 'footer')
        self.splits = urwid.SimpleFocusListWalker([])
        self.listbox = urwid.ListBox(self.splits)
        self.view = urwid.Frame(urwid.AttrWrap(self.listbox, 'body'), header=self.header, footer=self.footer)

        super().__init__(self.view)

    def add_split(self, split):
        self.splits.append(urwid.AttrMap(split, 'split', self.focus_map))

    def set_enabled(self, enabled):
        if enabled:
            self.focus_map['line'] = 'focus line'
        else:
            self.focus_map.pop('line')

        for split in self.splits:
            split._invalidate()


class Spliter:
    def __init__(self):
        self.view = MainWindow(self)
        self.current_split_idx = -1
        self.splits = []
        self.counter = 0
        self.progress = 0
        self.paused = True

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
        with open('route.yml', 'r', encoding='utf-8') as fp:
            route = yaml.safe_load(fp)

        start = 0
        for s in route['route']:
            bpt = s.get('bpt', 0)
            pb = s.get('pb', 0)
            split = Split(s['name'], s['description'], s.get('stats', {}), start, bpt, pb, s.get('color'), s.get('build'))
            self.splits.append(split)
            self.view.add_split(split)
            start += pb

        self.view.set_enabled(False)
        self.update()

        self.loop.set_alarm_in(1, self.tick)
        self.loop.run()

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

        sob = 0
        bpt = 0
        pb = 0
        for split in self.splits:
            sob += split.new_bpt or max(0, split.progress - split.progress_start)
            bpt += max(split.new_bpt, split.progress - split.progress_start)
            pb += split.pb

        text = []
        text.append('Sum of Best:        ')
        text.append(get_timer_display(sob, 'title normal'))
        text.append('\n')
        text.append('Best Possible Time: ')
        text.append(get_timer_display(bpt, 'title normal'))
        self.view.stats.set_text(text)

        if self.paused:
            color = 'title paused'
        elif self.previous_split:
            if self.previous_split.progress > self.previous_split.start + self.previous_split.pb:
                color = 'title red'
            else:
                color = 'title green'
        elif self.current_split:
            if self.current_split.progress > self.current_split.start + self.current_split.pb:
                color = 'title red'
            else:
                color = 'title green'
        else:
            color = 'title normal'
        self.view.timer.set_text(['Elapsed: ', get_timer_display(self.progress, color)])
        self.view.pb.set_text(['PB: ', get_timer_display(pb, 'title normal')])


    def go_next_split(self):
        if self.current_split:
            self.current_split.stop()

        self.current_split_idx += 1

        if self.current_split_idx >= len(self.splits):
            self.stop()
            return False

        self.current_split.progress_start = self.progress

        return True

    def start(self):
        self.view.set_enabled(True)
        self.paused = False
        self.progress = 0
        self.current_split_idx = 0
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

        if k == ' ':
            self.pause()

        if k == 'r' and self.current_split:
            self.paused = True
            for split in self.splits:
                split.reset()
            self.stop()
            self.progress = 0
            self.update()

        if k in ('s', 'g'):
            # s = save of pb
            # g = save only golds

            with open('route.yml', 'w', encoding='utf-8') as fp:
                route = []
                for split in self.splits:
                    split.bpt = split.new_bpt
                    if k == 's':
                        split.pb = split.new_pb

                    route.append({
                        'name': split.name,
                        'description': split.description,
                        'pb': split.pb,
                        'bpt': split.bpt,
                        'color': split.color,
                        'stats': split.stats,
                        'build': split.build,
                    })
                yaml.dump({'route': route}, fp)

        if k in ('q','Q'):
            raise urwid.ExitMainLoop()

if __name__ == '__main__':
    Spliter().main()
