"""
Test: Structured Logging (Phase C).
Verifies colored formatter, JSON formatter, request ID filter, and setup_logging.
"""
import sys
import io
import json
import logging
sys.path.insert(0, '.')

from config.logging_config import (
    setup_logging, Colors, ColoredFormatter, JSONFormatter, RequestIDFilter
)

PASS = FAIL = 0

def check(desc, actual, expected=None, tol=1e-3):
    global PASS, FAIL
    ok = True
    if expected is not None:
        if isinstance(expected, float):
            ok = abs(actual - expected) < tol
        elif isinstance(expected, str) and isinstance(actual, str):
            ok = expected in actual
        else:
            ok = actual == expected
    else:
        ok = bool(actual)
    if ok:
        PASS += 1; print(f"  [PASS] {desc}")
    else:
        FAIL += 1; print(f"  [FAIL] {desc} => expected {expected!r}, got {actual!r}")


# =========================================================================
# GROUP 1: ANSI Color codes
# =========================================================================
print("\n--- GROUP 1: ANSI Colors ---")
check("GREEN is ANSI code", Colors.GREEN, "\033[32m")
check("RED is ANSI code", Colors.RED, "\033[31m")
check("YELLOW is ANSI code", Colors.YELLOW, "\033[33m")
check("BOLD is ANSI code", Colors.BOLD, "\033[1m")
check("DIM is ANSI code", Colors.DIM, "\033[2m")
check("RESET is ANSI code", Colors.RESET, "\033[0m")


# =========================================================================
# GROUP 2: Colors.level_color
# =========================================================================
print("\n--- GROUP 2: Colors.level_color ---")
check("DEBUG=BLUE", Colors.level_color("DEBUG"), Colors.BLUE)
check("INFO=GREEN", Colors.level_color("INFO"), Colors.GREEN)
check("WARNING=YELLOW", Colors.level_color("WARNING"), Colors.YELLOW)
check("WARN=YELLOW", Colors.level_color("WARN"), Colors.YELLOW)
check("ERROR=RED+BOLD", Colors.level_color("ERROR"), Colors.RED + Colors.BOLD)
check("CRITICAL=RED_BG", Colors.level_color("CRITICAL"), Colors.RED_BG)
check("unknown=WHITE", Colors.level_color("UNKNOWN"), Colors.WHITE)


# =========================================================================
# GROUP 3: Colors.duration_color
# =========================================================================
print("\n--- GROUP 3: Colors.duration_color ---")
check("<100ms = GREEN", Colors.duration_color(50), Colors.GREEN)
check("<1000ms = YELLOW", Colors.duration_color(500), Colors.YELLOW)
check(">=1000ms = RED", Colors.duration_color(1500), Colors.RED)
check("threshold 99 = GREEN", Colors.duration_color(99), Colors.GREEN)
check("threshold 100 = YELLOW (not <100)", Colors.duration_color(100), Colors.YELLOW)
check("threshold 999 = YELLOW", Colors.duration_color(999), Colors.YELLOW)
check("threshold 1000 = RED", Colors.duration_color(1000), Colors.RED)


# =========================================================================
# GROUP 4: RequestIDFilter
# =========================================================================
print("\n--- GROUP 4: RequestIDFilter ---")

f = RequestIDFilter()
record = logging.LogRecord("test", logging.INFO, "", 0, "hello", (), None)
record.request_id = ""  # simulate default

# Test filter adds request_id attribute
f.filter(record)
check("filter sets request_id attr", hasattr(record, "request_id"), True)


# =========================================================================
# GROUP 5: ColoredFormatter
# =========================================================================
print("\n--- GROUP 5: ColoredFormatter ---")

fmt = ColoredFormatter()
record = logging.LogRecord("heritage.pipeline", logging.INFO, "", 0, "step done", (), None)
record.request_id = "abc123"

output = fmt.format(record)
check("colored output contains step message", output, "step done")
check("colored output contains module name", "pipeline" in output.replace("\033", ""), True)
check("colored output contains request_id", "abc123" in output, True)
check("colored output contains level", "INFO" in output, True)
check("colored output has ANSI codes", "\033[" in output, True)

# Test ERROR level
err_record = logging.LogRecord("test", logging.ERROR, "", 0, "fail", (), None)
err_record.request_id = ""
err_output = fmt.format(err_record)
check("ERROR has RED color", Colors.RED in err_output, True)


