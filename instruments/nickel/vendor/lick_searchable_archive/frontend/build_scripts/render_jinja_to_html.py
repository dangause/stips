import argparse
import sys
from pathlib import Path

from jinja2 import (
    BaseLoader,
    ChoiceLoader,
    Environment,
    FileSystemLoader,
    TemplateNotFound,
    select_autoescape,
)


def get_parser():
    """
    Parse build_metadata_config command line arguments with argparse.
    """
    parser = argparse.ArgumentParser(
        description="Build the archive HTML pages via jinja templating."
    )
    parser.add_argument("input", type=Path, help="The source template to render.")
    parser.add_argument("output", type=Path, help="The output HTML file to create.")
    parser.add_argument(
        "--set-variables",
        "-v",
        type=str,
        nargs="*",
        help='A variable to set for the template, of the format "var=value".',
    )
    parser.add_argument(
        "--template-paths",
        "-p",
        type=Path,
        nargs="*",
        help="Paths to find template files included or extended by the template being rendered.",
    )
    return parser


def main(args):

    # Parse command line arguments
    if not args.input.exists():
        print(f"Input file '{args.input}' does not exist.", file=sys.stderr)
        return 1

    vars = {x.split("=")[0]: x.split("=")[1] for x in args.set_variables}

    failed = False
    for path in args.template_paths:
        if not path.exists():
            print(f"Template path '{path}' does not exist.", file=sys.stderr)
            failed = True

    if failed:
        return 2

    paths = [str(p) for p in args.template_paths]

    print(f"Using template paths: {','.join(paths)}")
    for var in vars.items():
        print(f"Setting variable {var[0]} = '{var[1]}'")

    # Build the jinja template loader to use either our simple path loader or jinja2's FileSystemLoader. The
    # difference is that the FileSystemLoader *only* looks in the given paths, and ignores absolute paths.
    # Our PathLoader will open anything that the python "open" call can find, but doesn't know about template paths
    # Doing it this way allows the command line to specify a template via a pathname while the templates can assume
    # a fixed template path in their "extends" directives.
    loader = ChoiceLoader([PathLoader(), FileSystemLoader(paths)])

    # Build the environment and get the input template
    env = Environment(loader=loader, autoescape=select_autoescape())

    print(f"Rendering template {args.input} to {args.output}")
    template = env.get_template(str(args.input))

    # Render the template to the output file
    with open(args.output, "w") as f:
        print(template.render(**vars), file=f)


class PathLoader(BaseLoader):
    """Simple path loader that will load a template from any path visible to this script"""

    def get_source(self, environment, template):
        template_path = Path(template)
        if not template_path.exists():
            raise TemplateNotFound(template)

        with open(template, "r") as f:
            source = f.read()

        return source, Path(template).name, lambda: True


if __name__ == "__main__":
    parser = get_parser()
    args = parser.parse_args()
    sys.exit(main(args))
