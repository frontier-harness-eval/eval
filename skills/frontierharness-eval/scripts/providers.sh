# Kimi K3 provider routes, shared by provision-golden-checkpoint.sh and run-trials.sh.
#
# The benchmark fixes the *model* at Kimi K3 so the harness is the only variable. The
# *provider* is free: the published baselines used Fireworks, but any provider serving
# the same model produces a comparable pass rate. Model strings use the LiteLLM provider
# route, which is what Harbor, Pier, and mini-swe-agent expect.

PROVIDER_LIST="fireworks moonshot openrouter together custom"

# Sets the generic connection plus the MiniMax Code translation fields. Keeping these
# together prevents a provider addition from silently working in the generic runner but
# not in the MCode profile. Returns 1 on unknown input.
resolve_provider() {
  case "$1" in
    fireworks)
      PROVIDER_MODEL="fireworks_ai/accounts/fireworks/models/kimi-k3"
      PROVIDER_SECRET="FIREWORKS_API_KEY"
      PROVIDER_HOST="api.fireworks.ai"
      PROVIDER_MCODE_PREFIX="openai/"
      PROVIDER_MCODE_STRIP="fireworks_ai/"
      PROVIDER_MCODE_CONNECTION='OPENAI_API_KEY="$FIREWORKS_API_KEY" OPENAI_BASE_URL="https://api.fireworks.ai/inference/v1"' ;;
    moonshot)
      PROVIDER_MODEL="moonshot/kimi-k3"
      PROVIDER_SECRET="MOONSHOT_API_KEY"
      PROVIDER_HOST="api.moonshot.ai"
      PROVIDER_MCODE_PREFIX="openai/"
      PROVIDER_MCODE_STRIP="moonshot/"
      PROVIDER_MCODE_CONNECTION='OPENAI_API_KEY="$MOONSHOT_API_KEY" OPENAI_BASE_URL="https://api.moonshot.ai/v1"' ;;
    openrouter)
      PROVIDER_MODEL="openrouter/moonshotai/kimi-k3"
      PROVIDER_SECRET="OPENROUTER_API_KEY"
      PROVIDER_HOST="openrouter.ai"
      PROVIDER_MCODE_PREFIX=""
      PROVIDER_MCODE_STRIP=""
      PROVIDER_MCODE_CONNECTION="" ;;
    together)
      PROVIDER_MODEL="together_ai/moonshotai/Kimi-K3"
      PROVIDER_SECRET="TOGETHER_API_KEY"
      PROVIDER_HOST="api.together.xyz"
      PROVIDER_MCODE_PREFIX="together/"
      PROVIDER_MCODE_STRIP="together_ai/"
      PROVIDER_MCODE_CONNECTION="" ;;
    custom)
      # Anything else: --model and --secret-name must be supplied explicitly.
      PROVIDER_MODEL=""
      PROVIDER_SECRET=""
      PROVIDER_HOST=""
      PROVIDER_MCODE_PREFIX=""
      PROVIDER_MCODE_STRIP=""
      PROVIDER_MCODE_CONNECTION="" ;;
    *)
      return 1 ;;
  esac
}

# The model must still be Kimi K3 whatever the provider. Case-insensitive because
# providers disagree on capitalisation, e.g. Together serves it as Kimi-K3.
warn_unless_kimi_k3() {
  case "$(printf '%s' "$1" | tr 'A-Z' 'a-z')" in
    *kimi-k3*|*kimi_k3*|*"kimi k3"*|*kimik3*) return 0 ;;
  esac
  echo "warning: --model $1 is not Kimi K3. Every published FrontierHarness result uses Kimi K3, so this score will not be comparable to them." >&2
}
