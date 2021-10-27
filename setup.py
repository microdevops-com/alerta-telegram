
from setuptools import setup, find_packages

version = '5.1.3-sysadmws-3'

setup(
    name="alerta-telegram",
    version=version,
    description='Alerta plugin for Telegram',
    url='https://github.com/sysadmws/alerta-telegram',
    license='MIT',
    author='Nick Satterly',
    author_email='nick.satterly@theguardian.com',
    packages=find_packages(),
    py_modules=['alerta_telegram'],
    install_requires=[
        'telepot',
        'jinja2'
    ],
    include_package_data=True,
    zip_safe=True,
    entry_points={
        'alerta.plugins': [
            'telegram = alerta_telegram:TelegramBot'
        ]
    }
)
