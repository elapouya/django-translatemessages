import codecs
import glob
import os
import re

import polib
from pathlib import Path
from django.core.management.base import BaseCommand, CommandError
from django.core.management.utils import find_command, is_ignored_path, popen_wrapper
import deep_translator


def has_bom(fn):
    with fn.open("rb") as f:
        sample = f.read(4)
    return sample.startswith(
        (codecs.BOM_UTF8, codecs.BOM_UTF16_LE, codecs.BOM_UTF16_BE)
    )


def is_writable(path):
    # Known side effect: updating file access/modified time to current time if
    # it is writable.
    try:
        with open(path, "a"):
            os.utime(path, None)
    except OSError:
        return False
    return True


class Command(BaseCommand):
    help = "Translates .po files."

    requires_system_checks = []

    program = "msgfmt"
    program_options = ["--check-format"]

    def add_arguments(self, parser):
        parser.add_argument(
            "args",
            metavar="app_label",
            nargs="*",
            help="Specify the app label(s) to create migrations for.",
        )
        parser.add_argument(
            "--source-lang",
            "-s",
            action="store",
            default="en",
            dest="source_lang",
            metavar="LANG",
            help="What language is used for msgid in .po files",
        )
        parser.add_argument(
            "--locale",
            "-l",
            action="append",
            default=[],
            help="Locale(s) to process (e.g. de_AT). Default is to process all. "
            "Can be used multiple times.",
        )
        parser.add_argument(
            "--exclude",
            "-x",
            action="append",
            default=[],
            help="Locales to exclude. Default is none. Can be used multiple times.",
        )
        parser.add_argument(
            "--ignore",
            "-i",
            action="append",
            dest="ignore_patterns",
            default=[],
            metavar="PATTERN",
            help="Ignore directories matching this glob-style pattern. "
            "Use multiple times to ignore more.",
        )

    def handle(self, *app_labels, **options):
        self.options = options
        self.source_lang = options["source_lang"]
        app_labels = set(app_labels)
        locale = options["locale"]
        exclude = options["exclude"]
        ignore_patterns = set(options["ignore_patterns"])
        self.verbosity = options["verbosity"]

        if find_command(self.program) is None:
            raise CommandError(
                "Can't find %s. Make sure you have GNU gettext "
                "tools 0.15 or newer installed." % self.program
            )

        basedirs = [os.path.join("conf", "locale"), "locale"]
        if os.environ.get("DJANGO_SETTINGS_MODULE"):
            from django.conf import settings

            basedirs.extend(settings.LOCALE_PATHS)

        # Walk entire tree, looking for locale directories
        for dirpath, dirnames, filenames in os.walk(".", topdown=True):
            for dirname in dirnames:
                if is_ignored_path(
                    os.path.normpath(os.path.join(dirpath, dirname)), ignore_patterns
                ):
                    dirnames.remove(dirname)
                elif dirname == "locale":
                    basedirs.append(os.path.join(dirpath, dirname))

        # Gather existing directories.
        basedirs = set(map(os.path.abspath, filter(os.path.isdir, basedirs)))

        if not basedirs:
            raise CommandError(
                "This script should be run from the Django Git "
                "checkout or your project or app tree, or with "
                "the settings module specified."
            )

        translatemessages_params = getattr(settings, "TRANSLATEMESSAGES_PARAMS", None)
        if not translatemessages_params:
            raise CommandError(
                "Please, define a TRANSLATEMESSAGES_PARAMS in your settings.py"
                " (See django-translatemessages documentation)"
            )
        if "translator" not in translatemessages_params:
            raise CommandError(
                "Not a valid TRANSLATEMESSAGES_PARAMS : translator is missing"
                " (See django-translatemessages documentation)"
            )

        # Get translator
        self.translator_cls = getattr(
            deep_translator,
            settings.TRANSLATEMESSAGES_PARAMS["translator"]["class"],
            None,
        )

        if not self.translator_cls:
            translators = ", ".join(
                cls for cls in deep_translator.__all__ if cls.endswith("Translator")
            )
            raise CommandError(
                f"Not a valid TRANSLATEMESSAGES_PARAMS : bad translator class.\n"
                f"Possible values are: "
                f"{translators}"
            )

        # Get translator params
        self.translator_params = settings.TRANSLATEMESSAGES_PARAMS["translator"].get(
            "params", {}
        )

        # Get other parameters from settings
        self.do_batch = settings.TRANSLATEMESSAGES_PARAMS.get("batch", False)
        extract_regex = settings.TRANSLATEMESSAGES_PARAMS.get("extract_regex")
        if isinstance(extract_regex, str):
            extract_regex = re.compile(extract_regex)
        if extract_regex:

            def filter_msgid(msgid):
                m = extract_regex.match(msgid)
                if m:
                    return m.group(1)

            self.filter_msgid = filter_msgid
        else:
            self.filter_msgid = lambda msgid: msgid

        # Build locale list
        all_locales = []
        for basedir in basedirs:
            locale_dirs = filter(os.path.isdir, glob.glob("%s/*" % basedir))
            all_locales.extend(map(os.path.basename, locale_dirs))

        # Account for excluded locales
        locales = locale or all_locales
        locales = set(locales).difference(exclude)

        self.has_errors = False
        for basedir in basedirs:
            if locales:
                dirs = [
                    os.path.join(basedir, locale, "LC_MESSAGES") for locale in locales
                ]
            else:
                dirs = [basedir]
            locations = []
            for ldir in dirs:
                for dirpath, dirnames, filenames in os.walk(ldir):
                    locations.extend(
                        (dirpath, f) for f in filenames if f.endswith(".po")
                    )
            if locations:
                self.translate_messages(locations)

        if self.has_errors:
            raise CommandError("compilemessages generated one or more errors.")

    def translate_messages(self, locations):
        for location in locations:
            path = Path(os.sep.join(location))
            self.translate_pofile(path)

    def translate_pofile(self, path):
        target_lang = path.parent.parent.name
        po = polib.pofile(path)
        self.stdout.write(
            self.style.WARNING(
                f"Translating {path} ({self.source_lang} -> {target_lang}) ..."
            )
        )
        translator_params = dict(
            self.translator_params,
            source=self.source_lang,
            target=target_lang,
        )
        translator = self.translator_cls(**translator_params)
        if self.do_batch:
            entries = [
                entry
                for entry in po
                if not entry.translated() and self.filter_msgid(entry.msgid)
            ]

            texts = [entry.msgid for entry in entries]
            translated_texts = self.translate_text_batch(texts, translator)
            for entry, translated_text in zip(entries, translated_texts):
                entry.msgstr = translated_text
                self.stdout.write(
                    self.style.SUCCESS(f"{entry.msgid} -> {translated_text}")
                )
        else:
            for entry in po:
                if not entry.translated():
                    filtered_msgid = self.filter_msgid(entry.msgid)
                    if filtered_msgid:
                        if translator.source != translator.target:
                            translated_text = self.translate_text(
                                filtered_msgid, translator
                            )
                        else:
                            translated_text = filtered_msgid
                        entry.msgstr = translated_text
                        self.stdout.write(
                            self.style.SUCCESS(f"{entry.msgid} -> {translated_text}")
                        )

        po.save()

    def translate_text(self, text, translator):
        translated_text = translator.translate(text)
        return translated_text

    def translate_text_batch(self, texts, translator):
        translated_texts = []
        if texts:
            filtered_texts = [self.filter_msgid(t) for t in texts]
            if translator.source != translator.target:
                translated_texts = translator.translate_batch(filtered_texts)
            else:
                translated_texts = filtered_texts
        return translated_texts
