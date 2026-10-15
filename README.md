# StoreGear on Google Cloud

The StoreGear Assistant rebuilt entirely on Google Cloud. It's a RAG agent that answers shop staff's questions from smartwatch manuals and checks live price and stock, built with ADK + Vertex AI and deployed following production best practices.

- **Reference implementation:** n8n (`smoothr-storegear-n8n`)
- **Scope and success criteria:** [ADR-000](docs/adr/000-scope-and-success-criteria.md)
- **Decisions:** [docs/adr/](docs/adr/)
- **Diary:** [docs/build-log.md](docs/build-log.md)
- **Planning:** Linear project "StoreGear on Google Cloud"

| Folder | Contents |
|---|---|
| `agent/` | ADK agent |
| `ingestion/` | Document pipeline |
| `eval/` | 22-question eval and judges |
| `infra/` | Infrastructure scripts |
