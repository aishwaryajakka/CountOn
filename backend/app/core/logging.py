"""Small JSON log formatter with explicit fields and no exception payloads."""
import json
import logging
from datetime import datetime,timezone
from app.core.config import get_settings
from app.core.observability import request_id


class StructuredFormatter(logging.Formatter):
    def format(self,record):
        value={'timestamp':datetime.fromtimestamp(record.created,timezone.utc).isoformat(),
            'level':record.levelname,'logger':record.name,'message':record.getMessage(),
            'request_id':request_id.get()}
        for key in ('method','route','status_code','user_id','expectation_id','integration_id','duration_ms','tool_name','result_status'):
            if hasattr(record,key):value[key]=getattr(record,key)
        return json.dumps(value,default=str)


def configure_logging():
    logging.basicConfig(level=get_settings().log_level)
    for handler in logging.getLogger().handlers:handler.setFormatter(StructuredFormatter())
    for name in ('sqlalchemy.engine','sqlalchemy.pool','psycopg','httpx','httpcore','httpx2','httpcore2'):
        logging.getLogger(name).setLevel(logging.WARNING)
