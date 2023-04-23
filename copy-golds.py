#!/usr/bin/python3

from pathlib import Path
import sys
import yaml


def main():
    if len(sys.argv) < 3:
        print(f'{sys.argv[0]} [pb] [run]')
        sys.exit(1)

    pb = yaml.safe_load(Path(sys.argv[1]).read_text('utf-8'))
    run = yaml.safe_load(Path(sys.argv[2]).read_text('utf-8'))

    for i in range(len(run['route'])):
        pb['route'][i]['bpt'] = run['route'][i]['bpt']

    Path(sys.argv[1]).write_text(yaml.dump(pb), 'utf-8')


if __name__ == '__main__':
    main()
