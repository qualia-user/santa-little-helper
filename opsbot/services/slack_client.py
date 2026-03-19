from slack_sdk import WebClient


def build_client(bot_token: str) -> WebClient:
    return WebClient(token=bot_token)


def ensure_dm_channel(client: WebClient, user_id: str) -> str:
    response = client.conversations_open(users=user_id)
    return response['channel']['id']


def post_text(client: WebClient, channel: str, text: str) -> None:
    client.chat_postMessage(channel=channel, text=text)


def post_blocks(client: WebClient, channel: str, text: str, blocks: list) -> None:
    client.chat_postMessage(channel=channel, text=text, blocks=blocks)
