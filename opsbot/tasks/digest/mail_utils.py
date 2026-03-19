import re
from email.header import decode_header


def decode_str(value):
    if value is None:
        return ''
    parts = decode_header(value)
    result = []
    for part, charset in parts:
        if isinstance(part, bytes):
            result.append(part.decode(charset or 'utf-8', errors='replace'))
        else:
            result.append(part)
    return ' '.join(result)


def get_plain_body(msg):
    body = ''
    if msg.is_multipart():
        for part in msg.walk():
            content_type = part.get_content_type()
            disposition = str(part.get('Content-Disposition', ''))
            if content_type == 'text/plain' and 'attachment' not in disposition:
                charset = part.get_content_charset() or 'utf-8'
                payload = part.get_payload(decode=True) or b''
                body = payload.decode(charset, errors='replace')
                break
    else:
        charset = msg.get_content_charset() or 'utf-8'
        payload = msg.get_payload(decode=True) or b''
        body = payload.decode(charset, errors='replace')

    body = re.sub(r'<[^>]+>', ' ', body)
    body = re.sub(r'\s+', ' ', body).strip()
    return body[:500]
