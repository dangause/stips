"""Sphinx extension: the STIPS CLI reference, generated at build time.

``reference/cli.md`` holds a marker that this replaces, before the page is
parsed, with every command's ``stips <command> --help`` text, taken from the
click command tree. Nothing is generated into the source tree, so the page
cannot drift from the CLI. The help goes in verbatim rather than as Markdown:
the docstrings use click's ``\\b`` blocks for their examples, and Markdown
would run those lines together.
"""

from __future__ import annotations

from collections.abc import Iterator

import click

#: The page that holds the marker.
CLI_DOCNAME = "reference/cli"

#: Placeholder in that page that the generated reference replaces.
CLI_MARKER = "<!-- stips-cli-reference -->"

#: Wrap width for the help text: what fits in a furo code block on desktop.
HELP_WIDTH = 78


def _walk(
    command: click.Command, ctx: click.Context
) -> Iterator[tuple[click.Command, click.Context]]:
    """Yield every visible command depth-first, in ``stips --help`` order."""
    yield command, ctx
    if isinstance(command, click.Group):
        for name in command.list_commands(ctx):
            sub = command.get_command(ctx, name)
            if sub is None or sub.hidden:
                continue
            yield from _walk(sub, click.Context(sub, info_name=name, parent=ctx))


def render_cli_reference() -> str:
    """Return MyST markdown for the whole ``stips`` command tree."""
    from stips.cli import cli

    root = click.Context(
        cli, info_name="stips", terminal_width=HELP_WIDTH, max_content_width=HELP_WIDTH
    )
    lines: list[str] = []
    for command, ctx in _walk(cli, root):
        depth = ctx.command_path.count(" ")
        lines += [f"{'#' * min(depth + 2, 6)} `{ctx.command_path}`", ""]
        lines += ["```text", command.get_help(ctx).rstrip(), "```", ""]
    return "\n".join(lines)


def _on_source_read(app, docname: str, source: list[str]) -> None:
    if docname == CLI_DOCNAME and CLI_MARKER in source[0]:
        source[0] = source[0].replace(CLI_MARKER, render_cli_reference())


def _always_reread(app, env, added, changed, removed) -> list[str]:
    # The page's source never changes when the CLI does, so an incremental
    # build (make docs-serve) would otherwise keep a stale reference.
    return [CLI_DOCNAME]


def setup(app):
    app.connect("source-read", _on_source_read)
    app.connect("env-get-outdated", _always_reread)
    return {"version": "1.0", "parallel_read_safe": True, "parallel_write_safe": True}
