# Nickel Processing Suite Documentation

Welcome to the NPS documentation. This guide will help you understand, set up, and use NPS for processing Nickel telescope data.

## Quick Links

| I want to... | Read this |
|--------------|-----------|
| Get started quickly | [Getting Started](getting-started.md) |
| Set up a new transient campaign | [New Campaign Guide](new-campaign.md) |
| Look up a CLI command | [CLI Reference](cli-reference.md) |
| Configure pipeline options | [Configuration Guide](configuration.md) |
| Understand how NPS works | [Architecture Overview](architecture.md) |

## Documentation Map

```
docs/
├── README.md              ← You are here
├── getting-started.md     # Installation & first pipeline
├── new-campaign.md        # Setting up new transient targets
├── cli-reference.md       # Complete command reference
├── configuration.md       # YAML & environment options
├── architecture.md        # System design & internals
└── diagrams/
    ├── architecture.mmd   # Component diagram
    ├── pipeline-flow.mmd  # Data flow diagram
    ├── cli-commands.mmd   # CLI structure diagram
    ├── butler-collections.mmd  # Butler structure
    └── new-campaign.mmd   # Campaign setup workflow
```

## Guides

### [Getting Started](getting-started.md)

**Start here if you're new to NPS.**

- Prerequisites and installation
- Running your first pipeline
- Understanding outputs
- Common issues

### [New Campaign Guide](new-campaign.md)

**Setting up NPS for a new transient target.**

- Gathering target information
- Creating configuration files
- Choosing template strategy
- Running and validating

### [CLI Reference](cli-reference.md)

**Complete command documentation.**

- All `nickel` commands and options
- Examples for each command
- BPS commands for HPC
- Environment variables

### [Configuration Guide](configuration.md)

**Deep dive into configuration options.**

- YAML pipeline configuration
- Environment variables
- Profile-based workflows
- Pipeline tuning options

### [Architecture Overview](architecture.md)

**Understanding NPS internals.**

- Package structure
- Data flow
- Design patterns
- Extension points

## Diagrams

The `diagrams/` directory contains Mermaid diagrams that can be rendered in:
- GitHub (automatic rendering)
- VS Code with Mermaid extension
- [Mermaid Live Editor](https://mermaid.live)

| Diagram | Description |
|---------|-------------|
| [architecture.mmd](diagrams/architecture.mmd) | Component and layer diagram |
| [pipeline-flow.mmd](diagrams/pipeline-flow.mmd) | Data processing flow |
| [cli-commands.mmd](diagrams/cli-commands.mmd) | CLI command structure |
| [butler-collections.mmd](diagrams/butler-collections.mmd) | Butler repository layout |
| [new-campaign.mmd](diagrams/new-campaign.mmd) | Campaign setup workflow |

## Quick Reference

### Minimal Pipeline

```bash
# Install
uv sync --group dev

# Run complete pipeline
nickel run scripts/config/2023ixf/pipeline_ps1_template.yaml
```

### Step-by-Step

```bash
nickel bootstrap config.yaml     # Initialize repo
nickel calibs 20230519           # Build calibrations
nickel science 20230519          # Process science
nickel dia 20230519 --auto       # Difference imaging
nickel fphot 20230519 --ra R --dec D  # Forced photometry
nickel lightcurve --collections ...   # Extract light curve
```

### With Docker

```bash
docker-compose run --rm nps nickel run config.yaml
```

### On HPC

```bash
nickel bps submit science 20230519 --site slurm
nickel bps status RUN_ID
```

## Getting Help

1. Check the relevant guide above
2. Look at example configs in `scripts/config/`
3. Check processing logs in `{REPO}/processing_log/`
4. Open an issue on GitHub

## Contributing to Docs

Documentation source files are in `docs/`. To contribute:

1. Edit Markdown files directly
2. For diagrams, edit `.mmd` files (Mermaid syntax)
3. Submit a pull request

Diagrams use [Mermaid](https://mermaid.js.org/) syntax and render automatically on GitHub.
