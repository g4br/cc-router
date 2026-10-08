"""Explicit configuration migration; never overwrites without --write and backup."""
import argparse
import json
from pathlib import Path
from datetime import datetime, timezone
from candidates import validate_config


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('--write', type=Path, help='Destination; omit to print migrated JSON')
    args = parser.parse_args()
    try:
        config = validate_config(json.loads(args.source.read_text(encoding='utf-8')))
    except json.JSONDecodeError:
        parser.error('source: invalid JSON')
    content = json.dumps(config, ensure_ascii=False, indent=2) + '\n'
    if args.write:
        if args.write.exists():
            backup = args.write.with_name(args.write.name + '.' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%f') + '.bak')
            backup.write_bytes(args.write.read_bytes())
        args.write.write_text(content, encoding='utf-8')
    else:
        print(content, end='')


if __name__ == '__main__':
    main()
