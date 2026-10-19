#!/usr/bin/env python3
"""Entry point for Aniyori."""

import sys

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gio

from aniyori.window import AniyoriWindow


APP_ID = "io.github.sakibshahariar.Aniyori"


class AniyoriApplication(Adw.Application):
    def __init__(self):
        super().__init__(
            application_id=APP_ID,
            flags=Gio.ApplicationFlags.DEFAULT_FLAGS,
        )

    def do_activate(self):
        window = self.props.active_window
        if window is None:
            window = AniyoriWindow(application=self)
        window.present()


def main():
    app = AniyoriApplication()
    return app.run(sys.argv)


if __name__ == "__main__":
    raise SystemExit(main())
