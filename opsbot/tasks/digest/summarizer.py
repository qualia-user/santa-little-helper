import json
import re
import urllib.request

from opsbot.models.types import DigestConfig, RawEmail


OLLAMA_SYSTEM = (
    'You are an email triage assistant. '
    'Respond ONLY with a raw JSON object - no explanation, no markdown, no preamble, no postamble. '
    'The JSON must have exactly two keys:\n'
    '  "summary": 1-2 sentences in plain language: who sent it, what they want, and what action (if any) is needed.\n'
    '  "urgency": exactly one of "high", "medium", or "low".\n\n'
    'Urgency rules - apply the FIRST rule that matches:\n'
    '  high   - any of: production errors, payment issues, system outages, customer-reported bugs or discrepancies, '
    'direct support requests from clients, explicit deadlines, requests requiring action today\n'
    '  medium - any of: license agreements, invitations, event announcements, date corrections, informational updates '
    'that may require a future response\n'
    '  low    - any of: newsletters, automated system emails, FYIs with no required action, forwarded content with no direct ask\n\n'
    'When in doubt between two levels, choose the higher one.'
)


def parse_llm_json(text: str) -> dict:
    try:
        return json.loads(text)
    except (json.JSONDecodeError, ValueError):
        pass

    match = re.search(r'\{[^{}]*\}', text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group())
        except (json.JSONDecodeError, ValueError):
            pass

    stripped = text.strip()
    if stripped.startswith('{') and not stripped.endswith('}'):
        try:
            return json.loads(stripped + '}')
        except (json.JSONDecodeError, ValueError):
            pass

    return {}


def summarize_email(config: DigestConfig, email_item: RawEmail) -> tuple[str, str, bool]:
    prompt = f"Email:\nFrom: {email_item.sender}\nSubject: {email_item.subject}\nBody: {email_item.body}"

    payload = json.dumps(
        {
            'model': config.ollama_model,
            'system': OLLAMA_SYSTEM,
            'prompt': prompt,
            'stream': False,
            'num_predict': 200,
        }
    ).encode()

    try:
        req = urllib.request.Request(
            f'{config.ollama_base_url}/api/generate',
            data=payload,
            headers={'Content-Type': 'application/json'},
            method='POST',
        )
        with urllib.request.urlopen(req, timeout=config.ollama_timeout_sec) as resp:
            result = json.loads(resp.read())
            raw = result.get('response', '')
            raw = re.sub(r'```(?:json)?|```', '', raw).strip()
            parsed = parse_llm_json(raw)

            if not parsed:
                return 'Summary unavailable (parse error).', 'medium', False

            summary = parsed.get('summary') or 'Summary unavailable (empty response).'
            urgency = (parsed.get('urgency') or 'medium').lower()
            if urgency not in ('high', 'medium', 'low'):
                urgency = 'medium'
            return summary, urgency, True

    except Exception as ex:
        print(f"[Ollama] Error for '{email_item.subject}': {ex}")
        return 'Summary unavailable (Ollama error).', 'medium', False
