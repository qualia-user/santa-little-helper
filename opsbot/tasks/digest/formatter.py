from opsbot.models.types import DigestResult
from opsbot.services.slack_ui import ICONS, digest_result_blocks


def compose_digest_text(imap_user: str, result: DigestResult) -> str:
    lines = [
        'Daily Email Digest',
        f'{result.emails_processed} email(s) processed from {imap_user}',
        '',
    ]

    if result.warnings:
        lines.append('Warnings:')
        for warning in result.warnings:
            lines.append(f'- {warning}')
        lines.append('')

    for level in ('high', 'medium', 'low'):
        items = result.groups.get(level, [])
        if not items:
            continue
        lines.append(f"{ICONS[level]} {level.capitalize()} Priority ({len(items)})")
        for item in items:
            lines.append(f"- {item.sender} - {item.subject}")
            lines.append(f"  {item.summary}")
        lines.append('')

    if result.emails_processed == 0:
        lines.append('No emails to process.')

    return '\n'.join(lines).strip()


def compose_digest_blocks(profile_name: str, result: DigestResult) -> list:
    return digest_result_blocks(profile_name=profile_name, result=result, include_actions=True)
