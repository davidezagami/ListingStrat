from logging import Logger
from typing import NoReturn, Callable, Dict, Optional, Tuple

from discord_webhook import DiscordWebhook
from telegram import Bot, Chat

from .models import FormatFunction, NotificationSettings


class NotificationBase:
    def __init__(self, name: str) -> NoReturn:
        self.name = name
        self.settings = NotificationSettings(message=True, error=True, warning=True, info=True, debug=True)
        self.default_format_fn = self._default_format_fn

    def _default_format_fn(self, message: str, *args, **kwargs):
        return message

    def _format(self, service, message: str, format_fn: Optional[FormatFunction] = None,
                fn_args: Optional[Tuple] = None,
                fn_kwargs: Optional[Dict] = None, *args, **kwargs) -> str:
        if format_fn:
            return format_fn(service, message, fn_args, fn_kwargs)
        else:
            return self.default_format_fn(message, *args, **kwargs)

    def set_default_format_fn(self, format_fn: Callable) -> NoReturn:
        self.default_format_fn = format_fn

    def clear_default_format_fn(self) -> NoReturn:
        self.default_format_fn = self._default_format_fn

    def _send(self, message: str, format_fn: Optional[FormatFunction] = None, *args, **kwargs) -> NoReturn:
        raise NotImplementedError

    def message(self, message: str, format_fn: Optional[FormatFunction] = None, fn_args: Optional[Tuple] = None,
                fn_kwargs: Optional[Dict] = None, *args, **kwargs) -> NoReturn:
        raise NotImplementedError

    def error(self, message: str, format_fn: Optional[FormatFunction] = None, fn_args: Optional[Tuple] = None,
              fn_kwargs: Optional[Dict] = None, *args, **kwargs) -> NoReturn:
        raise NotImplementedError

    def warning(self, message: str, format_fn: Optional[FormatFunction] = None, fn_args: Optional[Tuple] = None,
                fn_kwargs: Optional[Dict] = None, *args, **kwargs) -> NoReturn:
        raise NotImplementedError

    def info(self, message: str, format_fn: Optional[FormatFunction] = None, fn_args: Optional[Tuple] = None,
             fn_kwargs: Optional[Dict] = None, *args, **kwargs) -> NoReturn:
        raise NotImplementedError

    def debug(self, message: str, format_fn: Optional[FormatFunction] = None, fn_args: Optional[Tuple] = None,
              fn_kwargs: Optional[Dict] = None, *args, **kwargs) -> NoReturn:
        raise NotImplementedError


class Notification(NotificationBase):
    def __init__(self) -> NoReturn:
        super().__init__("GLOBAL")
        self.services = {}

    def _add(self, name: str, service: any):
        self.services[name] = service

    def add_logger(self, name: str, logger: Logger, settings: NotificationSettings):
        self._add(name, LoggerNotification(name, logger, settings))

    def add_discord(self, name: str, webhook_url: str, settings: NotificationSettings):
        service = DiscordNotification(name, webhook_url, settings)
        self.services[name] = service

    def add_telegram(self, name: str, token: str, chat_id: int, settings: NotificationSettings):
        service = TelegramNotification(name, token, chat_id, settings)
        self.services[name] = service

    def remove_service(self, name: str) -> NoReturn:
        del self.services[name]

    def get_service(self, name: str) -> any:
        return self.services[name]

    def set_global_settings(self, settings: NotificationSettings):
        self.settings = settings

    def _send(self, message: str, *args, **kwargs) -> NoReturn:
        raise NotImplementedError

    def message(self, message: str, format_fn: Optional[FormatFunction] = None, fn_args: Optional[Tuple] = None,
                fn_kwargs: Optional[Dict] = None, *args, **kwargs) -> NoReturn:
        if self.settings.message:
            [_.message(self._format(_, message, format_fn, fn_args, fn_kwargs, *args, **kwargs), *args, **kwargs) for _
             in self.services.values()]

    def error(self, message: str, format_fn: Optional[FormatFunction] = None, fn_args: Optional[Tuple] = None,
              fn_kwargs: Optional[Dict] = None, *args, **kwargs) -> NoReturn:
        if self.settings.error:
            [_.error(self._format(_, message, format_fn, fn_args, fn_kwargs, *args, **kwargs), *args, **kwargs) for _ in
             self.services.values()]

    def warning(self, message: str, format_fn: Optional[FormatFunction] = None, fn_args: Optional[Tuple] = None,
                fn_kwargs: Optional[Dict] = None, *args, **kwargs) -> NoReturn:
        if self.settings.warning:
            [_.warning(self._format(_, message, format_fn, fn_args, fn_kwargs, *args, **kwargs), *args, **kwargs) for _
             in self.services.values()]

    def info(self, message: str, format_fn: Optional[FormatFunction] = None, fn_args: Optional[Tuple] = None,
             fn_kwargs: Optional[Dict] = None, *args, **kwargs) -> NoReturn:
        if self.settings.info:
            [_.info(self._format(_, message, format_fn, fn_args, fn_kwargs, *args, **kwargs), *args, **kwargs) for _ in
             self.services.values()]

    def debug(self, message: str, format_fn: Optional[FormatFunction] = None, fn_args: Optional[Tuple] = None,
              fn_kwargs: Optional[Dict] = None, *args, **kwargs) -> NoReturn:
        if self.settings.debug:
            [_.debug(self._format(_, message, format_fn, fn_args, fn_kwargs, *args, **kwargs), *args, **kwargs) for _ in
             self.services.values()]


