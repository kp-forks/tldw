# Website_scraping_tab.py
# Gradio UI for scraping websites
#
# Imports
import asyncio
import json
import logging
import os
import random
from concurrent.futures import ThreadPoolExecutor
from typing import Optional, List, Dict, Any
from urllib.parse import urlparse, urljoin

#
# External Imports
import gradio as gr
from playwright.async_api import TimeoutError, async_playwright
from playwright.sync_api import sync_playwright

#
# Local Imports
from App_Function_Libraries.Web_Scraping.Article_Extractor_Lib import scrape_from_sitemap, scrape_by_url_level, scrape_article
from App_Function_Libraries.Web_Scraping.Article_Summarization_Lib import scrape_and_summarize_multiple
from App_Function_Libraries.DB.DB_Manager import load_preset_prompts
from App_Function_Libraries.Gradio_UI.Chat_ui import update_user_prompt
from App_Function_Libraries.Summarization.Summarization_General_Lib import summarize


#
########################################################################################################################
#
# Functions:

def get_url_depth(url: str) -> int:
    return len(urlparse(url).path.strip('/').split('/'))


def sync_recursive_scrape(url_input, max_pages, max_depth, progress_callback, delay=1.0):
    def run_async_scrape():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        return loop.run_until_complete(
            recursive_scrape(url_input, max_pages, max_depth, progress_callback, delay)
        )

    with ThreadPoolExecutor() as executor:
        future = executor.submit(run_async_scrape)
        return future.result()


async def recursive_scrape(
        base_url: str,
        max_pages: int,
        max_depth: int,
        progress_callback: callable,
        delay: float = 1.0,
        resume_file: str = 'scrape_progress.json',
        user_agent: str = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.3"
) -> List[Dict]:
    async def save_progress():
        temp_file = resume_file + ".tmp"
        with open(temp_file, 'w') as f:
            json.dump({
                'visited': list(visited),
                'to_visit': to_visit,
                'scraped_articles': scraped_articles,
                'pages_scraped': pages_scraped
            }, f)
        os.replace(temp_file, resume_file)  # Atomic replace

    def is_valid_url(url: str) -> bool:
        return url.startswith("http") and len(url) > 0

    # Load progress if resume file exists
    if os.path.exists(resume_file):
        with open(resume_file, 'r') as f:
            progress_data = json.load(f)
            visited = set(progress_data['visited'])
            to_visit = progress_data['to_visit']
            scraped_articles = progress_data['scraped_articles']
            pages_scraped = progress_data['pages_scraped']
    else:
        visited = set()
        to_visit = [(base_url, 0)]  # (url, depth)
        scraped_articles = []
        pages_scraped = 0

    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(user_agent=user_agent)

            try:
                while to_visit and pages_scraped < max_pages:
                    current_url, current_depth = to_visit.pop(0)

                    if current_url in visited or current_depth > max_depth:
                        continue

                    visited.add(current_url)

                    # Update progress
                    progress_callback(f"Scraping page {pages_scraped + 1}/{max_pages}: {current_url}")

                    try:
                        await asyncio.sleep(random.uniform(delay * 0.8, delay * 1.2))

                        # This function should be implemented to handle asynchronous scraping
                        article_data = await scrape_article_async(context, current_url)

                        if article_data and article_data['extraction_successful']:
                            scraped_articles.append(article_data)
                            pages_scraped += 1

                        # If we haven't reached max depth, add child links to to_visit
                        if current_depth < max_depth:
                            page = await context.new_page()
                            await page.goto(current_url)
                            await page.wait_for_load_state("networkidle")

                            links = await page.eval_on_selector_all('a[href]',
                                                                    "(elements) => elements.map(el => el.href)")
                            for link in links:
                                child_url = urljoin(base_url, link)
                                if is_valid_url(child_url) and child_url.startswith(
                                        base_url) and child_url not in visited and should_scrape_url(child_url):
                                    to_visit.append((child_url, current_depth + 1))

                            await page.close()

                    except Exception as e:
                        logging.error(f"Error scraping {current_url}: {str(e)}")

                    # Save progress periodically (e.g., every 10 pages)
                    if pages_scraped % 10 == 0:
                        await save_progress()

            finally:
                await browser.close()

    finally:
        # These statements are now guaranteed to be reached after the scraping is done
        await save_progress()

        # Remove the progress file when scraping is completed successfully
        if os.path.exists(resume_file):
            os.remove(resume_file)

        # Final progress update
        progress_callback(f"Scraping completed. Total pages scraped: {pages_scraped}")

        return scraped_articles


