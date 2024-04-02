from typing import Literal, Type, Callable
from gi.repository import GObject
from gi._propertyhelper import Property


class Property(Property):
    """
    replace python's `property` built-in decorator with this decorator
    to get properties into your service object
    """

    def __init__(
        self,
        value_type: Type = str,
        default_value: object | None = None,
        name: str = "",
        description: str = "",
        flags: Literal[
            "r",
            "w",
            "rw",
            "readable",
            "writable",
            "read-write",
            "construct",
            "construct-only",
            "lax-validation",
            "static-name",
            "private",
            "static-nick",
            "static-blurb",
            "explicit-notify",
            "deprecated",
        ]
        | GObject.ParamFlags = "read-write",
        getter: Callable | None = None,
        setter: Callable | None = None,
        minimum: int | None = None,
        maximum: int | None = None,
        **kwargs,
    ):
        flags = (
            flags
            if isinstance(flags, GObject.ParamFlags)
            else {
                "r": GObject.ParamFlags.READABLE,
                "w": GObject.ParamFlags.WRITABLE,
                "rw": GObject.ParamFlags.READWRITE,
                "readable": GObject.ParamFlags.READABLE,
                "writable": GObject.ParamFlags.WRITABLE,
                "read-write": GObject.ParamFlags.READWRITE,
                "construct": GObject.ParamFlags.CONSTRUCT,
                "construct-only": GObject.ParamFlags.CONSTRUCT_ONLY,
                "lax-validation": GObject.ParamFlags.LAX_VALIDATION,
                "static-name": GObject.ParamFlags.STATIC_NAME,
                "private": GObject.ParamFlags.PRIVATE,
                "static-nick": GObject.ParamFlags.STATIC_NICK,
                "static-blurb": GObject.ParamFlags.STATIC_BLURB,
                "explicit-notify": GObject.ParamFlags.EXPLICIT_NOTIFY,
                "deprecated": GObject.ParamFlags.DEPRECATED,
            }.get(flags.lower(), GObject.ParamFlags.READWRITE)
        )
        super().__init__(
            type=value_type,
            default=default_value,
            nick=name,
            blurb=description,
            flags=flags,
            getter=getter,
            setter=setter,
            minimum=minimum,
            maximum=maximum,
            **kwargs,
        )

    def __get__(self, instance, klass):
        return super().__get__(instance, klass)

    def __set__(self, instance, value):
        return super().__set__(instance, value)

    def __call__(self, fget):
        return self.getter(fget)

    def getter(self, fget):
        return super().getter(fget)

    def setter(self, fset):
        return super().setter(fset)
