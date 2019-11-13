import argparse
import asyncio
import logging
import os
import sys

from kafka_logger.handlers import KafkaLoggingHandler

from .logs import file_callback_log

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
            self.mdc = {}
            self.log_context = getattr(task, "log_context", self.no_context_found)

            self.mdc["userId"] = getattr(task, "log_user_id", None)
            self.mdc["requestContext"] = getattr(task, "log_request_context", None)
            self.mdc["processContext"] = getattr(task, "log_process_context", None)
            self.mdc["expires"] = getattr(task, "log_expires", None)
            self.mdc["tmp"] = getattr(task, "log_tmp", None)
        else:
            self.log_context = self.no_context_found

    def has_event_loop(self):
        try:
            asyncio.get_event_loop()
            return True
        except RuntimeError:
            return False


def override(config, config_coords, args, arg_name):
    if getattr(args, arg_name, None) is not None:

        def resolve_leaf_dict(parent_dict, leaf_coords):
            if len(leaf_coords) == 1:
                return parent_dict
            return resolve_leaf_dict(parent_dict[leaf_coords[0]], leaf_coords[1:])

        d = resolve_leaf_dict(config, config_coords)
        logger.debug(
            "Overriding config/{} with arg {}".format("/".join(config_coords), arg_name)
        )
        d[config_coords[-1]] = getattr(args, arg_name)


#
# Subcommands
#


def run_subcommand(args):
    from .server import server

    # Config
    config = load_config(args.config)
    override(config, ("log", "path"), args, "log")
    override(config, ("bind", "address"), args, "address")
    override(config, ("bind", "port"), args, "port")

    # Logging
    log_default_level = logging._nameToLevel[config["log"]["level"]]
    configure_logging(
        log_default_level, config["log"]["path"], args.verbose, args.quiet, args.silent
    )

    repo_provider = {"type": "modeb", "params": {}}

    # Go
    server.start_server(
        bind=config["bind"],
        repo_provider=repo_provider,
        adjust_provider=config["adjust_provider"],
    )


def run_container_subcommand(args):
    from .server import server

    # Log to stdout/stderr only (no file)
    kafka_server = os.environ.get("REPOUR_KAFKA_SERVER")
    kafka_topic = os.environ.get("REPOUR_KAFKA_TOPIC")
    kafka_cafile = os.environ.get("REPOUR_KAFKA_CAFILE")

    configure_logging(
        logging.INFO,
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
        "-v",
        "--verbose",
        action="count",
        default=0,
        help="Increase logging verbosity one level, repeatable.",
    )
    parser.add_argument(
        "-q",
        "--quiet",
        action="count",
        default=0,
        help="Decrease logging verbosity one level, repeatable.",
    )
    parser.add_argument(
        "-s", "--silent", action="store_true", help="Do not log to stdio."
    )
    parser.add_argument(
        "-l",
        "--log",
        help="Override the path for the log file provided in the config file.",
    )

    subparsers = parser.add_subparsers()

    run_desc = "Run the server"
    run_parser = subparsers.add_parser("run", help=run_desc)
    run_parser.description = run_desc
    run_parser.set_defaults(func=run_subcommand)
    run_parser.add_argument(
        "-c",
        "--config",
        default="config.json",
        help="Path to the configuration file. Default: config.json",
    )
    run_parser.add_argument(
        "-a",
        "--address",
        help="Override the bind IP address provided in the config file.",
    )
    run_parser.add_argument(
        "-p",
        "--port",
        help="Override the bind port number provided in the config file.",
    )

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
    verbose_count=0,
    quiet_count=0,
    silent=False,
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

    if not silent:
        console_log = logging.StreamHandler()
        console_log.setFormatter(formatter)
        root_logger.addHandler(console_log)

    callback_id_log = file_callback_log.FileCallbackHandler()
    callback_id_log.setFormatter(formatter_callback)
    root_logger.addHandler(callback_id_log)

    # Cleanup of old log files
    asyncio.get_event_loop().create_task(file_callback_log.setup_clean_old_logfiles())

    log_level = default_level + (10 * quiet_count) - (10 * verbose_count)
    root_logger.setLevel(log_level)

    if kafka_server and kafka_topic and kafka_cafile:
        logger.info("Setting up Kafka logging handler")
        # we only care if you fail, kafka
        logger_kafka = logging.getLogger("kafka")
        logger_kafka.setLevel(logging.ERROR)

        kafka_handler_obj = KafkaLoggingHandler(
            kafka_server, kafka_topic, ssl_cafile=kafka_cafile
        )
        root_logger.addHandler(kafka_handler_obj)


def load_config(config_path):
    import yaml
    from . import validation

    config_dir = os.path.dirname(config_path)

    def config_relative(loader, node):
        value = loader.construct_scalar(node)
        return os.path.abspath(os.path.join(config_dir, value))

    yaml.add_constructor("!config_relative", config_relative)

    with open(config_path, "r") as f:
        config = yaml.load(f)

    return validation.server_config(config)


def main():
    # Args
    parser = create_argparser()
    args = parser.parse_args()

    if "func" in args:
        sys.exit(args.func(args))
    else:
        parser.print_help()
        sys.exit(1)
