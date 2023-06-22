========================
django-translatemessages
========================

Django app for translating Django .po files.
It uses `deep-translator <https://pypi.org/project/deep-translator/>`_ and
`polib <https://github.com/izimobil/polib/>`_

Installation
------------

when using pip::

    pip install django-translatemessages

When using poetry::

    poetry add django-translatemessages


Configuration
-------------

You must declare in your ``settings.py`` what translator to use and its params.
Please refer to `deep-translator Translators <https://deep-translator.readthedocs.io/en/latest/usage.html>`_
to know what parameters to specify (Note that ``django-translatemessages`` automatically add ``source`` and ``target`` parameters)

To configure GoogleTranslator, add in your ``settings.py``::

    TRANSLATEMESSAGES_PARAMS = {
        "translator": {
            "class": "GoogleTranslator",
            "params": {},
        },
    }


To configure DeeplTranslator, you will need an API key, add in your ``settings.py``::

    TRANSLATEMESSAGES_PARAMS = {
        "translator": {
            "class": "DeeplTranslator",
            "params": {
                "api_key": "your deepl api key",
            },
        },
    }

A good pratice in a Django application is to encapsulate strings to be translated into square brakets,
thus, you will noticed at once what strings has not been translated yet.
You can ask ``django-translatemessages`` to extract the string to translate from the source string.
Use a regex which selects with parentheses the text to extract. Note that if there is no match, the translation will not occur.

For example if you want to translate ``[my english string]`` into ``my french string`` with deepl, put in ``settings.py``::

    TRANSLATEMESSAGES_PARAMS = {
        "extract_regex": r"\[(.*)\]",
        "translator": {
            "class": "DeeplTranslator",
            "params": {
                "api_key": "your deepl api key",
            },
        },
    }

The source language is ``en`` by default, but you can use another one in your ``settings.py``::

    TRANSLATEMESSAGES_PARAMS = {
        "source_lang": "fr",
        ...
    }

**IMPORTANT :** By default, ``django-translatemessages`` will produce translations with the flag ``fuzzy``.
This force the developer to validate manually each translation.

To do so, edit each ``django.po`` file, search for the line ``#, fuzzy`` and remove it if you agree with the proposed translation. If you do not do this,
Django will not display the translation. You can also use `poedit <https://poedit.net/>`_
and press ``CTRL + RETURN`` on each highlighted translation you agree.

To disable auto-fuzzy feature, use this in your ``settings.py``::

    TRANSLATEMESSAGES_PARAMS = {
        "auto_fuzzy": False,
        ...
    }


Usage
-----

To auto-translate all languages in all apps::

    python ./manage.py translatemessages

Do not forget to do a ``makemessages`` before if needed (See Django documentation)

For more options, run ``python ./manage.py translatemessages -h``
