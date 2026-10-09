"""MkDocs hooks for the STIPS documentation site (registered in mkdocs.yml).

Builds the CLI reference from the click command tree at build time, so the page
is always exactly what ``stips <command> --help`` prints. The help text goes in
verbatim rather than as Markdown: the docstrings use click's ``\\b`` blocks for
their examples, and Markdown would run those lines together.
"""

from __future__ import annotations

from collections.abc import Iterator

import click

#: Placeholder in docs/reference/cli.md that the generated reference replaces.
CLI_MARKER = "<!-- stips-cli-reference -->"

#: Wrap width for the help text: what fits in a Material code block on desktop.
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
    """Return the Markdown for the whole ``stips`` command tree."""
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


def on_page_markdown(markdown: str, **kwargs) -> str:
    if CLI_MARKER not in markdown:
        return markdown
    return markdown.replace(CLI_MARKER, render_cli_reference())
