import sys
import os
import requests
import json
import subprocess
import re
import logging
import argparse
import random
from colorama import init, Fore, Style

# Initialize colorama
init()

# Configure logging
logger = logging.getLogger(__name__)
handlers = [logging.StreamHandler()]

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=handlers
)
if '--debug' in sys.argv:
    logger.setLevel(logging.DEBUG)

def call_ollama(prompt, model="qwen2.5-coder:latest"):
    """Call the local Ollama API"""
    try:
        logger.info(f"Calling Ollama API with model {model}")
        response = requests.post('http://localhost:11434/api/generate', 
                                json={
                                    "model": model,
                                    "prompt": prompt,
                                    "stream": False
                                })
        response.raise_for_status()
        result = response.json()['response']
        logger.info("Successfully received response from Ollama API")
        return result
    except requests.RequestException as e:
        logger.error(f"Network error calling Ollama API: {e}")
        return ""
    except Exception as e:
        logger.error(f"Unexpected error calling Ollama API: {e}", exc_info=True)
        return ""

def extract_filenames(response):
    """Extract filenames from between <full_filenames> tags"""
    pattern = r'<full_filenames>(.*?)</full_filenames>'
    match = re.search(pattern, response, re.DOTALL)
    if match:
        # Split on newlines and remove empty lines and whitespace
        return [line.strip() for line in match.group(1).split('\n') if line.strip()]
    return []

def run_ffuf(original_cmd, wordlist, target_url, output):
    """Run ffuf and return results"""
    try:
        # Split original command into parts
        cmd_parts = original_cmd.split()
        # Remove the original -u and -w arguments and their values
        i = 0
        while i < len(cmd_parts):
            if cmd_parts[i] in ['-u', '-w']:
                cmd_parts.pop(i)  # Remove the argument
                if i < len(cmd_parts):  # Remove its value
                    cmd_parts.pop(i)
                continue
            i += 1
        
        # Remove 'ffuf' if it's the first part
        if cmd_parts and cmd_parts[0] == 'ffuf':
            cmd_parts = cmd_parts[1:]
            
        # Construct new command with all original arguments
        ffuf_cmd = ['ffuf'] + cmd_parts + ['-w', wordlist, '-u', target_url, '-o', f'{output}/output.json']
        logger.info(f"Running ffuf command: {' '.join(ffuf_cmd)}")
        
        result = subprocess.run(ffuf_cmd, capture_output=True, text=True)
        if result.returncode != 0:
            logger.error(f"ffuf command failed: {result.stderr}")
            return None
        
        if not os.path.exists('{output}/output.json') or os.stat('{output}/output.json').st_size == 0:
            logger.warning("ffuf produced no output")
            return None        
            
        with open('{output}/output.json', 'r') as f:
            data = json.load(f)
            return data
    except FileNotFoundError:
        logger.error("ffuf command not found. Please ensure it's installed and in PATH")
        return None
    except json.JSONDecodeError as e:
        logger.error(f"Error parsing ffuf output JSON: {e}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error running ffuf: {e}", exc_info=True)
        return None

def display_results(tested_filenames, new_discovered_filenames):
    """Display final results and statistics"""
    print(f"\n{Fore.YELLOW}=== Final Results ==={Style.RESET_ALL}")
    print(f"{Fore.CYAN}Total filenames tested with ffuf:{Style.RESET_ALL} {len(tested_filenames)}")
    print(f"{Fore.CYAN}Total new filenames discovered:{Style.RESET_ALL} {len(new_discovered_filenames)}")
    if new_discovered_filenames:
        print(f"\n{Fore.YELLOW}New discovered filenames (via ffuf):{Style.RESET_ALL}")
        for filename in sorted(new_discovered_filenames):
            print(f"  {Fore.GREEN}{filename}{Style.RESET_ALL}")
    else:
        print(f"\n{Fore.YELLOW}No new filenames were discovered{Style.RESET_ALL}")

