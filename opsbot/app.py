from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler

from opsbot import settings
from opsbot.commands.ops_parser import CommandParseError, parse_command
from opsbot.db import get_connection, initialize_database
from opsbot.services import job_queue, slack_ui
from opsbot.services.profiles import ProfileInactiveError, ProfileNotFoundError, get_user_profile, user_can_run


initialize_database()
slack_app = App(token=settings.SLACK_BOT_TOKEN)


def _enqueue_command(*, user_id: str, channel_id: str | None, channel_name: str | None, command_text: str, task_name: str, args: dict, logger):
    logger.info('Queue insert attempt', extra={'user_id': user_id, 'channel_id': channel_id, 'job_type': task_name})
    job_id = job_queue.enqueue_job(
        job_type=task_name,
        slack_user_id=user_id,
        channel_id=channel_id,
        channel_name=channel_name,
        command_text=command_text,
        args=args,
    )
    logger.info('Queue insert success', extra={'user_id': user_id, 'channel_id': channel_id, 'job_type': task_name, 'job_id': job_id})

    with get_connection() as conn:
        position_ahead = job_queue.count_jobs_ahead(conn, job_id)

    return job_id, position_ahead


@slack_app.command('/ops')
def handle_ops_command(ack, body, respond, logger):
    raw_text = body.get('text', '').strip()
    user_id = body.get('user_id', '')
    channel_id = body.get('channel_id')
    channel_name = body.get('channel_name')

    logger.info('Slash command received', extra={'user_id': user_id, 'channel_id': channel_id, 'command_text': raw_text})
    ack()
    logger.info('Slash command ack sent', extra={'user_id': user_id, 'channel_id': channel_id})

    try:
        command = parse_command(raw_text)
    except CommandParseError as ex:
        respond({'response_type': 'ephemeral', 'text': str(ex)})
        return

    try:
        with get_connection() as conn:
            try:
                profile = get_user_profile(conn, user_id)
            except (ProfileNotFoundError, ProfileInactiveError) as ex:
                respond({'response_type': 'ephemeral', 'text': str(ex)})
                return

            if not user_can_run(profile, command.task_name):
                respond({'response_type': 'ephemeral', 'text': f'You are not allowed to run: {command.task_name}'})
                return

        job_id, position_ahead = _enqueue_command(
            user_id=user_id,
            channel_id=channel_id,
            channel_name=channel_name,
            command_text=command.raw_text,
            task_name=command.task_name,
            args=command.flags,
            logger=logger,
        )
        blocks = slack_ui.queue_accepted_blocks(job_id, position_ahead, command.raw_text)
        respond({'response_type': 'ephemeral', 'text': f'Job #{job_id} accepted.', 'blocks': blocks})
    except Exception:
        logger.exception('Queue insert failure', extra={'user_id': user_id, 'channel_id': channel_id, 'command_text': raw_text})
        respond({'response_type': 'ephemeral', 'text': 'Sorry, I could not queue that job right now. Please try again in a moment.'})


@slack_app.action('digest_run_again')
def handle_digest_run_again(ack, body, client, logger):
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
    job_id, ahead = _enqueue_command(
        user_id=user_id,
        channel_id=body['channel']['id'],
        channel_name=body['channel'].get('name'),
        command_text='digest run',
        task_name='digest.run',
        args={},
        logger=logger,
    )
    client.chat_postMessage(channel=body['channel']['id'], text=f'Queued digest job #{job_id}. Jobs ahead: {ahead}')


@slack_app.action('digest_show_last')
def handle_digest_show_last(ack, body, client, logger):
    ack()
    job_id, ahead = _enqueue_command(
        user_id=body['user']['id'],
        channel_id=body['channel']['id'],
        channel_name=body['channel'].get('name'),
        command_text='digest last',
        task_name='digest.last',
        args={},
        logger=logger,
    )
    client.chat_postMessage(channel=body['channel']['id'], text=f'Queued last digest lookup #{job_id}. Jobs ahead: {ahead}')


@slack_app.action('jobs_queue_status')
def handle_jobs_queue_status(ack, body, client, logger):
    ack()
    job_id, ahead = _enqueue_command(
        user_id=body['user']['id'],
        channel_id=body['channel']['id'],
        channel_name=body['channel'].get('name'),
        command_text='jobs queue',
        task_name='jobs.queue',
        args={},
        logger=logger,
    )
    client.chat_postMessage(channel=body['channel']['id'], text=f'Queued queue status lookup #{job_id}. Jobs ahead: {ahead}')


def main():
    if not settings.SLACK_BOT_TOKEN or not settings.SLACK_APP_TOKEN:
        raise RuntimeError('SLACK_BOT_TOKEN and SLACK_APP_TOKEN must be set.')
    SocketModeHandler(slack_app, settings.SLACK_APP_TOKEN).start()


if __name__ == '__main__':
    main()
