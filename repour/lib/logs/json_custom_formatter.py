import socket
from pythonjsonlogger import jsonlogger
from datetime import datetime


class JsonCustomFormatter(jsonlogger.JsonFormatter):
    def add_fields(self, log_record, record, message_dict):
        super(JsonCustomFormatter, self).add_fields(log_record, record, message_dict)

        if not log_record.get("timestamp"):
            # this doesn't use record.created, so it is slightly off
            now = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S.%fZ")
            log_record["timestamp"] = now
            log_record["@timestamp"] = now

        if log_record.get("level"):
            log_record["level"] = log_record["level"].upper()
        else:
            log_record["level"] = record.levelname

        if not log_record.get("hostName"):
            log_record["hostName"] = socket.gethostname()
