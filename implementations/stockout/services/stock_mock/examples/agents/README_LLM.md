# Running LLM Agent Examples

## Prerequisites

Before running LLM agent examples, make sure you have:

1. **Installed project dependencies:**
   ```bash
   cd /path/to/floor
   pip install -r requirements.txt
   ```

2. **Installed LLM provider library:**
   ```bash
   # For OpenAI
   pip install openai
   
   # For Anthropic
   pip install anthropic
   ```

3. **Set API key:**
   ```bash
   export OPENAI_API_KEY="sk-..."
   # or
   export ANTHROPIC_API_KEY="sk-ant-..."
   ```

## Running Examples

### Quick Test

```bash
# From project root
python examples/agents/quick_llm_test.py
```

### Full Examples

```bash
# From project root
python examples/agents/llm_agent_example.py
```

## Troubleshooting

### Error: `ModuleNotFoundError: No module named 'src'`

**Solution:** Run the script from the project root directory:
```bash
cd /path/to/floor
python examples/agents/llm_agent_example.py
```

### Error: `ModuleNotFoundError: No module named 'structlog'`

**Solution:** Install project dependencies:
```bash
pip install -r requirements.txt
```

### Error: `ModuleNotFoundError: No module named 'openai'`

**Solution:** Install OpenAI library:
```bash
pip install openai
```

### Error: `OPENAI_API_KEY environment variable not set`

**Solution:** Set your API key:
```bash
export OPENAI_API_KEY="sk-..."
```