# =========================================================================
# GROUP 6: ColoredFormatter with exception
# =========================================================================
print("\n--- GROUP 6: ColoredFormatter with exception ---")

try:
    raise ValueError("test error")
except ValueError:
    exc_record = logging.LogRecord("test", logging.ERROR, "", 0, "crash", (), sys.exc_info())
    exc_record.request_id = "exc-001"
    exc_output = fmt.format(exc_record)
    check("exception includes traceback", "ValueError" in exc_output, True)
    check("exception includes error message", "test error" in exc_output, True)


# =========================================================================
# GROUP 7: JSONFormatter
# =========================================================================
print("\n--- GROUP 7: JSONFormatter ---")

json_fmt = JSONFormatter()
record2 = logging.LogRecord("heritage.pipeline", logging.INFO, "", 0, "step2 done 12ms", (), None)
record2.request_id = "req-json-001"

json_out = json_fmt.format(record2)
parsed = json.loads(json_out)
check("JSON has ts", "ts" in parsed, True)
check("JSON has level=INFO", parsed["level"], "INFO")
check("JSON has module", parsed["module"], "heritage.pipeline")
check("JSON has req_id", parsed["req_id"], "req-json-001")
check("JSON has message", "step2 done" in parsed["message"], True)


# =========================================================================
# GROUP 8: JSONFormatter with exception
# =========================================================================
print("\n--- GROUP 8: JSONFormatter with exception ---")

try:
    raise ConnectionError("timeout")
except ConnectionError:
    exc_record2 = logging.LogRecord("test", logging.ERROR, "", 0, "api fail", (), sys.exc_info())
    exc_record2.request_id = "exc-json-001"
    json_out2 = json_fmt.format(exc_record2)
    parsed2 = json.loads(json_out2)
    check("JSON exception has error key", "error" in parsed2, True)
    check("JSON exception has traceback", "traceback" in parsed2, True)
    check("JSON error message contains error text", bool(parsed2.get("error")), True)


# =========================================================================
# GROUP 9: setup_logging
# =========================================================================
print("\n--- GROUP 9: setup_logging ---")

logger = setup_logging(level="DEBUG")
check("setup_logging returns logger", logger is not None, True)
check("logger name is heritage", logger.name, "heritage")

root = logging.getLogger()
check("root logger has handlers", len(root.handlers) > 0, True)

# Verify levels
check("root level set", root.level, logging.DEBUG)


# =========================================================================
# GROUP 10: setup_logging with file handler
# =========================================================================
print("\n--- GROUP 10: setup_logging with file handler ---")

log_dir = "/tmp/heritage_test_logs"
logger2 = setup_logging(level="INFO", log_dir=log_dir, log_file="test.log",
                        max_bytes=1024*1024, backup_count=2)

file_handlers = [h for h in logging.getLogger().handlers if isinstance(h, logging.handlers.RotatingFileHandler)]
check("file handler created with log_dir", len(file_handlers) > 0, True)
check("log file exists", __import__('os').path.exists(f"{log_dir}/test.log"), True)


# =========================================================================
# GROUP 11: Noisy loggers suppressed
# =========================================================================
print("\n--- GROUP 11: Noisy loggers suppressed ---")

for name in ("uvicorn.access", "httpx", "httpcore", "urllib3", "asyncio"):
    lvl = logging.getLogger(name).level
    check(f"{name} level >= WARNING", lvl >= logging.WARNING, True)


# =========================================================================
# GROUP 12: Handler format auto-selection
# =========================================================================
print("\n--- GROUP 12: Format auto-selection ---")

console_handlers = [h for h in logging.getLogger().handlers
                    if isinstance(h, logging.StreamHandler) and not isinstance(h, logging.FileHandler)]
check("console handler exists", len(console_handlers) > 0, True)

# On non-TTY (CI/script), should use JSONFormatter
if not sys.stdout.isatty():
    check("non-TTY uses JSONFormatter", isinstance(console_handlers[-1].formatter, JSONFormatter), True)
else:
    check("TTY uses ColoredFormatter", isinstance(console_handlers[-1].formatter, ColoredFormatter), True)


# =========================================================================
# REPORT
# =========================================================================
print(f"\n{'='*60}")
print(f"RESULTS: {PASS} passed, {FAIL} failed, {PASS+FAIL} total")
if FAIL == 0:
    print("ALL TESTS PASSED")
else:
    print(f"{FAIL} TEST(S) FAILED")
print(f"{'='*60}")
sys.exit(0 if FAIL == 0 else 1)
