import argparse
import shlex
from typing import Dict, List

from opsbot.models.types import CommandRequest


class CommandParseError(ValueError):
    pass


class RaisingArgumentParser(argparse.ArgumentParser):
    def error(self, message):
        raise CommandParseError(message)


def _clean_flags(values: Dict) -> Dict:
    return {k: v for k, v in values.items() if v is not None}


def _parse_digest_run(rest: List[str]) -> Dict:
    parser = RaisingArgumentParser(prog='digest run', add_help=False)
    parser.add_argument('--hours', type=int)
    parser.add_argument('--max-emails', dest='max_emails', type=int)
    return _clean_flags(vars(parser.parse_args(rest)))


def _parse_digest_test(rest: List[str]) -> Dict:
    parser = RaisingArgumentParser(prog='digest test', add_help=False)
    parser.add_argument('--max-emails', dest='max_emails', type=int)
    return _clean_flags(vars(parser.parse_args(rest)))


def _parse_no_flags(name: str, rest: List[str]) -> Dict:
    if rest:
        raise CommandParseError(f'{name} does not accept flags.')
    return {}


def usage_text() -> str:
    return (
        'Valid commands:\n'
        '/ops digest run [--hours N] [--max-emails N]\n'
        '/ops digest test [--max-emails N]\n'
        '/ops digest last\n'
        '/ops jobs status\n'
        '/ops jobs queue\n'
        '/ops system health\n'
        '/ops platform scan'
    )


def parse_command(raw_text: str) -> CommandRequest:
    text = (raw_text or '').strip()
    if not text:
        raise CommandParseError(usage_text())

    try:
        tokens = shlex.split(text)
    except ValueError as ex:
        raise CommandParseError(str(ex)) from ex

    if len(tokens) < 2:
        raise CommandParseError(usage_text())

    domain, action = tokens[0].lower(), tokens[1].lower()
    rest = tokens[2:]

    mapping = {
        ('digest', 'run'): ('digest.run', _parse_digest_run),
        ('digest', 'test'): ('digest.test', _parse_digest_test),
        ('digest', 'last'): ('digest.last', lambda args: _parse_no_flags('digest last', args)),
        ('jobs', 'status'): ('jobs.status', lambda args: _parse_no_flags('jobs status', args)),
        ('jobs', 'queue'): ('jobs.queue', lambda args: _parse_no_flags('jobs queue', args)),
        ('system', 'health'): ('system.health', lambda args: _parse_no_flags('system health', args)),
        ('platform', 'scan'): ('platform.scan', lambda args: _parse_no_flags('platform scan', args)),
    }

    if (domain, action) not in mapping:
        raise CommandParseError(usage_text())

    task_name, parser_func = mapping[(domain, action)]
    flags = parser_func(rest)

    return CommandRequest(
        raw_text=text,
        domain=domain,
        action=action,
        task_name=task_name,
        flags=flags,
    )
