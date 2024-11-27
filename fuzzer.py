import sys
import os
import requests
import json
import subprocess
import re
import logging
import argparse
import random
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
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

def extract_links(url):
    """Extract first 25 links from the main page"""
    try:
        logger.info(f"Attempting to extract links from {url}")
        response = requests.get(url)
        soup = BeautifulSoup(response.text, 'html.parser')
        links = []
        for a in soup.find_all('a', href=True)[:25]:
            href = a['href']
            # Extract path without leading slash
            if href and not href.startswith(('#', 'javascript:', 'mailto:')):
                # Remove any URL prefix
                if href.startswith(('http://', 'https://')):
                    href = urlparse(href).path
                # Remove leading slash if present
                if href.startswith('/'):
                    href = href[1:]
                # Only add if it's not empty
                if href:
                    links.append(href)
        logger.info(f"Successfully extracted {len(links)} links")
        return links, dict(response.headers)
    except requests.RequestException as e:
        logger.error(f"Network error while extracting links: {e}")
        return [], {}
    except Exception as e:
        logger.error(f"Unexpected error while extracting links: {e}", exc_info=True)
        return [], {}

def format_headers(headers):
    """Format headers in the required format"""
    formatted = []
    formatted.append("HTTP/1.1 200")
    for key, value in headers.items():
        formatted.append(f"{key}: {value}")
    return "\n".join(formatted)

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

def extract_new_links(response):
    """Extract links from between <new_files_dirs> tags"""
    pattern = r'<new_files_dirs>(.*?)</new_files_dirs>'
    match = re.search(pattern, response, re.DOTALL)
    if match:
        # Split on newlines and remove empty lines and whitespace
        return [line.strip() for line in match.group(1).split('\n') if line.strip()]
    return []

def run_ffuf(original_cmd, wordlist, target_url):
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
        ffuf_cmd = ['ffuf'] + cmd_parts + ['-w', wordlist, '-u', target_url, '-o', '/tmp/brainstorm/output.json']
        logger.info(f"Running ffuf command: {' '.join(ffuf_cmd)}")
        
        result = subprocess.run(ffuf_cmd, capture_output=True, text=True)
        if result.returncode != 0:
            logger.error(f"ffuf command failed: {result.stderr}")
            return None
        
        if not os.path.exists('/tmp/brainstorm/output.json') or os.stat('/tmp/brainstorm/output.json').st_size == 0:
            logger.warning("ffuf produced no output")
            return None        
            
        with open('/tmp/brainstorm/output.json', 'r') as f:
            data = json.load(f)
            #logger.info(f"Successfully parsed ffuf results")
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

def display_results(tested_links, new_discovered_links):
    """Display final results and statistics"""
    print(f"\n{Fore.YELLOW}=== Final Results ==={Style.RESET_ALL}")
    print(f"{Fore.CYAN}Total links tested with ffuf:{Style.RESET_ALL} {len(tested_links)}")
    print(f"{Fore.CYAN}Total new links discovered:{Style.RESET_ALL} {len(new_discovered_links)}")
    if new_discovered_links:
        print(f"\n{Fore.YELLOW}New discovered links (via ffuf):{Style.RESET_ALL}")
        for link in sorted(new_discovered_links):
            print(f"  {Fore.GREEN}{link}{Style.RESET_ALL}")
    else:
        print(f"\n{Fore.YELLOW}No new links were discovered{Style.RESET_ALL}")

