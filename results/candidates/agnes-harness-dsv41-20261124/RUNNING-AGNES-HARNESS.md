# Running Agnes Harness on FrontierHarness Eval v1.1

```bash
harbor run \
  -d frontier-harness-eval/frontier-harness-eval@v1.1.0 \
  --agent harbor_agh_agent:AgnesHarnessAgent \
  -m deepseek-v4.1-flash-1017 \
  -k 4 -n 4 \
  --timeout-multiplier 1.0
```