def main():
    logger.info("Starting shortname fuzzer application")
    
    # Set up argument parser
    parser = argparse.ArgumentParser(description='Shortname Fuzzer with Ollama integration')
    parser.add_argument('command', help='ffuf command to run')
    parser.add_argument('filename', help='Filename to use in the prompt')
    parser.add_argument('--debug', action='store_true', help='Enable debug mode')
    parser.add_argument('--cycles', type=int, default=50, help='Number of fuzzing cycles to run (default: 50)')
    parser.add_argument('--model', default='qwen2.5-coder:latest', help='Ollama model to use (default: qwen2.5:latest)')
    parser.add_argument('-o', '--output', default='/tmp/brainstorm', help='The output directory for links & ffuf files. (default: /tmp/brainstorm)')
    parser.add_argument('--status-codes', type=str, default='200,301,302,303,307,308,403,401,500',
                    help='Comma-separated list of status codes to consider as successful (default: 200,301,302,303,307,308,403,401,500)')    

    args = parser.parse_args()

    # Parse command line argument
    cmd = args.command
    # Try to match URL with double quotes, single quotes, or no quotes
    url_match = re.search(r'-u\s*["\']?([^"\'\s]+)["\']?', cmd)
    if not url_match:
        logger.error("Could not extract URL from command")
        print("Could not extract URL from command")
        return
    
    logger.info(f"Extracted base URL from command: {url_match.group(1)}")
    
    # Initial setup
    try:
        output = args.output
        if re.search('/$', output):
            output = output.rstrip('/')

        os.mkdir(output)
        logger.info(f"Created output directory {output}.")
    except FileExistsError:
        logger.info(f"{output} already exists.")

    considered_status_codes = [int(code) for code in args.status_codes.split(',')]
    
    all_filenames = set()  # all filenames including tried ones
    new_discovered_filenames = set()    # only filenames discovered by ffuf
    tested_filenames = set()           # filenames that were tested with ffuf
    
    # Read prompt template
    try:
        with open('prompts/shortname.txt', 'r') as f:
            ollama_prompt = f.read()
    except Exception as e:
        print(f"Error reading prompt file: {e}")
        return

    cycle = 0
    max_cycles = args.cycles

    while cycle < max_cycles:
        try:
            print(f"\nCycle {cycle + 1}/{max_cycles}")
            
            # Prepare prompt with filename
            current_prompt = ollama_prompt.replace('{{INPUT_83_FILENAME}}', args.filename)
            
            # Call Ollama API
            if args.debug:
                logger.debug("\nSending prompt to Ollama:")
                logger.debug(current_prompt)
                
            response = call_ollama(current_prompt, model=args.model)
            
            if args.debug:
                logger.debug("\nOllama response:")
                logger.debug(response)
                
            new_filenames = extract_filenames(response)
            # print new filenames
            print(f"\n{Fore.YELLOW}New filenames suggested by Ollama:{Style.RESET_ALL}")
            for filename in new_filenames:
                print(f"  {Fore.GREEN}{filename}{Style.RESET_ALL}")
            
            # Update filenames
            # Filter out filenames that have already been tested
            new_unique_filenames = set(new_filenames) - all_filenames
            untested_filenames = new_unique_filenames - tested_filenames

            # add to tested filenames
            tested_filenames.update(new_unique_filenames)
            
            if untested_filenames:
                if args.debug:
                    logger.debug("\nNew untested filenames suggested by Ollama:")
                    for filename in untested_filenames:
                        logger.debug(f" {filename}")
                with open('{output}/links.txt', 'w') as f:
                    f.write('\n'.join(untested_filenames))
            
            # Run ffuf with original command
            ffuf_results = run_ffuf(cmd, '{output}/links.txt', url_match.group(1), output)
            if ffuf_results and 'results' in ffuf_results:
                if args.debug:
                    logger.debug("\nffuf results:")
                    logger.debug(json.dumps(ffuf_results, indent=2))
                
                fuzz_filenames = set()
                for result in ffuf_results['results']:
                    tested_filename = result['input']['FUZZ']                    
                    if result['status'] in considered_status_codes:
                        fuzz_filenames.add(tested_filename)
                
                # Update discovered filenames
                new_discovered = fuzz_filenames - all_filenames
                if new_discovered:
                    print(f"\n{Fore.YELLOW}New filenames discovered:{Style.RESET_ALL}")
                    for filename in new_discovered:
                        print(f"  {Fore.GREEN}{filename}{Style.RESET_ALL}")
                    all_filenames.update(new_discovered)
                    new_discovered_filenames.update(new_discovered)
                
                # Save all discovered filenames to file
                with open('{output}/all_filenames.txt', 'w') as f:
                    f.write('\n'.join(sorted(all_filenames)))
            
            cycle += 1
            
        except KeyboardInterrupt:
            logger.info("Fuzzer stopped by user")
            print(f"\n{Fore.RED}Stopping fuzzer...{Style.RESET_ALL}")
            display_results(tested_filenames, new_discovered_filenames)
            break
        except Exception as e:
            print(f"Error in cycle {cycle}: {e}")
            continue
    
    # Display final results after all cycles complete
    if cycle >= max_cycles:
        display_results(tested_filenames, new_discovered_filenames)

if __name__ == "__main__":
    main()
