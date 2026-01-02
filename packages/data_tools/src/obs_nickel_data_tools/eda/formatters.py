"""Output formatters for EDA tools.

Supports multiple output formats:
- Rich terminal output with tables and colors
- JSON for programmatic use
- CSV/TSV for spreadsheets
"""

from __future__ import annotations

import csv
import json
from io import StringIO
from pathlib import Path
from typing import Any

from rich.console import Console
from rich.table import Table


def format_table_rich(
    data: list[dict[str, Any]],
    title: str | None = None,
    column_order: list[str] | None = None,
) -> None:
    """Print data as a rich formatted table to terminal.

    Parameters
    ----------
    data : list[dict[str, Any]]
        List of dictionaries to display
    title : str | None
        Optional table title
    column_order : list[str] | None
        Optional column ordering, otherwise uses keys from first row
    """
    if not data:
        console = Console()
        console.print("[yellow]No data to display[/yellow]")
        return

    # Determine columns
    if column_order is None:
        column_order = list(data[0].keys())

    # Create table
    table = Table(title=title, show_header=True, header_style="bold magenta")
    for col in column_order:
        table.add_column(col, overflow="fold")

    # Add rows
    for row in data:
        table.add_row(*[str(row.get(col, "")) for col in column_order])

    # Print
    console = Console()
    console.print(table)


def format_json(
    data: Any,
    output_file: str | Path | None = None,
    indent: int = 2,
) -> None:
    """Output data as JSON.

    Parameters
    ----------
    data : Any
        Data to serialize (must be JSON-serializable)
    output_file : str | Path | None
        If provided, write to file; otherwise print to stdout
    indent : int
        JSON indentation level
    """
    json_str = json.dumps(data, indent=indent, default=str)

    if output_file:
        Path(output_file).write_text(json_str)
    else:
        print(json_str)


def format_csv(
    data: list[dict[str, Any]],
    output_file: str | Path | None = None,
    delimiter: str = ",",
    column_order: list[str] | None = None,
) -> None:
    """Output data as CSV/TSV.

    Parameters
    ----------
    data : list[dict[str, Any]]
        List of dictionaries to write
    output_file : str | Path | None
        If provided, write to file; otherwise print to stdout
    delimiter : str
        Field delimiter (comma for CSV, tab for TSV)
    column_order : list[str] | None
        Optional column ordering, otherwise uses keys from first row
    """
    if not data:
        return

    # Determine fieldnames
    if column_order is None:
        column_order = list(data[0].keys())

    # Write to string or file
    if output_file:
        with Path(output_file).open("w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=column_order, delimiter=delimiter)
            writer.writeheader()
            writer.writerows(data)
    else:
        output = StringIO()
        writer = csv.DictWriter(output, fieldnames=column_order, delimiter=delimiter)
        writer.writeheader()
        writer.writerows(data)
        print(output.getvalue().rstrip())


def output_data(
    data: Any,
    format_type: str = "table",
    output_file: str | Path | None = None,
    title: str | None = None,
    column_order: list[str] | None = None,
) -> None:
    """Unified output function supporting multiple formats.

    Parameters
    ----------
    data : Any
        Data to output (list of dicts for table/csv, any for json)
    format_type : str
        Output format: 'table', 'json', 'csv', 'tsv'
    output_file : str | Path | None
        Optional output file
    title : str | None
        Optional title for table format
    column_order : list[str] | None
        Optional column ordering for table/csv formats
    """
    if format_type == "table":
        if not isinstance(data, list):
            raise ValueError("Table format requires list of dictionaries")
        format_table_rich(data, title=title, column_order=column_order)

    elif format_type == "json":
        format_json(data, output_file=output_file)

    elif format_type == "csv":
        if not isinstance(data, list):
            raise ValueError("CSV format requires list of dictionaries")
        format_csv(
            data, output_file=output_file, delimiter=",", column_order=column_order
        )

    elif format_type == "tsv":
        if not isinstance(data, list):
            raise ValueError("TSV format requires list of dictionaries")
        format_csv(
            data, output_file=output_file, delimiter="\t", column_order=column_order
        )

    else:
        raise ValueError(f"Unknown format type: {format_type}")


def print_section(title: str, style: str = "bold cyan") -> None:
    """Print a section header.

    Parameters
    ----------
    title : str
        Section title
    style : str
        Rich style string
    """
    console = Console()
    console.print(f"\n[{style}]{title}[/{style}]")


def print_info(label: str, value: Any, style: str = "green") -> None:
    """Print a labeled info line.

    Parameters
    ----------
    label : str
        Info label
    value : Any
        Info value
    style : str
        Rich style for value
    """
    console = Console()
    console.print(f"  {label}: [{style}]{value}[/{style}]")


def print_warning(message: str) -> None:
    """Print a warning message.

    Parameters
    ----------
    message : str
        Warning message
    """
    console = Console()
    console.print(f"[yellow]Warning: {message}[/yellow]")


def print_error(message: str) -> None:
    """Print an error message.

    Parameters
    ----------
    message : str
        Error message
    """
    console = Console(stderr=True)
    console.print(f"[red]Error: {message}[/red]")
