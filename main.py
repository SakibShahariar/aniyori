#!/usr/bin/env python3
"""Entry point for Aniyori."""

import sys

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gio, Gtk


APP_ID = "io.github.sakibshahariar.Aniyori"


class AniyoriWindow(Adw.ApplicationWindow):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.set_title("Aniyori")
        self.set_default_size(1000, 680)
        self.set_size_request(600, 420)

        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.set_content(root)

        header = Adw.HeaderBar()
        root.append(header)

        title = Adw.WindowTitle(title="Aniyori", subtitle="Your anime library")
        header.set_title_widget(title)

        add_button = Gtk.Button.new_from_icon_name("list-add-symbolic")
        add_button.set_tooltip_text("Add anime")
        add_button.add_css_class("suggested-action")
        add_button.connect("clicked", self._on_add_clicked)
        header.pack_end(add_button)

        self.toast_overlay = Adw.ToastOverlay()
        root.append(self.toast_overlay)

        content = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL,
            spacing=18,
            halign=Gtk.Align.CENTER,
            valign=Gtk.Align.CENTER,
        )
        content.set_margin_top(36)
        content.set_margin_bottom(36)
        content.set_margin_start(28)
        content.set_margin_end(28)
        self.toast_overlay.set_child(content)

        icon = Gtk.Image.new_from_icon_name("applications-graphics-symbolic")
        icon.set_pixel_size(64)
        icon.add_css_class("dim-label")
        content.append(icon)

        heading = Gtk.Label(label="Your anime journey starts here")
        heading.add_css_class("title-1")
        heading.set_wrap(True)
        heading.set_justify(Gtk.Justification.CENTER)
        content.append(heading)

        description = Gtk.Label(
            label="Connect an anime service to build your library, "
            "track episodes, and keep your progress in one place."
        )
        description.set_wrap(True)
        description.set_max_width_chars(54)
        description.set_justify(Gtk.Justification.CENTER)
        description.add_css_class("dim-label")
        content.append(description)

        connect_button = Gtk.Button(label="Get started")
        connect_button.add_css_class("suggested-action")
        connect_button.set_halign(Gtk.Align.CENTER)
        connect_button.connect("clicked", self._on_add_clicked)
        content.append(connect_button)

        footer = Gtk.Label(label="Early development · AniList integration coming later")
        footer.add_css_class("caption")
        footer.add_css_class("dim-label")
        footer.set_margin_bottom(16)
        root.append(footer)

    def _on_add_clicked(self, _button):
        self.toast_overlay.add_toast(
            Adw.Toast.new("Anime service setup will be added in a later milestone.")
        )


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
