import logging
import os

try:
    from alerta.plugins import app  # alerta >= 5.0
except ImportError:
    from alerta.app import app  # alerta < 5.0
from alerta.plugins import PluginBase

import telepot
from jinja2 import Template, UndefinedError

DEFAULT_TMPL = """
{% if customer %}Customer: `{{customer}}` {% endif %}

*[{{ status.capitalize() }}] {{ environment }} {{ severity.capitalize() }}*
{{ event | replace("_","\_") }} {{ resource.capitalize() }}

```
{{ text }}
```
"""

LOG = logging.getLogger('alerta.plugins.telegram')

TELEGRAM_TOKEN = app.config.get('TELEGRAM_TOKEN') \
                 or os.environ.get('TELEGRAM_TOKEN')
TELEGRAM_CHAT_ID = app.config.get('TELEGRAM_CHAT_ID') \
                   or os.environ.get('TELEGRAM_CHAT_ID')
TELEGRAM_WEBHOOK_URL = app.config.get('TELEGRAM_WEBHOOK_URL', None) \
                       or os.environ.get('TELEGRAM_WEBHOOK_URL')
TELEGRAM_TEMPLATE = app.config.get('TELEGRAM_TEMPLATE') \
                    or os.environ.get('TELEGRAM_TEMPLATE')
TELEGRAM_PROXY = app.config.get('TELEGRAM_PROXY') \
                 or os.environ.get('TELEGRAM_PROXY')
TELEGRAM_PROXY_USERNAME = app.config.get('TELEGRAM_PROXY_USERNAME') \
                          or os.environ.get('TELEGRAM_PROXY_USERNAME')
TELEGRAM_PROXY_PASSWORD = app.config.get('TELEGRAM_PROXY_PASSWORD') \
                          or os.environ.get('TELEGRAM_PROXY_PASSWORD')
TELEGRAM_SOUND_NOTIFICATION_SEVERITY = app.config.get('TELEGRAM_SOUND_NOTIFICATION_SEVERITY') \
                          or os.environ.get('TELEGRAM_SOUND_NOTIFICATION_SEVERITY')
TELEGRAM_FILTER_NOTIFICATION_SEVERITY = app.config.get('TELEGRAM_FILTER_NOTIFICATION_SEVERITY') \
                          or os.environ.get('TELEGRAM_FILTER_NOTIFICATION_SEVERITY')

DASHBOARD_URL = app.config.get('DASHBOARD_URL', '') \
                or os.environ.get('DASHBOARD_URL')

TELEGRAM_CHAT_ID_PER_CUSTOMER = app.config.get('TELEGRAM_CHAT_ID_PER_CUSTOMER')

# use all the same, but telepot.aio.api.set_proxy for async telepot
if all([TELEGRAM_PROXY, TELEGRAM_PROXY_USERNAME, TELEGRAM_PROXY_PASSWORD]):
    telepot.api.set_proxy(
        TELEGRAM_PROXY, (TELEGRAM_PROXY_USERNAME, TELEGRAM_PROXY_PASSWORD))
    LOG.debug('Telegram: using proxy %s', TELEGRAM_PROXY)
elif TELEGRAM_PROXY is not None:
    telepot.api.set_proxy(TELEGRAM_PROXY)
    LOG.debug('Telegram: using proxy %s', TELEGRAM_PROXY)

