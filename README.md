# DevForge Scoop Bucket

Scoop bucket for **DevForge** developer CLI tools — installable via `scoop install Coding-Dev-Tools/scoop-bucket/<app>`.

## Available Manifests

| App | Description |
|-----|-------------|
| `configdrift` | Track and detect configuration drift across environments |
| `api-contract-guardian` | Monitor OpenAPI schema diffs, detect breaking changes |
| `click-to-mcp` | Convert any Click/Typer CLI into an MCP server automatically |
| `deadcode` | Detect unused exports, dead routes, and orphaned CSS in TS/React/Next.js |
| `datamorph` | Batch convert between data formats (CSV, JSON, YAML, Parquet, Avro, Protobuf) |
| `deploydiff` | Compare deployment manifests across environments |
| `envault` | Env variable syncing, diffing, and secret rotation CLI |
| `json2sql-cli` | Convert JSON files to SQL CREATE TABLE and INSERT statements |
| `schemaforge` | Bidirectional ORM schema converter |
| `saas-churn-predictor` | SaaS churn prediction with sklearn pipelines |

## Quick Start

```powershell
# Add the bucket
scoop bucket add Coding-Dev-Tools https://github.com/Coding-Dev-Tools/scoop-bucket

# Install any app
scoop install Coding-Dev-Tools/schemaforge

# Verify
schemaforge --help
```

## License

MIT — see [LICENSE](./LICENSE).
