# Changelog

All notable changes to Kayori v2 will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/), and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Dedicated core services for episodic memory and conversation contraction
- Episodic memory backends for in-memory, Pinecone, and Redis storage
- Inactivity-based conversation compaction with summary rewriting and fact extraction
- Agent-side episodic recall injection through graph state and prompt context
- New core-service docs for orchestrator, episodic memory, conversation contraction, and output sink
- MkDocs navigation for the expanded core-service documentation set

### Changed
- Refactored episodic memory into a backend-driven core service instead of provider-specific wiring
- Moved scheduler backends into `src/adapters/scheduler/` and kept `src/core/scheduler.py` focused on scheduling logic
- Simplified orchestrator routing by separating chat, LIFE, and scheduled compaction paths
- Updated prompt/context preparation so recalled episodic memories are available to the agent as distilled context
- Reworked scheduler usage toward explicit backend injection and inactivity-driven compaction scheduling
- Refreshed README and core docs to match the current architecture and runtime behavior

### Removed
- Graph memory / Neo4j-related runtime pieces
- Old Pinecone-specific episodic memory coupling from the memory core
- Obsolete scheduler package layout under `src/core/scheduler/`

### Technical Details
- Python requirement aligned to `>=3.13,<3.14`
- Local FastEmbed embeddings added for episodic memory backends
- Scheduler trigger defaults now support internal runtime triggers more cleanly
- Documentation links now point to the GitHub repository instead of local filesystem paths

---

For more detailed information, see the [README.md](README.md) and [documentation](docs/).