async def scrape_article_async(context, url: str) -> Dict[str, Any]:
    page = await context.new_page()
    try:
        await page.goto(url)
        await page.wait_for_load_state("networkidle")

        title = await page.title()
        content = await page.content()

        return {
            'url': url,
            'title': title,
            'content': content,
            'extraction_successful': True
        }
    except Exception as e:
        logging.error(f"Error scraping article {url}: {str(e)}")
        return {
            'url': url,
            'extraction_successful': False,
            'error': str(e)
        }
    finally:
        await page.close()


def scrape_article_sync(url: str) -> Dict[str, Any]:
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        try:
            page.goto(url)
            page.wait_for_load_state("networkidle")

            title = page.title()
            content = page.content()

            return {
                'url': url,
                'title': title,
                'content': content,
                'extraction_successful': True
            }
        except Exception as e:
            logging.error(f"Error scraping article {url}: {str(e)}")
            return {
                'url': url,
                'extraction_successful': False,
                'error': str(e)
            }
        finally:
            browser.close()


def should_scrape_url(url: str) -> bool:
    parsed_url = urlparse(url)
    path = parsed_url.path.lower()

    # List of patterns to exclude
    exclude_patterns = [
        '/tag/', '/category/', '/author/', '/search/', '/page/',
        'wp-content', 'wp-includes', 'wp-json', 'wp-admin',
        'login', 'register', 'cart', 'checkout', 'account',
        '.jpg', '.png', '.gif', '.pdf', '.zip'
    ]

    # Check if the URL contains any exclude patterns
    if any(pattern in path for pattern in exclude_patterns):
        return False

    # Add more sophisticated checks here
    # For example, you might want to only include URLs with certain patterns
    include_patterns = ['/article/', '/post/', '/blog/']
    if any(pattern in path for pattern in include_patterns):
        return True

    # By default, return True if no exclusion or inclusion rules matched
    return True


async def scrape_with_retry(url: str, max_retries: int = 3, retry_delay: float = 5.0):
    for attempt in range(max_retries):
        try:
            return await scrape_article(url)
        except TimeoutError:
            if attempt < max_retries - 1:
                logging.warning(f"Timeout error scraping {url}. Retrying in {retry_delay} seconds...")
                await asyncio.sleep(retry_delay)
            else:
                logging.error(f"Failed to scrape {url} after {max_retries} attempts.")
                return None
        except Exception as e:
            logging.error(f"Error scraping {url}: {str(e)}")
            return None


