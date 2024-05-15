# NOTE: for who's reading this, you're on your own, good luck.
from functools import partial
from fabric.service import Service, Signal, SignalContainer
from typing import Any, Callable
from gi.repository import GLib, Gio
from fabric.utils import snake_case_to_pascal_case, bulk_connect


def error_if_not_callable(func):
    assert callable(func), f"passed handler must be a callable function but not {func}"


class DBusProxyWrapper(Service):
    """
    a service that wraps a dbus proxy object
    made to implement features PyGObject's override lacks

    ---
    NOTE: don't use this service before the `ready` signal is emitted
    """

    __proxy_methods__: dict[str, Callable] = {}

    __proxy_getters__: dict[str, Callable] = {}

    __proxy_setters__: dict[str, Callable[[GLib.Variant, Any], Any]] = {}

    __proxy_notifiers__: dict[str, Callable[[GLib.Variant, Any], Any]] = {}

    __proxy_signals__: dict[str, Callable[[GLib.Variant, Any], Any]] = {}

    __gsignals__ = SignalContainer(
        Signal("ready"),
        Signal("changed"),
        Signal("name-lost"),
        Signal("proxy-own-error"),
        Signal("caching"),
        Signal("caching-error", args=(object,)),
        Signal("property-changed", args=(str, object)),
        Signal("signal", args=(str, object)),
    )

    def __init__(
        self,
        bus_name: str,
        bus_path: str,
        interface: str | None = None,
        flags: Gio.DBusProxyFlags = Gio.DBusProxyFlags.NONE,
        info: Gio.DBusInterfaceInfo | None = None,
        proxy: Gio.DBusProxy | None = None,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self.bus_name = bus_name
        self.bus_path = bus_path
        self.__ready__: bool = False
        self.__proxy__: Gio.DBusProxy | None = None or proxy
        self.__connection__: Gio.DBusConnection | None = (
            None if not proxy else proxy.get_connection()
        )
        self.__proxy_interface__ = interface
        self.__proxy_flags__ = flags
        self.__proxy_info__ = info
        self.do_load_decorated_handlers()
        self.do_acquire_proxy() if not self.__proxy__ or not self.__connection__ else None

    @classmethod
    def method_hook(cls, name: str | None = None):
        def decorator(func):
            actual = func if not isinstance(func, staticmethod) else func.__func__
            actual_name = name or snake_case_to_pascal_case(actual.__name__)
            actual.__proxy_handler__ = (actual_name, "method")
            return func

        return decorator

    @classmethod
    def property_hook(
        cls, name: str | None = None, setter: bool = False, notify: bool = False
    ):
        def decorator(func):
            actual = func if not isinstance(func, staticmethod) else func.__func__
            actual_name = name or snake_case_to_pascal_case(
                func_name[4:]
                if (func_name := actual.__name__).startswith(("set_", "get_"))
                else func_name
            )
            actual.getter = partial(cls.property_hook, actual_name, False, False)
            actual.setter = partial(cls.property_hook, actual_name, True, False)
            actual.notify = partial(cls.property_hook, actual_name, False, True)
            actual.__proxy_handler__ = (
                actual_name,
                ("property-getter" if not setter else "property-setter")
                if not notify
                else "property-notify",
            )
            return func

        return decorator

    @classmethod
    def signal_hook(cls, name: str | None = None):
        def decorator(func):
            actual = func if not isinstance(func, staticmethod) else func.__func__
            actual_name = name or snake_case_to_pascal_case(actual.__name__)
            actual.__proxy_handler__ = (actual_name, "signal")
            return func

        return decorator

    def register_method_hook(self, name: str, handler: Callable) -> None:
        error_if_not_callable(handler)
        self.__proxy_methods__[
            name or snake_case_to_pascal_case(handler.__name__)
        ] = handler
        return

    def register_property_hook(
        self, name: str, handler: Callable, setter: bool = False, notify: bool = False
    ) -> None:
        error_if_not_callable(handler)
        (
            (self.__proxy_getters__ if not setter else self.__proxy_setters__)
            if not notify
            else self.__proxy_notifiers__
        )[name or snake_case_to_pascal_case(handler.__name__)] = handler
        return

    def register_signal_hook(self, name: str, handler: Callable) -> None:
        error_if_not_callable(handler)
        self.__proxy_signals__[
            name or snake_case_to_pascal_case(handler.__name__)
        ] = handler
        return

    def do_acquire_proxy(self) -> None:
        if self.__ready__:
            raise RuntimeError("the proxy is already initialized and ready to use")

        def acquire_proxy_finish(
            _,
            result: Gio.AsyncResult,
            *args,
        ) -> None:
            proxy: Gio.DBusProxy | None = Gio.DBusProxy.new_for_bus_finish(result)
            if not proxy:
                return self.emit("proxy-own-error")
            self.__proxy__ = proxy
            self.__connection__ = proxy.get_connection()

            bulk_connect(
                self.__proxy__,
                {
                    "g-properties-changed": self.do_cache_proxy_properties,
                    "notify::g-name-owner": lambda *args: (
                        self.emit("name-lost")
                        if not self.__proxy__.get_name_owner()
                        else None
                    ),
                },
            )
            proxy.connect(
                "g-signal",
                self.do_handle_proxy_signal,
            )

            return self.emit("ready")

        return Gio.DBusProxy.new_for_bus(
            Gio.BusType.SYSTEM,
            self.__proxy_flags__,
            self.__proxy_info__,
            self.bus_name,
            self.bus_path,
            self.__proxy_interface__ or self.bus_name,
            None,
            acquire_proxy_finish,
            None,
        )

    def do_load_decorated_handlers(self) -> None:
        handlers = []
        for base in reversed(self.__class__.__mro__):
            for name, value in base.__dict__.items():
                try:
                    x = getattr(value, "__proxy_handler__")
                    assert isinstance(x, tuple) and len(x) == 2
                except:
                    continue
                else:
                    # this must be a registered handler
                    handlers.append(value)
        for handler in handlers:
            handler_info: tuple[str, str] = handler.__proxy_handler__
            match handler_info[1]:
                case "method":
                    self.register_method_hook(handler_info[0], handler)
                case "property-getter":
                    self.register_property_hook(handler_info[0], handler, False, False)
                case "property-setter":
                    self.register_property_hook(handler_info[0], handler, True, False)
                case "property-notify":
                    self.register_property_hook(handler_info[0], handler, False, True)
                case "signal":
                    self.register_signal_hook(handler_info[0], handler)
        return

    def do_handle_proxy_signal(
        self, _proxy: Gio.DBusProxy, unique_name: str, name: str, value: GLib.Variant
    ) -> None:
        # TODO: do something with the signal
        self.emit("signal", name, value)
        if handler := self.__proxy_signals__.get(name):
            handler(self, value)
        if self.__proxy_flags__ != Gio.DBusProxyFlags.DO_NOT_LOAD_PROPERTIES:
            self.do_cache_proxy_properties()
        return

    def do_notify_proxy_property(self, name: str, value: GLib.Variant) -> None:
        self.emit("property-changed", name, value)
        if (handler := self.__proxy_notifiers__.get(name)) is not None:
            return handler(self, value)
        return

    def do_cache_proxy_properties(
        self,
        _proxy: Gio.DBusProxy | None = None,
        props: GLib.Variant | None = None,
        *args,
    ) -> None:
        self.emit("caching")

        def unpack_properties(variant: GLib.Variant) -> dict:
            # there's no .deep_unpack(), this is a fix
            res = {}
            variant = variant.get_child_value(0)
            signature = variant.get_type_string()
            if signature.startswith("a{"):
                for i in range(variant.n_children()):
                    v = variant.get_child_value(i)
                    res[v.get_child_value(0).unpack()] = v.get_child_value(1)
            elif signature.startswith("{sv"):
                res[variant.get_child_value(0).unpack()] = variant.get_child_value(1)
            return res

        def set_proxy_properties_from_variant(variant: GLib.Variant):
            for prop_name, prop_value in unpack_properties(variant).items():
                prop_name: str
                prop_value: GLib.Variant
                self.do_notify_proxy_property(prop_name, prop_value)
                self.__proxy__.set_cached_property(prop_name, prop_value.get_variant())
            return

        if props is not None:
            set_proxy_properties_from_variant(props)
            return self.emit("changed")

        def cache_proxy_properties_finish(_, result: Gio.AsyncResult) -> None:
            try:
                props_var: GLib.Variant = self.__connection__.call_finish(result)
                if not props_var:
                    raise RuntimeError("can't get the properties variant")
            except Exception as e:
                return self.emit("caching-error", e)
            set_proxy_properties_from_variant(props_var)
            return self.emit("changed")

        return self.do_call_connection_method(  # "async"
            "GetAll",
            "org.freedesktop.DBus.Properties",
            GLib.Variant("(s)", [self.__proxy__.get_interface_name()]),
            GLib.VariantType("(a{sv})"),
            cache_proxy_properties_finish,
        )

    def do_get_proxy_property(self, name: str) -> Any | None:
        if not self.__proxy__ or not (prop := self.__proxy__.get_cached_property(name)):
            return None
        return prop.unpack()

    def do_set_proxy_property(
        self, name: str, value: GLib.Variant, **kwargs
    ) -> Any | None:
        return self.do_call_connection_method(
            "Set",
            "org.freedesktop.DBus.Properties",
            GLib.Variant("(ssv)", (self.__proxy__.get_interface_name(), name, value)),
        )

    def do_call_proxy_method(
        self,
        name: str,
        params: GLib.Variant,
        result_handler: Callable | None = None,
    ) -> Any | None:
        if result_handler and callable(result_handler):
            # asynchronous
            self.__proxy__.call(name, params, 0, -1, None, result_handler, None)
        else:
            # synchronous
            result = self.__proxy__.call_sync(name, params, 0, -1, None)
            return result.unpack() if result is not None else None

    def do_call_connection_method(
        self,
        name: str,
        interface_name: str,
        params: GLib.Variant,
        return_type: GLib.Variant | None = None,
        result_handler: Callable | None = None,
    ) -> Any | None:
        if result_handler and callable(result_handler):
            # asynchronous
            return self.__connection__.call(
                self.__proxy__.get_name(),
                self.__proxy__.get_object_path(),
                interface_name,
                name,
                params,
                return_type,
                Gio.DBusCallFlags.NONE,
                -1,  # no timeout
                None,
                result_handler,
            )
        else:
            # synchronous
            return self.__connection__.call_sync(
                self.__proxy__.get_name(),
                self.__proxy__.get_object_path(),
                interface_name,
                name,
                params,
                return_type,
                Gio.DBusCallFlags.NONE,
                -1,  # no timeout
                None,
            )

    def __getattribute__(self, name: str) -> Any:
        dest = super().__getattribute__(name)

        try:
            assert isinstance(dest, Callable) or callable(dest)
            handler_info = getattr(dest, "__proxy_handler__")
        except:
            return dest

        if handler_info[1] == "method":
            return lambda value=GLib.Variant("()", ()), *args, **kwargs: partial(
                self.do_call_proxy_method, handler_info[0], value
            )()

        fget = (
            partial(self.do_get_proxy_property, handler_info[0])
            if self.__proxy_getters__.get(handler_info[0]) is not None
            else None
        )
        fset = (
            partial(self.do_set_proxy_property, handler_info[0])
            if self.__proxy_setters__.get(handler_info[0]) is not None
            else None
        )

        callback = (
            (
                lambda *args, **kwargs: fset(*args, **kwargs)
                if len(args) >= 1 or len(kwargs) >= 1
                else fget()
            )
            if fget and fset
            else fset
            if fset and not fget
            else fget
            if fget and not fset
            else None
        )

        return callback or dest


class DBusClient(Service):
    """
    implementaion for a dbus client
    made to reduce repeated code
    """

    __gsignals__ = SignalContainer(Signal("name-own-error"), Signal("name-owned"))

    __bus_properties__: dict[
        str, Callable[[Gio.DBusMethodInvocation, Any], GLib.Variant]
    ] = {}
    __bus_methods__: dict[
        str, Callable[[Gio.DBusMethodInvocation, Any], GLib.Variant]
    ] = {}
    __bus_raw_handlers__: dict[
        str, Callable[[Gio.DBusMethodInvocation, Any], GLib.Variant]
    ] = {}

    def __init__(
        self, bus_name: str, bus_path: str, interface_node: Gio.DBusNodeInfo, **kwargs
    ) -> None:
        super().__init__(**kwargs)
        self.bus_name = bus_name
        self.bus_path = bus_path
        self.interface_node = interface_node
        self.__connection__: Gio.DBusConnection | None = None
        self.__registered__: bool = False

        # all aboard
        self.do_load_decorated_handlers()
        self.do_register()

    @classmethod
    def method_handler(cls, name: str | None = None):
        """
        decorator for registering a dbus method handler
        if the name of the method was not given
        the name of the decorated function (converted to pascal case)
        will be used instead

        ---
        this must be used like so
        ```python
        @decorator()
        ```
        but not like this
        ```python
        @decorator
        ```
        """

        def decorator(func):
            actual = func
            if isinstance(actual, staticmethod):
                actual = actual.__func__
            actual.__bus_handler__ = (
                name or snake_case_to_pascal_case(actual.__name__),
                "method",
            )
            return func

        return decorator

    @classmethod
    def property_handler(cls, name: str | None = None):
        """
        decorator for registering a dbus property handler
        if the name of the property was not given
        the name of the decorated function (converted to pascal case)
        will be used instead

        ---
        this must be called like so
        ```python
        @decorator()
        ```
        but not like this
        ```python
        @decorator
        ```
        """

        def decorator(func):
            actual = func
            if isinstance(actual, staticmethod):
                actual = actual.__func__
            actual.__bus_handler__ = (
                name or snake_case_to_pascal_case(actual.__name__),
                "property",
            )
            return func

        return decorator

    @classmethod
    def raw_handler(cls, name: str):
        """
        this will act like other registering decorators
        yet the difference here that you will receive raw calls
        ---
        examples of `name` can be:
            `"org.Fabric.fabric.Method"`/`"org.freedesktop.DBus.Properties.Get"`/`"org.freedesktop.DBus.Properties.Set"`

        this decorator is useful if you're looking for more flexibility

        NOTE: `name` must be passed unlike other decorators
        """
        assert isinstance(name, str), f"passed name must be a string not {name}"

        def decorator(func):
            actual = func
            if isinstance(actual, staticmethod):
                actual = actual.__func__
            actual.__bus_handler__ = (
                name,
                "raw",
            )
            return func

        return decorator

    def register_method_handler(self, name: str, handler: Callable) -> None:
        error_if_not_callable(handler)
        self.__bus_methods__[
            name or snake_case_to_pascal_case(handler.__name__)
        ] = handler
        return

    def register_property_handler(self, name: str, handler: Callable) -> None:
        error_if_not_callable(handler)
        self.__bus_properties__[
            name or snake_case_to_pascal_case(handler.__name__)
        ] = handler
        return

    def register_raw_handler(self, name: str, handler: Callable) -> None:
        error_if_not_callable(handler)
        self.__bus_raw_handlers__[name] = handler
        return

    def emit_bus_signal(self, name: str, value: GLib.Variant) -> None:
        return (
            self.__connection__.emit_signal(
                None,
                self.bus_path,
                self.bus_name,
                name,
                value,
            )
            if self.__connection__ is not None
            else None
        )

    def connect_bus_signal(
        self,
        name: str,
        handler: Callable,
        interface_name: str | None = None,
        object_path: str | None = None,
        sender_name: str | None = None,
    ):
        return self.__connection__.signal_subscribe(
            sender_name,  # sender
            interface_name,
            name,
            object_path,  # path
            None,
            Gio.DBusSignalFlags.NONE,
            handler,
            None,  # user_data
        )

    def do_register(self) -> int:
        if self.__registered__:
            raise RuntimeError("dbus client is already registered")

        def on_bus_acquired(
            conn: Gio.DBusConnection, name: str, user_data: object = None
        ):
            self.__registered__ = True
            self.__connection__ = conn
            for interface in self.interface_node.interfaces:
                interface: Gio.DBusInterface
                if interface.name == name:
                    conn.register_object(
                        self.bus_path, interface, self.do_handle_bus_call
                    )
            return

        return Gio.bus_own_name(
            Gio.BusType.SESSION,
            self.bus_name,
            Gio.BusNameOwnerFlags.NONE,
            on_bus_acquired,
            lambda *args: self.emit("name-owned"),
            lambda *args: self.emit("name-own-error"),
        )

    def do_load_decorated_handlers(self) -> None:
        handlers = []
        for base in reversed(self.__class__.__mro__):
            for name, value in base.__dict__.items():
                try:
                    x = getattr(value, "__bus_handler__")
                    assert isinstance(x, tuple) and len(x) == 2
                except:
                    continue
                else:
                    # this must be a registered handler
                    handlers.append(value)
        for handler in handlers:
            handler_info: tuple[str, str] = handler.__bus_handler__
            match handler_info[1]:
                case "method":
                    self.register_method_handler(handler_info[0], handler)
                case "property":
                    self.register_property_handler(handler_info[0], handler)
                case "raw":
                    self.register_raw_handler(handler_info[0], handler)
        return

    def do_handle_bus_call(
        self,
        conn: Gio.DBusConnection,
        sender: str,
        path: str,
        interface: str,
        target: str,
        params: tuple | GLib.Variant,
        invocation: Gio.DBusMethodInvocation,
        user_data: object = None,
    ) -> None:
        # https://stackoverflow.com/a/5470320/21662703
        # self must be passed manually to handlers
        # otherwise the "method" will not receive self
        # if you know a fix for this, please open a PR or notify me
        # for now if it works it works

        # TL;DR: decorated methods are converted to functions somehow
        # normal functions doesn't receive self by default
        # so we pass it manually
        if (
            raw_method := self.__bus_raw_handlers__.get((interface + "." + target))
        ) is not None:
            raw_method(self, invocation, *params)  # type: ignore
            return conn.flush()
        match target:
            case "Get":
                if (
                    target_method := self.__bus_properties__.get(params[1])
                ) is not None:
                    invocation.return_value(
                        GLib.Variant("(v)", [target_method(self, invocation, *params)])  # type: ignore
                    )
                else:
                    invocation.return_value(None)
            case "GetAll":
                props = {
                    prop_name: handler(self, invocation, *params)  # type: ignore
                    for prop_name, handler in self.__bus_properties__.items()
                }
                invocation.return_value(GLib.Variant("(a{sv})", [props]))
            case _:
                if (target_method := self.__bus_methods__.get(target)) is not None:
                    invocation.return_value(target_method(self, invocation, params))  # type: ignore
                else:
                    invocation.return_value(None)
        return conn.flush()