def main():
    logger.info("Starting fuzzer application")
    
    # Set up argument parser
    parser = argparse.ArgumentParser(description='Web Fuzzer with Ollama integration')
    parser.add_argument('command', help='ffuf command to run')
    parser.add_argument('--debug', action='store_true', help='Enable debug mode')
    parser.add_argument('--cycles', type=int, default=50, help='Number of fuzzing cycles to run (default: 50)')
    parser.add_argument('--model', default='qwen2.5-coder:latest', help='Ollama model to use (default: qwen2.5-coder:latest)')
    parser.add_argument('--prompt-file', default='prompts/files.txt', help='Path to prompt file (default: prompts/files.txt)')
    parser.add_argument('--status-codes', type=str, default='200,301,302,303,307,308,403,401,500',
                    help='Comma-separated list of status codes to consider as successful (default: 200,301,302,303,307,308,403,401,500)')    

    args = parser.parse_args()

    # Parse command line argument
    cmd = sys.argv[1]
    # Try to match URL with double quotes, single quotes, or no quotes
    url_match = re.search(r'-u\s*["\']?([^"\'\s]+)["\']?', cmd)
    if not url_match:
        logger.error("Could not extract URL from command")
        print("Could not extract URL from command")
        return
    
    logger.info(f"Extracted base URL from command: {url_match.group(1)}")

    base_url = url_match.group(1).replace('FUZZ', '')
    considered_status_codes = [int(code) for code in args.status_codes.split(',')]
    
    # Initial setup
    try:
        os.mkdir('/tmp/brainstorm')
        logger.info("Created output directory /tmp/brainstorm.")
    except FileExistsError:
        logger.info("/tmp/brainstorm already exists.")

    initial_links, headers = extract_links(base_url)
    unique_initial_links = set(initial_links)
    print(f"\n{Fore.LIGHTBLACK_EX}Initial unique links extracted from website:{Style.RESET_ALL}")
    for link in sorted(unique_initial_links):
        print(f"  {Fore.LIGHTBLACK_EX}{link}{Style.RESET_ALL}")
    print()
    
    all_links = set(initial_links)  # all links including tried ones
    new_discovered_links = set()    # only links discovered by ffuf
    tested_links = set()           # links that were tested with ffuf
    server_headers = format_headers(headers)
    
    # Read prompt template from specified file
    try:
        with open(args.prompt_file, 'r') as f:
            ollama_prompt = f.read()
    except Exception as e:
        print(f"Error reading prompt file: {e}")
        return

    cycle = 0
    max_cycles = args.cycles

    while cycle < max_cycles:
        try:
            #logger.info(f"Starting cycle {cycle + 1}/{max_cycles}")
            print(f"\nCycle {cycle + 1}/{max_cycles}")
            
            # Prepare prompt with randomized link order
            randomized_links = list(all_links)
            random.shuffle(randomized_links)
            current_prompt = ollama_prompt.replace('{{initialLinks}}', 
                                                    '\n'.join(randomized_links))
            current_prompt = current_prompt.replace('{{serverHeaders}}', 
                                                    server_headers)
            
            # Call Ollama API
            if args.debug:
                logger.debug("\nSending prompt to Ollama:")
                logger.debug(current_prompt)
                
            response = call_ollama(current_prompt, model=args.model)
            
            if args.debug:
                logger.debug("\nOllama response:")
                logger.debug(response)
                
            new_links = extract_new_links(response)
            
            # Update links
            # Filter out links that have already been tested
            new_unique_links = set(new_links) - all_links
            untested_links = new_unique_links - tested_links

            # add to tested links
            tested_links.update(new_unique_links)
            
            if untested_links:
                if args.debug:
                    logger.debug("\nNew untested links suggested by Ollama:")
                    for link in untested_links:
                        logger.debug(f" {link}")
                with open('/tmp/brainstorm/links.txt', 'w') as f:
                    f.write('\n'.join(untested_links))
            
            # Run ffuf with original command
            ffuf_results = run_ffuf(cmd, '/tmp/brainstorm/links.txt', url_match.group(1))
            if ffuf_results and 'results' in ffuf_results:
                if args.debug:
                    logger.debug("\nffuf results:")
                    logger.debug(json.dumps(ffuf_results, indent=2))
                
                fuzz_links = set()
                for result in ffuf_results['results']:
                    tested_url = result['input']['FUZZ']                    
                    if result['status'] in considered_status_codes:
                        fuzz_links.add(tested_url)
                
                # Update discovered links
                new_discovered = fuzz_links - all_links
                if new_discovered:
                    print(f"\n{Fore.YELLOW}New links discovered:{Style.RESET_ALL}")
                    for link in new_discovered:
                        print(f"  {Fore.GREEN}{link}{Style.RESET_ALL}")
                    all_links.update(new_discovered)
                    new_discovered_links.update(new_discovered)
                
                # Save all discovered links to file
                with open('/tmp/brainstorm/all_links.txt', 'w') as f:
                    f.write('\n'.join(sorted(all_links)))
            
            cycle += 1
            
        except KeyboardInterrupt:
            logger.info("Fuzzer stopped by user")
            print(f"\n{Fore.RED}Stopping fuzzer...{Style.RESET_ALL}")
            display_results(tested_links, new_discovered_links)
            break
        except Exception as e:
            print(f"Error in cycle {cycle}: {e}")
            continue
    
    # Display final results after all cycles complete
    if cycle >= max_cycles:
        display_results(tested_links, new_discovered_links)

if __name__ == "__main__":
    main()