def create_website_scraping_tab():
    with gr.TabItem("Website Scraping"):
        gr.Markdown("# Scrape Websites & Summarize Articles")
        with gr.Row():
            with gr.Column():
                scrape_method = gr.Radio(
                    ["Individual URLs", "Sitemap", "URL Level", "Recursive Scraping"],
                    label="Scraping Method",
                    value="Individual URLs"
                )
                url_input = gr.Textbox(
                    label="Article URLs or Base URL",
                    placeholder="Enter article URLs here, one per line, or base URL for sitemap/URL level/recursive scraping",
                    lines=5
                )
                url_level = gr.Slider(
                    minimum=1,
                    maximum=10,
                    step=1,
                    label="URL Level (for URL Level scraping)",
                    value=2,
                    visible=False
                )
                max_pages = gr.Slider(
                    minimum=1,
                    maximum=100,
                    step=1,
                    label="Maximum Pages to Scrape (for Recursive Scraping)",
                    value=10,
                    visible=False
                )
                max_depth = gr.Slider(
                    minimum=1,
                    maximum=10,
                    step=1,
                    label="Maximum Depth (for Recursive Scraping)",
                    value=3,
                    visible=False
                )
                custom_article_title_input = gr.Textbox(
                    label="Custom Article Titles (Optional, one per line)",
                    placeholder="Enter custom titles for the articles, one per line",
                    lines=5
                )
                with gr.Row():
                    summarize_checkbox = gr.Checkbox(label="Summarize Articles", value=False)
                    custom_prompt_checkbox = gr.Checkbox(label="Use a Custom Prompt", value=False, visible=True)
                    preset_prompt_checkbox = gr.Checkbox(label="Use a pre-set Prompt", value=False, visible=True)
                with gr.Row():
                    temp_slider = gr.Slider(0.1, 2.0, 0.7, label="Temperature")
                with gr.Row():
                    preset_prompt = gr.Dropdown(
                        label="Select Preset Prompt",
                        choices=load_preset_prompts(),
                        visible=False
                    )
                with gr.Row():
                    website_custom_prompt_input = gr.Textbox(
                        label="Custom Prompt",
                        placeholder="Enter custom prompt here",
                        lines=3,
                        visible=False
                    )
                with gr.Row():
                    system_prompt_input = gr.Textbox(
                        label="System Prompt",
                        value="""<s>You are a bulleted notes specialist. [INST]```When creating comprehensive bulleted notes, you should follow these guidelines: Use multiple headings based on the referenced topics, not categories like quotes or terms. Headings should be surrounded by bold formatting and not be listed as bullet points themselves. Leave no space between headings and their corresponding list items underneath. Important terms within the content should be emphasized by setting them in bold font. Any text that ends with a colon should also be bolded. Before submitting your response, review the instructions, and make any corrections necessary to adhered to the specified format. Do not reference these instructions within the notes.``` \nBased on the content between backticks create comprehensive bulleted notes.[/INST]
                                **Bulleted Note Creation Guidelines**
                                
                                **Headings**:
                                - Based on referenced topics, not categories like quotes or terms
                                - Surrounded by **bold** formatting 
                                - Not listed as bullet points
                                - No space between headings and list items underneath
                                
                                **Emphasis**:
                                - **Important terms** set in bold font
                                - **Text ending in a colon**: also bolded
                                
                                **Review**:
                                - Ensure adherence to specified format
                                - Do not reference these instructions in your response.</s>[INST] {{ .Prompt }} [/INST]
                                """,
                        lines=3,
                        visible=False
                    )

                api_name_input = gr.Dropdown(
                    choices=[None, "Local-LLM", "OpenAI", "Anthropic", "Cohere", "Groq", "DeepSeek", "Mistral",
                             "OpenRouter",
                             "Llama.cpp", "Kobold", "Ooba", "Tabbyapi", "VLLM", "ollama", "HuggingFace",
                             "Custom-OpenAI-API"],
                    value=None,
                    label="API Name (Mandatory for Summarization)"
                )
                api_key_input = gr.Textbox(
                    label="API Key (Mandatory if API Name is specified)",
                    placeholder="Enter your API key here; Ignore if using Local API or Built-in API",
                    type="password"
                )
                keywords_input = gr.Textbox(
                    label="Keywords",
                    placeholder="Enter keywords here (comma-separated)",
                    value="default,no_keyword_set",
                    visible=True
                )

                scrape_button = gr.Button("Scrape and Summarize")
            with gr.Column():
                progress_output = gr.Textbox(label="Progress", lines=3)
                result_output = gr.Textbox(label="Result", lines=20)

        def update_ui_for_scrape_method(method):
            url_level_update = gr.update(visible=(method == "URL Level"))
            max_pages_update = gr.update(visible=(method == "Recursive Scraping"))
            max_depth_update = gr.update(visible=(method == "Recursive Scraping"))
            url_input_update = gr.update(
                label="Article URLs" if method == "Individual URLs" else "Base URL",
                placeholder="Enter article URLs here, one per line" if method == "Individual URLs" else "Enter the base URL for scraping"
            )
            return url_level_update, max_pages_update, max_depth_update, url_input_update

        scrape_method.change(
            fn=update_ui_for_scrape_method,
            inputs=[scrape_method],
            outputs=[url_level, max_pages, max_depth, url_input]
        )

        custom_prompt_checkbox.change(
            fn=lambda x: (gr.update(visible=x), gr.update(visible=x)),
            inputs=[custom_prompt_checkbox],
            outputs=[website_custom_prompt_input, system_prompt_input]
        )
        preset_prompt_checkbox.change(
            fn=lambda x: gr.update(visible=x),
            inputs=[preset_prompt_checkbox],
            outputs=[preset_prompt]
        )

        def update_prompts(preset_name):
            prompts = update_user_prompt(preset_name)
            return (
                gr.update(value=prompts["user_prompt"], visible=True),
                gr.update(value=prompts["system_prompt"], visible=True)
            )

        preset_prompt.change(
            update_prompts,
            inputs=preset_prompt,
            outputs=[website_custom_prompt_input, system_prompt_input]
        )

        async def scrape_and_summarize_wrapper(
                scrape_method: str,
                url_input: str,
                url_level: Optional[int],
                max_pages: int,
                max_depth: int,
                summarize_checkbox: bool,
                custom_prompt: Optional[str],
                api_name: Optional[str],
                api_key: Optional[str],
                keywords: str,
                custom_titles: Optional[str],
                system_prompt: Optional[str],
                temperature: float = 0.7,
                progress: gr.Progress = gr.Progress()
        ) -> str:
            try:
                result: List[Dict[str, Any]] = []

                if scrape_method == "Individual URLs":
                    result = await scrape_and_summarize_multiple(url_input, custom_prompt, api_name, api_key, keywords,
                                                                 custom_titles, system_prompt)
                elif scrape_method == "Sitemap":
                    result = await asyncio.to_thread(scrape_from_sitemap, url_input)
                elif scrape_method == "URL Level":
                    if url_level is None:
                        return convert_json_to_markdown(
                            json.dumps({"error": "URL level is required for URL Level scraping."}))
                    result = await asyncio.to_thread(scrape_by_url_level, url_input, url_level)
                elif scrape_method == "Recursive Scraping":
                    result = await recursive_scrape(url_input, max_pages, max_depth, progress.update, delay=1.0)
                else:
                    return convert_json_to_markdown(json.dumps({"error": f"Unknown scraping method: {scrape_method}"}))

                # Ensure result is always a list of dictionaries
                if isinstance(result, dict):
                    result = [result]
                elif isinstance(result, list):
                    if all(isinstance(item, str) for item in result):
                        # Convert list of strings to list of dictionaries
                        result = [{"content": item} for item in result]
                    elif not all(isinstance(item, dict) for item in result):
                        raise ValueError("Not all items in result are dictionaries or strings")
                else:
                    raise ValueError(f"Unexpected result type: {type(result)}")

                # Ensure all items in result are dictionaries
                if not all(isinstance(item, dict) for item in result):
                    raise ValueError("Not all items in result are dictionaries")

                if summarize_checkbox:
                    total_articles = len(result)
                    for i, article in enumerate(result):
                        progress.update(f"Summarizing article {i + 1}/{total_articles}")
                        content = article.get('content', '')
                        if content:
                            summary = await asyncio.to_thread(summarize, content, custom_prompt, api_name, api_key,
                                                              temperature, system_prompt)
                            article['summary'] = summary
                        else:
                            article['summary'] = "No content available to summarize."

                # Concatenate all content
                all_content = "\n\n".join(
                    [f"# {article.get('title', 'Untitled')}\n\n{article.get('content', '')}\n\n" +
                     (f"Summary: {article.get('summary', '')}" if summarize_checkbox else "")
                     for article in result])

                # Collect all unique URLs
                all_urls = list(set(article.get('url', '') for article in result if article.get('url')))

                # Structure the output for the entire website collection
                website_collection = {
                    "base_url": url_input,
                    "scrape_method": scrape_method,
                    "summarization_performed": summarize_checkbox,
                    "api_used": api_name if summarize_checkbox else None,
                    "keywords": keywords if summarize_checkbox else None,
                    "url_level": url_level if scrape_method == "URL Level" else None,
                    "max_pages": max_pages if scrape_method == "Recursive Scraping" else None,
                    "max_depth": max_depth if scrape_method == "Recursive Scraping" else None,
                    "total_articles_scraped": len(result),
                    "urls_scraped": all_urls,
                    "content": all_content
                }

                # Convert the JSON to markdown and return
                return convert_json_to_markdown(json.dumps(website_collection, indent=2))
            except Exception as e:
                return convert_json_to_markdown(json.dumps({"error": f"An error occurred: {str(e)}"}))

        # Update the scrape_button.click to include the temperature parameter
        scrape_button.click(
            fn=lambda *args: asyncio.run(scrape_and_summarize_wrapper(*args)),
            inputs=[scrape_method, url_input, url_level, max_pages, max_depth, summarize_checkbox,
                    website_custom_prompt_input, api_name_input, api_key_input, keywords_input,
                    custom_article_title_input, system_prompt_input, temp_slider],
            outputs=[result_output]
        )


