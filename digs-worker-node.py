import argparse
import asyncio

from digs import conf
from digs.common.utils import get_random_central_server
from digs.exc import ConfigurationError
from digs.worker.handlers import WorkerProtocol
from digs.messaging import persistent


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        '-c', '--conf', required=False, default="",
        help="Provide additional configuration file, on top of the default "
             "ones."
    )
    parser.add_argument(
        '-d', '--debug', action="store_true", default=False,
        help="Enable debug mode."
    )

    args = parser.parse_args()

    if 'worker' not in conf.settings:
        raise ConfigurationError("The configuration file does not have a "
                                 "'worker' section.")
    worker_settings = conf.settings['worker']

    rabbitmq_settings = {
        key.replace("rabbitmq.", ""): worker_settings[key]
        for key in worker_settings if key.startswith("rabbitmq.")
    }

    rabbitmq_settings['host'] = get_random_central_server()
    rabbitmq_settings['port'] = 25672

    loop = asyncio.get_event_loop()
    coro = persistent.create_persistent_listener(WorkerProtocol,
                                                 **rabbitmq_settings)
    listener = loop.run_until_complete(coro)
    loop.create_task(listener.basic_consume("jobs.mafft"))

    try:
        loop.run_forever()
    except KeyboardInterrupt:
        pass

    # Close the RabbitMQ connection
    loop.run_until_complete(persistent.wait_closed())

    loop.close()


if __name__ == '__main__':
    main()
