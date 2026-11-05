'''
Decorators that mark what agents may use on a class, through MCP.

Like ``@change`` and ``@trigger``, they only attach options to a method or a
property and do nothing on their own. Agents can use a marked member once
the application exposes an instance of the class (``mcp_expose``) and turns
agent access on (``server.mcp.enabled``).

.. code-block:: python

    class Viewer(TrameComponent):
        @mcp_method
        def set_view_up(self, axis: Literal["x", "y", "z"]) -> None:
            """Orient the camera so this axis points up."""

        @mcp_property(requires="files")
        def data_path(self) -> Annotated[str, "File shown in this view"]:
            return self._path

        @data_path.setter(requires="scripts")
        def data_path(self, value: str):
            self.load(value)

A component that the application builds once can also provide the
application's own tools, resources and prompts (``@mcp_tool``,
``@mcp_resource``, ``@mcp_prompt``).
'''

__all__ = [
    "mcp_method",
    "mcp_prompt",
    "mcp_property",
    "mcp_resource",
    "mcp_tool",
    "requirements",
]

METHOD_MARKER = "_trame_mcp_method"
PROPERTY_MARKER = "_trame_mcp_property"
TOOL_MARKER = "_trame_mcp_tool"
RESOURCE_MARKER = "_trame_mcp_resource"
PROMPT_MARKER = "_trame_mcp_prompt"

# What a component built once offers as the app's own tools
FIRST_CLASS_MARKERS = (TOOL_MARKER, RESOURCE_MARKER, PROMPT_MARKER)


def requirements(value, label="requires"):
    """
    Return ``requires=`` as a tuple of permission names.

    :param value: None, a permission name, or a list of them.
    :param label: the option name used in the error message.
    """
    if value is None:
        return ()
    names = (value,) if isinstance(value, str) else value
    try:
        names = tuple(names)
    except TypeError:
        names = None
    if names is None or not all(isinstance(n, str) and n for n in names):
        msg = f"{label} must be a permission name or a list of them, got {value!r}"
        raise TypeError(msg)
    return names


def mcp_method(
    fn=None,
    *,
    name=None,
    description=None,
    read_only=False,
    annotations=None,
    concurrent=False,
    requires=None,
):
    """
    Decorator that lets agents call a method through ``object_call``.

    Use it bare (``@mcp_method``) or with options. The method may be async.
    Its type hints describe its parameters, and
    ``Annotated[T, "description", {json-schema}]`` adds a description and
    constraints. For a parameter typed with a component or model class, the
    agent passes the object's name or id, and the method receives the object.

    :param name: the name agents call it by (default: the method's own name).
    :param description: the text agents read (default: the docstring).
    :param read_only: True when calling it changes nothing. Agents may then
        call it on an object exposed read-only.
    :param annotations: MCP tool annotations (``destructiveHint``,
        ``idempotentHint``, ``openWorldHint``), which agents see with the
        method. ``readOnlyHint`` is the same as ``read_only``.
    :param concurrent: True to let it run while other agent calls are in
        progress, instead of waiting for them.
    :param requires: the permission, or list of permissions, that a call
        needs.
    """
    options = {
        "name": name,
        "description": description,
        "read_only": bool(read_only),
        "annotations": _annotations(annotations),
        "concurrent": bool(concurrent),
        "requires": requirements(requires),
    }

    return _marker(METHOD_MARKER, options, fn)


def _annotations(value, label="annotations"):
    if value is not None and not isinstance(value, dict):
        msg = f"{label} must be a dict of MCP tool annotations, got {value!r}"
        raise TypeError(msg)
    return value


def _marker(attribute, options, fn):
    def decorate(f):
        setattr(f, attribute, dict(options))
        return f

    if fn is None:
        return decorate
    return decorate(fn)


def mcp_tool(
    fn=None,
    *,
    name=None,
    description=None,
    read_only=False,
    annotations=None,
    concurrent=False,
    requires=None,
):
    """
    Decorator that makes a method one of the application's own tools. The
    tool is added when its component is built, and removed when the component
    is unbound. It takes the same options as ``@server.mcp.tool``.

    It is meant for a component that the application builds once: building a
    second instance while the first one is still bound raises an error,
    because the tool names would collide. Marking tools does not let agents
    reach the component itself with ``object_call``; ``@mcp_method`` does.
    """
    options = {
        "name": name,
        "description": description,
        "read_only": bool(read_only),
        "annotations": _annotations(annotations),
        "concurrent": bool(concurrent),
        "requires": requirements(requires),
    }
    return _marker(TOOL_MARKER, options, fn)


def mcp_resource(uri, *, name=None, description=None, mime_type=None):
    """
    Decorator that serves what a method returns as the resource ``uri``. Like
    ``@mcp_tool``, it is meant for a component built once: the resource is
    added when the component is built, and removed when it is unbound.
    """
    options = {
        "uri": uri,
        "name": name,
        "description": description,
        "mime_type": mime_type,
    }
    return _marker(RESOURCE_MARKER, options, None)


def mcp_prompt(fn=None, *, name=None, description=None):
    """
    Decorator that makes a method one of the application's prompts. Like
    ``@mcp_tool``, it is meant for a component built once: the prompt is added
    when the component is built, and removed when it is unbound.
    """
    return _marker(PROMPT_MARKER, {"name": name, "description": description}, fn)


class mcp_property(property):
    """
    A ``property`` that agents can read, and also write when it has a setter.

    Use it bare (``@mcp_property``) or with options
    (``@mcp_property(requires="files")``). The getter and the setter must be
    synchronous. The getter's return annotation gives the type and schema,
    and also the description when it is ``Annotated[T, "description"]``;
    otherwise the description is the getter's docstring.

    Without a setter, agents can read the property but not write it.
    ``@prop.setter`` also accepts ``requires=``: the getter's ``requires``
    applies to reading and writing, and the setter's adds the permissions that
    only writing needs.

    :param description: the text agents read (default: the text in the
        getter's return annotation, else its docstring).
    :param requires: the permission, or list of permissions, that reading it
        needs.
    """

    def __new__(cls, fget=None, fset=None, fdel=None, doc=None, **options):
        if fget is None and fset is None and fdel is None and doc is None:
            # @mcp_property(...) with options only: return the decorator
            return lambda f: cls(f, **options)
        return super().__new__(cls)

    def __init__(
        self,
        fget=None,
        fset=None,
        fdel=None,
        doc=None,
        *,
        description=None,
        requires=None,
        set_requires=None,
    ):
        super().__init__(fget, fset, fdel, doc)
        setattr(
            self,
            PROPERTY_MARKER,
            {
                "description": description,
                "requires": requirements(requires),
                "set_requires": requirements(set_requires, "setter requires"),
            },
        )

    def _copy(self, **changes):
        options = {**getattr(self, PROPERTY_MARKER), **changes}
        fget = options.pop("fget", self.fget)
        fset = options.pop("fset", self.fset)
        fdel = options.pop("fdel", self.fdel)
        return type(self)(fget, fset, fdel, self.__doc__, **options)

    def getter(self, fget):
        return self._copy(fget=fget)

    def setter(self, fset=None, *, requires=None):
        """
        Decorate the setter, bare (``@prop.setter``) or with the permissions that
        writing needs (``@prop.setter(requires="scripts")``).
        """
        if fset is None:
            return lambda f: self._copy(fset=f, set_requires=requires)
        return self._copy(fset=fset, set_requires=None)

    def deleter(self, fdel):
        return self._copy(fdel=fdel)
