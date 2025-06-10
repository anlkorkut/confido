import logging
import sys
import json
from datetime import datetime
from typing import Dict, Any

class JsonFormatter(logging.Formatter):
    """Custom formatter that outputs log records as JSON"""
    def format(self, record):
        log_data = {
            "timestamp": datetime.utcnow().isoformat(),
            "level": record.levelname,
            "name": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno
        }
        
        # Include exception info if available
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)
            
        # Include any extra attributes
        for key, value in record.__dict__.items():
            if key not in ["args", "asctime", "created", "exc_info", "exc_text", "filename",
                          "funcName", "id", "levelname", "levelno", "lineno", "module",
                          "msecs", "message", "msg", "name", "pathname", "process",
                          "processName", "relativeCreated", "stack_info", "thread", "threadName"]:
                log_data[key] = value
                
        return json.dumps(log_data)

def setup_logging(log_level: str = "INFO", json_output: bool = False):
    """Configure application logging"""
    # Map string log level to logging constants
    log_level_map = {
        "DEBUG": logging.DEBUG,
        "INFO": logging.INFO,
        "WARNING": logging.WARNING,
        "ERROR": logging.ERROR,
        "CRITICAL": logging.CRITICAL
    }
    level = log_level_map.get(log_level.upper(), logging.INFO)
    
    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(level)
    
    # Clear existing handlers
    for handler in root_logger.handlers:
        root_logger.removeHandler(handler)
    
    # Create console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(level)
    
    # Set formatter based on output type
    if json_output:
        formatter = JsonFormatter()
    else:
        formatter = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        )
    
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)
    
    # Configure specific loggers
    for logger_name, logger_level in [
        ("openai", logging.WARNING),  # Reduce noise from OpenAI library
        ("urllib3", logging.WARNING),  # Reduce noise from HTTP client
        ("sqlalchemy.engine", logging.WARNING)  # Reduce SQL query logging
    ]:
        logging.getLogger(logger_name).setLevel(logger_level)
    
    return root_logger

def get_logger(name: str) -> logging.Logger:
    """Get a logger with the specified name"""
    return logging.getLogger(name)

def log_request(logger: logging.Logger, request_type: str, data: Dict[str, Any]):
    """Log an API request with sensitive data masked"""
    # Create a copy of the data to avoid modifying the original
    safe_data = data.copy() if isinstance(data, dict) else {"data": str(data)}
    
    # Mask sensitive fields
    sensitive_fields = ["api_key", "password", "token", "secret", "credentials"]
    for field in sensitive_fields:
        if field in safe_data:
            safe_data[field] = "*****"
    
    logger.info("API Request: %s - %s", request_type, json.dumps(safe_data))

def log_response(logger: logging.Logger, request_type: str, status_code: int, data: Any = None):
    """Log an API response"""
    if data:
        # Truncate large responses
        if isinstance(data, dict) and "response" in data and isinstance(data["response"], str):
            if len(data["response"]) > 500:
                data["response"] = data["response"][:500] + "... [truncated]"
        
        logger.info("API Response: %s - Status: %d - %s", 
                   request_type, status_code, json.dumps(data) if isinstance(data, (dict, list)) else str(data))
    else:
        logger.info("API Response: %s - Status: %d", request_type, status_code)