def convert_json_to_markdown(json_str: str) -> str:
    """
    Converts the JSON output from the scraping process into a markdown format.

    Args:
        json_str (str): JSON-formatted string containing the website collection data

    Returns:
        str: Markdown-formatted string of the website collection data
    """
    try:
        # Parse the JSON string
        data = json.loads(json_str)

        # Check if there's an error in the JSON
        if "error" in data:
            return f"# Error\n\n{data['error']}"

        # Start building the markdown string
        markdown = f"# Website Collection: {data['base_url']}\n\n"

        # Add metadata
        markdown += "## Metadata\n\n"
        markdown += f"- **Scrape Method:** {data['scrape_method']}\n"
        markdown += f"- **API Used:** {data['api_used']}\n"
        markdown += f"- **Keywords:** {data['keywords']}\n"
        if data['url_level'] is not None:
            markdown += f"- **URL Level:** {data['url_level']}\n"
        markdown += f"- **Total Articles Scraped:** {data['total_articles_scraped']}\n\n"

        # Add URLs scraped
        markdown += "## URLs Scraped\n\n"
        for url in data['urls_scraped']:
            markdown += f"- {url}\n"
        markdown += "\n"

        # Add the content
        markdown += "## Content\n\n"
        markdown += data['content']

        return markdown

    except json.JSONDecodeError:
        return "# Error\n\nInvalid JSON string provided."
    except KeyError as e:
        return f"# Error\n\nMissing key in JSON data: {str(e)}"
    except Exception as e:
        return f"# Error\n\nAn unexpected error occurred: {str(e)}"
#
# End of File
########################################################################################################################