class LoggerNotification(NotificationBase):
    def __init__(self, name: str, logger: Logger, settings: NotificationSettings, ):
        super().__init__(name)
        self.logger = logger
        self.settings = settings

    def _send(self, message: str, *args, **kwargs) -> NoReturn:
        raise NotImplementedError

    def message(self, message: str, format_fn: Optional[FormatFunction] = None, fn_args: Optional[Tuple] = None,
                fn_kwargs: Optional[Dict] = None, *args, **kwargs) -> NoReturn:
        if self.settings.message:
            msg = self._format(self, message, format_fn, fn_args, fn_kwargs, *args, **kwargs)
            self.logger.warning(msg, *args, **kwargs)

    def error(self, message: str, format_fn: Optional[FormatFunction] = None, fn_args: Optional[Tuple] = None,
              fn_kwargs: Optional[Dict] = None, *args, **kwargs) -> NoReturn:
        if self.settings.error:
            msg = self._format(self, message, format_fn, fn_args, fn_kwargs, *args, **kwargs)
            self.logger.error(msg, *args, **kwargs)

    def warning(self, message: str, format_fn: Optional[FormatFunction] = None, fn_args: Optional[Tuple] = None,
                fn_kwargs: Optional[Dict] = None, *args, **kwargs) -> NoReturn:
        if self.settings.warning:
            msg = self._format(self, message, format_fn, fn_args, fn_kwargs, *args, **kwargs)
            self.logger.warning(msg, *args, **kwargs)

    def info(self, message: str, format_fn: Optional[FormatFunction] = None, fn_args: Optional[Tuple] = None,
             fn_kwargs: Optional[Dict] = None, *args, **kwargs) -> NoReturn:
        if self.settings.info:
            msg = self._format(self, message, format_fn, fn_args, fn_kwargs, *args, **kwargs)
            self.logger.info(msg, *args, *kwargs)

    def debug(self, message: str, format_fn: Optional[FormatFunction] = None, fn_args: Optional[Tuple] = None,
              fn_kwargs: Optional[Dict] = None, *args, **kwargs) -> NoReturn:
        if self.settings.debug:
            msg = self._format(self, message, format_fn, fn_args, fn_kwargs, *args, **kwargs)
            self.logger.debug(msg, *args, **kwargs)


class ChatNotification(NotificationBase):
    def __init__(self, name: str):
        super().__init__(name)

    def _send(self, message: str, *args, **kwargs):
        raise NotImplementedError

    def message(self, message: str, format_fn: Optional[FormatFunction] = None, fn_args: Optional[Tuple] = None,
                fn_kwargs: Optional[Dict] = None, *args, **kwargs) -> NoReturn:
        if self.settings.message:
            msg = self._format(self, message, format_fn, fn_args, fn_kwargs, *args, **kwargs)
            self._send(msg, *args, **kwargs)

    def error(self, message: str, format_fn: Optional[FormatFunction] = None, fn_args: Optional[Tuple] = None,
              fn_kwargs: Optional[Dict] = None, *args, **kwargs) -> NoReturn:
        if self.settings.error:
            msg = self._format(self, message, format_fn, fn_args, fn_kwargs, *args, **kwargs)
            self._send(msg, *args, **kwargs)

    def warning(self, message: str, format_fn: Optional[FormatFunction] = None, fn_args: Optional[Tuple] = None,
                fn_kwargs: Optional[Dict] = None, *args, **kwargs) -> NoReturn:
        if self.settings.warning:
            msg = self._format(self, message, format_fn, fn_args, fn_kwargs, *args, **kwargs)
            self._send(msg, *args, **kwargs)

    def info(self, message: str, format_fn: Optional[FormatFunction] = None, fn_args: Optional[Tuple] = None,
             fn_kwargs: Optional[Dict] = None, *args, **kwargs) -> NoReturn:
        if self.settings.info:
            msg = self._format(self, message, format_fn, fn_args, fn_kwargs, *args, **kwargs)
            self._send(msg, *args, **kwargs)

    def debug(self, message: str, format_fn: Optional[FormatFunction] = None, fn_args: Optional[Tuple] = None,
              fn_kwargs: Optional[Dict] = None, *args, **kwargs) -> NoReturn:
        if self.settings.debug:
            msg = self._format(self, message, format_fn, fn_args, fn_kwargs, *args, **kwargs)
            self._send(msg, *args, **kwargs)


class DiscordNotification(ChatNotification):
    def __init__(self, name: str, webhook_url: str, settings: NotificationSettings,
                 bot_config: Optional[Dict] = None) -> NoReturn:
        super().__init__(name)
        if bot_config:
            self.send_fn = DiscordWebhook(**bot_config)
        else:
            self.send_fn = DiscordWebhook(webhook_url)
        self.settings = settings

    def _send(self, message: str, *args, **kwargs):
        if message != '':
            self.send_fn.set_content(message)
            self.send_fn.execute()


class TelegramNotification(ChatNotification):
    def __init__(self, name: str, token: str, chat_id: int, settings: NotificationSettings,
                 bot_config: Optional[Dict] = None, chat_config: Optional[Dict] = None) -> NoReturn:
        super().__init__(name)

        if bot_config:
            self.bot = Bot(**bot_config)
        else:
            self.bot = Bot(token)

        self.chat_id = chat_id

        if chat_config:
            self.send_fn = Chat(**chat_config)
        else:
            self.send_fn = Chat(self.chat_id, "private", bot=self.bot)
        self.settings = settings

    def _send(self, message: str, *args, **kwargs):
        if message != '':
            self.send_fn.send_message(message)
