from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler

from opsbot import settings
from opsbot.commands.handlers import build_direct_response, is_direct_task
from opsbot.commands.ops_parser import CommandParseError, parse_command
from opsbot.db import get_connection, initialize_database
from opsbot.services import job_queue, slack_ui
from opsbot.services.profiles import ProfileInactiveError, ProfileNotFoundError, get_user_profile, user_can_run


initialize_database()
slack_app = App(token=settings.SLACK_BOT_TOKEN)


@slack_app.command('/ops')
def handle_ops_command(ack, body, logger):
    raw_text = body.get('text', '').strip()
    user_id = body.get('user_id', '')
    channel_id = body.get('channel_id')
    channel_name = body.get('channel_name')

    try:
        command = parse_command(raw_text)
    except CommandParseError as ex:
        ack({'response_type': 'ephemeral', 'text': str(ex)})
        return

    with get_connection() as conn:
        try:
            profile = get_user_profile(conn, user_id)
        except (ProfileNotFoundError, ProfileInactiveError) as ex:
            ack({'response_type': 'ephemeral', 'text': str(ex)})
            return

        if not user_can_run(profile, command.task_name):
            ack({'response_type': 'ephemeral', 'text': f'You are not allowed to run: {command.task_name}'})
            return

        if is_direct_task(command.task_name):
            ack(build_direct_response(conn, user_id, command))
            return

        job_id = job_queue.enqueue_job(
            conn=conn,
            job_type=command.task_name,
            slack_user_id=user_id,
            channel_id=channel_id,
            channel_name=channel_name,
            command_text=command.raw_text,
            args=command.flags,
        )
        position_ahead = job_queue.count_jobs_ahead(conn, job_id)
        blocks = slack_ui.queue_accepted_blocks(job_id, position_ahead, command.raw_text)
        ack({'response_type': 'ephemeral', 'text': f'Job #{job_id} accepted.', 'blocks': blocks})


@slack_app.action('digest_run_again')
def handle_digest_run_again(ack, body, client):
    ack()
    user_id = body['user']['id']
    with get_connection() as conn:
        try:
            profile = get_user_profile(conn, user_id)
        except (ProfileNotFoundError, ProfileInactiveError) as ex:
            channel = body['channel']['id']
            client.chat_postMessage(channel=channel, text=str(ex))
            return
        if not user_can_run(profile, 'digest.run'):
            client.chat_postMessage(channel=body['channel']['id'], text='You are not allowed to run digest.run')
            return
        job_id = job_queue.enqueue_job(
            conn=conn,
            job_type='digest.run',
            slack_user_id=user_id,
            channel_id=body['channel']['id'],
            channel_name=None,
            command_text='digest run',
            args={},
        )
        ahead = job_queue.count_jobs_ahead(conn, job_id)
    client.chat_postMessage(channel=body['channel']['id'], text=f'Queued digest job #{job_id}. Jobs ahead: {ahead}')


@slack_app.action('digest_show_last')
def handle_digest_show_last(ack, body, client):
    ack()
    with get_connection() as conn:
        response = build_direct_response(conn, body['user']['id'], parse_command('digest last'))
    client.chat_postMessage(channel=body['channel']['id'], text=response.get('text', 'Last digest'), blocks=response.get('blocks'))


@slack_app.action('jobs_queue_status')
def handle_jobs_queue_status(ack, body, client):
    ack()
    with get_connection() as conn:
        response = build_direct_response(conn, body['user']['id'], parse_command('jobs queue'))
    client.chat_postMessage(channel=body['channel']['id'], text=response.get('text', 'Queue status'), blocks=response.get('blocks'))


def main():
    if not settings.SLACK_BOT_TOKEN or not settings.SLACK_APP_TOKEN:
        raise RuntimeError('SLACK_BOT_TOKEN and SLACK_APP_TOKEN must be set.')
    SocketModeHandler(slack_app, settings.SLACK_APP_TOKEN).start()


if __name__ == '__main__':
    main()
