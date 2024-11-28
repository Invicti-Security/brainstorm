# brainstorm

A smarter web fuzzing tool that combines local LLM models (via Ollama) and [ffuf](https://github.com/ffuf/ffuf) to optimize directory and file discovery.

I wrote a blog post about the ideas behind this tool: 
[Brainstorm tool release: Optimizing web fuzzing with local LLMs](https://www.invicti.com/blog/security-labs/brainstorm-tool-release-optimizing-web-fuzzing-with-local-llms/)

## Short Description

Combines traditional web fuzzing techniques with AI-powered path generation to discover hidden endpoints, files, and directories in web applications.

## Information

The original author of **brainstorm** is [@harisec](https://github.com/harisec)/[Invicti Security](https://github.com/Invicti-Security) (thanks!). I only forked the project to modify a few things & add functions that will not be implemented in the main repo (ex: argument for output directory). 

## Screenshot
![screenshot](screenshot.png)

## Long Description

This tool enhances traditional web fuzzing by using local AI language models (via Ollama) to generate intelligent guesses for potential paths and filenames. It works by:

1. Extracting initial links from the target website
2. Using AI to analyze the structure and suggest new potential paths
3. Fuzzing these paths using ffuf
4. Learning from discoveries to generate more targeted suggestions
5. Repeat

There are 2 tools:
- `fuzzer.py`: Main fuzzer focusing on general path discovery
- `fuzzer_shortname.py`: Specialized variant for short filename discovery (e.g., legacy 8.3 format)

## Prerequisites

- Python 3.6+
- ffuf (https://github.com/ffuf/ffuf)
- Ollama (https://ollama.ai)
- Required Python packages (see requirements.txt)

## Local Ollama models

By default, the tool is using the model `qwen2.5-coder:latest`. 
This model (or other models you want to use) needs to be downloaded first.

```bash
ollama pull qwen2.5-coder:latest
```

## Installation

```bash
# Clone the repository
git clone https://github.com/Invicti-Security/brainstorm.git
cd brainstorm

# Install Python dependencies
pip install -r requirements.txt

# Ensure ffuf is installed and in your PATH
# Ensure Ollama is running locally on port 11434
```

## Usage

### Basic Usage

```bash
# Basic fuzzing with default settings
python fuzzer.py "ffuf -w ./fuzz.txt -u http://example.com/FUZZ"

# Short filename fuzzing (specify the 8.3 filename as the last parameter)
python fuzzer_shortname.py "ffuf -w ./fuzz.txt -u http://example.com/FUZZ" "BENCHM~1.PY"
```

### Command Line Options

#### Main Fuzzer (fuzzer.py)
```
-d, --debug             Enable debug mode
-c, --cycles N          Number of fuzzing cycles to run (default: 50)
-m, --model NAME        Ollama model to use (default: qwen2.5-coder:latest)
--prompt-file PATH  Path to prompt file (default: prompts/files.txt)
-o, --output        The output directory for links & ffuf files (default: /tmp/brainstorm)
--status-codes LIST Comma-separated list of status codes to consider successful
                   (default: 200,301,302,303,307,308,403,401,500)
```

#### Short Filename Fuzzer (fuzzer_shortname.py)
```
-d, --debug             Enable debug mode
-c, --cycles N          Number of fuzzing cycles to run (default: 50)
-m, --model NAME        Ollama model to use (default: qwen2.5-coder:latest)
-o, --output        The output directory for links & ffuf files (default: /tmp/brainstorm)
--status-codes LIST Comma-separated list of status codes to consider successful
```

### Examples

```bash
# Run fuzzing with custom cycles and model
python fuzzer.py "ffuf -w ./fuzz.txt -u http://target.com/FUZZ" --cycles 100 --model llama2:latest

# Run short filename fuzzing targeting a specific file
python fuzzer_shortname.py "ffuf -w ./fuzz.txt -u http://target.com/FUZZ" "document.pdf" --cycles 25

# Benchmark different models and generate HTML report
python benchmark.py
```

## Output

- Discovered paths are saved to `all_links.txt`, in the directory specified in the `--output` argument (defaults to /tmp/brainstorm).
- Short filenames are saved to `all_filenames.txt`, in the directory specified in the `--output` argument (defaults to /tmp/brainstorm).
- Real-time console output shows progress and discoveries

## Benchmarking Ollama LLM models

I've compared the most popular local LLM models, you can find the [results here](https://github.com/Invicti-Security/brainstorm/blob/main/benchmark_report.md).
