# Upstream attribution

`codex-glm-models.json` includes native Codex fallback instructions and model
metadata taken from [openai/codex at rust-v0.148.0](https://github.com/openai/codex/tree/3ba0f711642a888aec92a611a3f3b2211157ff89),
including `codex-rs/core/prompt.md` and model metadata. The GLM entry adds
provider-specific model identification and capability settings. Upstream content
is covered by the accompanying [Apache 2.0 license](CODEX-LICENSE).

The other adapter modules supply installation/configuration and runner glue for
stock Harbor/Pier agents. They do not include benchmark solution patches.
