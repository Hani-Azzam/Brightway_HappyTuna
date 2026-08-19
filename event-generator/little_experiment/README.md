# little_experiment

A throwaway reporter agent that subscribes to the event generator, and asks
Claude Haiku for a three sentence report on every `press` event.

It is `example_subscriber.py` with the print swapped for an LLM call: the
subscription itself is still just `async for event in subscribe("press")`.

## Running it

Three terminals, all from `event-generator/`:

```bash
# A - the event generator
uvicorn server:app --port 8006

# B - the reporter (needs an API key)
export ANTHROPIC_API_KEY=sk-ant-...          # PowerShell: $env:ANTHROPIC_API_KEY="sk-ant-..."
python little_experiment/reporter_agent.py

# C - fire the scripted crisis feed
curl -X POST http://localhost:8006/replay
```

The feed's five events include three `press` briefings (Day 3, Day 7, Day 10),
so terminal B prints three reports. Inject your own with:

```bash
curl -X POST http://localhost:8006/emit \
  -H 'Content-Type: application/json' \
  -d '{"tag":"press","text":"Day 12 - Senate hearing scheduled."}'
```

If the generator runs somewhere else, set `EVENT_GENERATOR_URL`.

## Knobs

Everything worth changing is at the top of `reporter_agent.py`: `TAG` (which
channel to follow), `MODEL`, and `SYSTEM` (what kind of report you want).
