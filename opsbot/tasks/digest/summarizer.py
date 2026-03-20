import json
import re
import urllib.request

from opsbot.models.types import DigestConfig, RawEmail


OLLAMA_SYSTEM = (
    'You are an email triage assistant for a work email digest. '
    'Respond ONLY with a raw JSON object. No markdown, no explanation, no extra text. '
    'The JSON must have exactly two keys:\n'
    '  "summary": 1-2 sentences in plain language, grounded only in the email content. '
    'Do not invent roles, intent, or actions that are not explicitly stated.\n'
    '  "urgency": exactly one of "high", "medium", or "low".\n\n'
    'Urgency rules - apply the FIRST rule that matches:\n'
    '  high   - production incidents, outages, payment problems, security issues, customer-reported bugs, '
    'direct support requests, explicit deadlines, or requests requiring action today\n'
    '  medium - relevant work emails that may need follow-up later, scheduling changes, date corrections, '
    'non-urgent informational updates, or internal coordination\n'
    '  low    - newsletters, marketing, automated emails, event announcements, invitations, concert/ticket emails, '
    'promotions, social messages, FYIs with no direct ask, and forwarded content with no action required\n\n'
    'Important:\n'
    '  - Concerts, promotions, entertainment, ticket offers, and event announcements are LOW unless the email explicitly '
    'states an urgent work action is required.\n'
    '  - Do not infer urgency from enthusiastic wording alone.\n'
    '  - Do not guess missing context.\n'
    '  - When uncertain, choose the LOWER urgency.\n'
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
