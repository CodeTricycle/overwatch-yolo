import logging
from colorama import init, Fore, Style
from core.settings import Settings

init(autoreset=True)

_TRACE = 5
_SUCCESS = 25
logging.addLevelName(_TRACE, "TRACE")
logging.addLevelName(_SUCCESS, "OK")


def _trace_inst(self, msg, *args, **kw):
    if self.isEnabledFor(_TRACE):
        self._log(_TRACE, msg, args, **kw)


def _success_inst(self, msg, *args, **kw):
    if self.isEnabledFor(_SUCCESS):
        self._log(_SUCCESS, msg, args, **kw)


logging.Logger.trace = _trace_inst
logging.Logger.success = _success_inst


def _resolve_level() -> int:
    table = {
        "TRACE": _TRACE, "DEBUG": logging.DEBUG, "INFO": logging.INFO,
        "SUCCESS": _SUCCESS, "WARNING": logging.WARNING,
        "ERROR": logging.ERROR, "CRITICAL": logging.CRITICAL,
    }
    return table.get(Settings.get("LOG_LEVEL", "INFO").upper(), logging.INFO)


_LEVEL_COLORS = {
    "TRACE": Fore.LIGHTBLACK_EX,
    "DEBUG": Fore.LIGHTBLUE_EX,
    "INFO": Fore.LIGHTWHITE_EX,
    "OK": Fore.LIGHTGREEN_EX,
    "WARNING": Fore.LIGHTYELLOW_EX,
    "ERROR": Fore.LIGHTRED_EX,
    "CRITICAL": Fore.RED + Style.BRIGHT,
}

_LEVEL_ICONS = {
    "TRACE": "··",
    "DEBUG": "──",
    "INFO": "──",
    "OK": "✓✓",
    "WARNING": "⚠⚠",
    "ERROR": "✗✗",
    "CRITICAL": "!!",
}

_TAG_COLORS = {
    "Router": Fore.CYAN,
    "Capture": Fore.MAGENTA,
    "Aim": Fore.LIGHTMAGENTA_EX,
    "UI": Fore.LIGHTGREEN_EX,
    "Model": Fore.LIGHTCYAN_EX,
    "Kalman": Fore.LIGHTBLUE_EX,
    "SHM": Fore.LIGHTYELLOW_EX,
    "IPC": Fore.LIGHTCYAN_EX,
    "Config": Fore.LIGHTGREEN_EX,
}


class _ConsoleFormatter(logging.Formatter):
    def format(self, record):
        lvl = record.levelname
        color = _LEVEL_COLORS.get(lvl, Fore.WHITE)
        icon = _LEVEL_ICONS.get(lvl, "──")
        tag = getattr(record, "tag", None)
        tag_str = ""
        if tag:
            tc = _TAG_COLORS.get(tag, Fore.LIGHTWHITE_EX)
            tag_str = f" {tc}{Style.BRIGHT}[{tag}]{Style.RESET_ALL}"

        ts = f"{Fore.LIGHTBLACK_EX}{Style.DIM}{self.formatTime(record, self.datefmt)}{Style.RESET_ALL}"
        lvl_str = f"{color}{Style.BRIGHT}{icon} {lvl:<7}{Style.RESET_ALL}"
        msg = f"{Fore.WHITE}{record.getMessage()}{Style.RESET_ALL}"

        return f"{ts} {lvl_str}{tag_str} {msg}"


class Log:
    _logger = logging.getLogger("VisionAim")
    _logger.setLevel(_resolve_level())

    _console = logging.StreamHandler()
    _console.setLevel(_TRACE)
    _console.setFormatter(_ConsoleFormatter(datefmt="%H:%M:%S"))
    _logger.addHandler(_console)

    @staticmethod
    def _fmt(*args):
        return " ".join(str(a) for a in args)

    @classmethod
    def _emit(cls, level_fn, tag, args):
        msg = cls._fmt(*args)
        record = cls._logger.makeRecord(
            cls._logger.name, level_fn, "", 0, msg, (), None
        )
        record.tag = tag
        cls._logger.handle(record)

    @classmethod
    def trace(cls, *args, tag=None):
        cls._emit(_TRACE, tag, args)

    @classmethod
    def debug(cls, *args, tag=None):
        cls._emit(logging.DEBUG, tag, args)

    @classmethod
    def info(cls, *args, tag=None):
        cls._emit(logging.INFO, tag, args)

    @classmethod
    def success(cls, *args, tag=None):
        cls._emit(_SUCCESS, tag, args)

    @classmethod
    def warning(cls, *args, tag=None):
        cls._emit(logging.WARNING, tag, args)

    @classmethod
    def warn(cls, *args, tag=None):
        cls.warning(*args, tag=tag)

    @classmethod
    def error(cls, *args, tag=None):
        cls._emit(logging.ERROR, tag, args)

    @classmethod
    def critical(cls, *args, tag=None):
        cls._emit(logging.CRITICAL, tag, args)

    @classmethod
    def fatal(cls, *args, tag=None):
        cls.critical(*args, tag=tag)