class TelegramBot(PluginBase):
    def __init__(self, name=None):

        self.bot = telepot.Bot(TELEGRAM_TOKEN)
        LOG.debug('Telegram: %s', self.bot.getMe())

        if TELEGRAM_WEBHOOK_URL and \
                        TELEGRAM_WEBHOOK_URL != self.bot.getWebhookInfo()['url']:
            self.bot.setWebhook(TELEGRAM_WEBHOOK_URL)
            LOG.debug('Telegram: %s', self.bot.getWebhookInfo())

        super(TelegramBot, self).__init__(name)
        if TELEGRAM_TEMPLATE:
            if os.path.exists(TELEGRAM_TEMPLATE):
                with open(TELEGRAM_TEMPLATE, 'r') as f:
                    self.template = Template(f.read())
            else:
                self.template = Template(TELEGRAM_TEMPLATE)
        else:
            self.template = Template(DEFAULT_TMPL)

    def pre_receive(self, alert):
        return alert

    def post_receive(self, alert, **kwargs):
        
        if alert.repeat:
            LOG.debug('Telegram alert filtered due to alert.repeat: id: %s, resource: %s, status: %s, severity: %s, previous_severity: %s', alert.id, alert.resource, alert.status, alert.severity, alert.previous_severity)
            return

        # Do not send notifications about new (previous severity == indeterminate) immediately closed alerts
        if alert.status == "closed" and alert.previous_severity == "indeterminate":
            LOG.info('Telegram alert filtered due to closed and previous_severity == indeterminate: id: %s, resource: %s, status: %s, severity: %s, previous_severity: %s', alert.id, alert.resource, alert.status, alert.severity, alert.previous_severity)
            return

        # If filter set - send only needed severities
        if TELEGRAM_FILTER_NOTIFICATION_SEVERITY:

            # By default do not send
            send_alert = False

            # If alert is closed - previous severity matters
            # Send only previous severity in list
            if alert.status == "closed":
                if alert.previous_severity in TELEGRAM_FILTER_NOTIFICATION_SEVERITY:
                    send_alert = True

            # For open alerts
            else:
                # If previous severity in list should be sent
                if alert.previous_severity in TELEGRAM_FILTER_NOTIFICATION_SEVERITY:
                    send_alert = True

                # If current severity in list should be send as well
                if alert.severity in TELEGRAM_FILTER_NOTIFICATION_SEVERITY:
                    send_alert = True
            
            # return (do not send) if send_alert == False
            if not send_alert:
                LOG.info('Telegram alert filtered due to send_alert == False: id: %s, resource: %s, status: %s, severity: %s, previous_severity: %s', alert.id, alert.resource, alert.status, alert.severity, alert.previous_severity)
                return

            LOG.info('Telegram alert not filtered: id: %s, resource: %s, status: %s, severity: %s, previous_severity: %s', alert.id, alert.resource, alert.status, alert.severity, alert.previous_severity)

        try:
            text = self.template.render(alert.__dict__)
        except UndefinedError:
            text = "Something bad has happened but also we " \
                   "can't handle your telegram template message."

        LOG.debug('Telegram: message=%s', text)

        if TELEGRAM_WEBHOOK_URL:
            keyboard = {
                'inline_keyboard': [
                    [
                        {'text': 'ack', 'callback_data': '/ack ' + alert.id},
                        {'text': 'close', 'callback_data': '/close ' + alert.id},
                        {'text': 'blackout',
                         'callback_data': '/blackout ' + alert.id}
                    ]
                ]
            }
        else:
            keyboard = None

        if TELEGRAM_SOUND_NOTIFICATION_SEVERITY:
            disable_notification = True
            if alert.severity in TELEGRAM_SOUND_NOTIFICATION_SEVERITY:
                disable_notification = False
        else:
            disable_notification = False

        LOG.debug('Telegram: post_receive sendMessage disable_notification=%s', str(disable_notification))

        try:
            if alert.customer in TELEGRAM_CHAT_ID_PER_CUSTOMER:
                tg_chat_id = TELEGRAM_CHAT_ID_PER_CUSTOMER[alert.customer]
            else:
                tg_chat_id = TELEGRAM_CHAT_ID
            response = self.bot.sendMessage(tg_chat_id,
                                            text,
                                            parse_mode='Markdown',
                                            disable_notification=disable_notification,
                                            reply_markup=keyboard)
        except telepot.exception.TelegramError as e:
            raise RuntimeError("Telegram: ERROR - %s, description= %s, json=%s",
                               e.error_code,
                               e.description,
                               e.json)
        except Exception as e:
            raise RuntimeError("Telegram: ERROR - %s", e)

        LOG.debug('Telegram: %s', response)

    def status_change(self, alert, status, summary, **kwargs):
        return
