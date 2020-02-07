# flake8: noqa
import argparse
import asyncio
import copy
import logging
import os
import sys

from kafka_logger.handlers import KafkaLoggingHandler

from repour.lib.logs import file_callback_log

logger = logging.getLogger(__name__)


class ContextLogRecord(logging.LogRecord):
    no_context_found = "NoContext"

    # TODO: at some point we'll probably just have to scan for 'log-*' stuff to clean this up
    def __init__(self, *args, **kwargs):

        super().__init__(*args, **kwargs)

        if self.has_event_loop():
            task = asyncio.Task.current_task()
        else:
            task = None
        if task is not None:
            # shallow copy the mdc. this is needed since logging is async and
            # could be sent after changes in the mdc object. So we want to
            # capture the mdc object at the time the log was submitted, not
            # afterwards
            self.mdc = copy.copy(getattr(task, "mdc", {}))
            self.log_context = getattr(task, "log_context", self.no_context_found)
        else:
            self.log_context = self.no_context_found

    def has_event_loop(self):
        try:
            asyncio.get_event_loop()
            return True
        except RuntimeError:
            return False


#
# Subcommands
#
def run_container_subcommand(args):
    from .server import server

    # Log to stdout/stderr only (no file)
    kafka_server = os.environ.get("REPOUR_KAFKA_SERVER")
    kafka_topic = os.environ.get("REPOUR_KAFKA_TOPIC")
    kafka_cafile = os.environ.get("REPOUR_KAFKA_CAFILE")

    configure_logging(
        args.log,
        kafka_server=kafka_server,
        kafka_topic=kafka_topic,
        kafka_cafile=kafka_cafile,
    )

    # Read required config from env vars, most of it is hardcoded though
    missing_envs = []

    def required_env(name, desc):
        val = os.environ.get(name, None)
        # Val should not be empty or None
        if not val:
            missing_envs.append((name, desc))
        return val

    da_url = required_env(
        "REPOUR_PME_DA_URL", "The REST endpoint required by PME to look up GAVs"
    )
    repour_url = required_env("REPOUR_URL", "Repour's URL")

    repo_provider = {"type": "modeb", "params": {}}

    if missing_envs:
        print("Missing environment variable(s):")
        for missing_env in missing_envs:
            print("{m[0]} ({m[1]})".format(m=missing_env))
        return 2

    # Go
    server.start_server(
        bind={"address": None, "port": 7331},
        repo_provider=repo_provider,
        repour_url=repour_url,
        adjust_provider={
            "type": "subprocess",
            "params": {
                "description": "PME",
                "cmd": [
                    "java",
                    "-jar",
                    os.path.join(os.getcwd(), "pom-manipulation-cli.jar"),
                    "-s",
                    "/home/repour/settings.xml",
                    "-DrestMaxSize=30",
                    "-DrestURL=" + da_url,
                    "-DversionIncrementalSuffix=redhat",
                    "-DallowConfigFilePrecedence=true",
                    "-DrepoReportingRemoval=true",
                    "-DdependencySource=REST",
                    "-DrepoRemovalBackup=repositories-backup.xml",
                ],
                "log_context_option": "--log-context",
                "send_log": False,  # enable when PNC central logging is ready
            },
        },
    )


#
# General
#
def create_argparser():
    parser = argparse.ArgumentParser(description="Run repour server in various modes")
    parser.add_argument(
        "-l",
        "--log",
        default="INFO",
        help="Override the path for the log file provided in the config file.",
    )

    subparsers = parser.add_subparsers()

    run_container_desc = "Run the server in a container environment"
    run_container_parser = subparsers.add_parser(
        "run-container", help=run_container_desc
    )
    run_container_parser.description = run_container_desc
    run_container_parser.set_defaults(func=run_container_subcommand)

    return parser


def configure_logging(
    default_level,
    log_path=None,
    kafka_server=None,
    kafka_topic=None,
    kafka_cafile=None,
):
    logging.setLogRecordFactory(ContextLogRecord)

    formatter = logging.Formatter(
        fmt="{asctime} [{levelname}] [{log_context}] {name}:{lineno} {message}",
        style="{",
    )

    formatter_callback = logging.Formatter(
        fmt="{asctime} [{levelname}] {name}:{lineno} {message}", style="{"
    )

    root_logger = logging.getLogger()

    if log_path is not None:
        file_log = logging.FileHandler(log_path)
        file_log.setFormatter(formatter)
        root_logger.addHandler(file_log)

    console_log = logging.StreamHandler()
    console_log.setFormatter(formatter)
    root_logger.addHandler(console_log)

    callback_id_log = file_callback_log.FileCallbackHandler()
    callback_id_log.setFormatter(formatter_callback)
    root_logger.addHandler(callback_id_log)

    # Cleanup of old log files
    asyncio.get_event_loop().create_task(file_callback_log.setup_clean_old_logfiles())

    root_logger.setLevel(getattr(logging, default_level))

    if kafka_server and kafka_topic and kafka_cafile:
        logger.info("Setting up Kafka logging handler")
        # we only care if you fail, kafka
        logger_kafka = logging.getLogger("kafka")
        logger_kafka.setLevel(logging.ERROR)

        kafka_handler_obj = KafkaLoggingHandler(
            kafka_server,
            kafka_topic,
            log_preprocess=[adjust_kafka_timestamp],
            ssl_cafile=kafka_cafile,
        )
        root_logger.addHandler(kafka_handler_obj)


def adjust_kafka_timestamp(data):
    """
    This is needed for the log-event-duration service to work properly
    """
    if data is not None and "timestamp" in data:
        data["@timestamp"] = data["timestamp"]
        return data


def main():
    # Args
    parser = create_argparser()
    args = parser.parse_args()

    if "func" in args:
        sys.exit(args.func(args))
    else:
        parser.print_help()
        sys.exit(1)
