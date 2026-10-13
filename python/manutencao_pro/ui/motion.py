from __future__ import annotations

from gi.repository import Adw, GLib, Gtk

_SLIDE_PX = 12


def fade(widget: Gtk.Widget, start: float, end: float, duration: int) -> None:
    previous = getattr(widget, "_mp_fade", None)
    if isinstance(previous, Adw.Animation):
        previous.skip()
    animation = Adw.TimedAnimation.new(
        widget,
        start,
        end,
        duration,
        Adw.CallbackAnimationTarget.new(widget.set_opacity),
    )
    animation.set_easing(Adw.Easing.EASE_OUT_CUBIC)
    widget._mp_fade = animation
    animation.play()


def spring_margin(widget: Gtk.Widget, start: float, end: float) -> None:
    previous = getattr(widget, "_mp_spring", None)
    if isinstance(previous, Adw.Animation):
        previous.skip()

    def apply_margin(value: float) -> None:
        widget.set_margin_start(max(0, int(round(value))))

    animation = Adw.SpringAnimation.new(
        widget,
        start,
        end,
        Adw.SpringParams.new(0.72, 1.0, 340.0),
        Adw.CallbackAnimationTarget.new(apply_margin),
    )
    widget._mp_spring = animation
    animation.play()


def play_entrance(widget: Gtk.Widget) -> None:
    widget.set_opacity(0)
    widget.set_margin_start(_SLIDE_PX)
    fade(widget, 0, 1, 220)
    spring_margin(widget, float(_SLIDE_PX), 0)


class ProgressPulse:
    def __init__(self, bar: Gtk.ProgressBar) -> None:
        self._bar = bar
        self._source = 0

    def start(self) -> None:
        if self._source:
            return
        self._bar.set_pulse_step(0.08)
        self._source = GLib.timeout_add(90, self._tick)

    def stop(self) -> None:
        if not self._source:
            return
        GLib.source_remove(self._source)
        self._source = 0

    def _tick(self) -> bool:
        if not self._source:
            return False
        self._bar.pulse()
        return True
