Web Tooling and Artifact Operations Reference Manual
Purpose

This manual documents the tooling layer of graph_mapper_agent, with a focus on web navigation, inspection, in-page search, artifact download, document opening, and preliminary remote content classification.

Its goal is to make clear:

the role this layer plays inside the agent,
how it is assembled,
which objects are returned by bootstrap,
how tooling adapters connect to WebBrowserTool,
how Playwright is used underneath,
how PDFs, screenshots, downloads, and probes are handled,
and how to extend the layer with new tools.

This document is intended for maintenance, onboarding, debugging, and publication of the codebase.

1. General overview

The tooling layer gives the agent operational access to web resources and artifacts.

It does not decide goals, resolve LLM providers, or interpret structured outputs. Its responsibility is different:

navigate,
inspect,
search,
download,
open artifacts,
classify remote content,
and expose those capabilities through clean ports to the rest of the system.
Correct mental model
bootstrap/builders/tooling.py
    -> ToolRegistry
    -> WebBrowserTool
    -> NavigationActions adapter
    -> LiveInspection adapter
    -> consumption by runner and services
Relationship to the rest of the system

The tooling layer complements the LLM pipeline.

the LLM layer decides, interprets, validates, and structures;
the tooling layer navigates, observes, downloads, and returns raw or operational evidence.
2. Overall tool architecture map
Bootstrap flow
build_tooling()
    -> ToolRegistry()
    -> IngestStorage()
    -> WebBrowserTool(settings, storage)
    -> WebBrowserNavigationActionsAdapter(browser_tool)
    -> WebBrowserLiveInspectionAdapter(browser_tool)
    -> register functions in ToolRegistry
    -> ToolingBundle
Real operational flow
runner.py
    -> build_tooling()
    -> registry
    -> browser_tool
    -> navigation_actions
    -> live_inspection
    -> services / orchestrator / agent actions
Main components
ToolRegistry
WebBrowserTool
PlaywrightDriver
WebBrowserNavigationActionsAdapter
WebBrowserLiveInspectionAdapter
functional modules:
inspection
search
downloads
artifacts
content_probe
pdf_support
3. Tooling bootstrap
File: bootstrap/builders/tooling.py

This file assembles the operational tooling bundle.

What it builds
ToolRegistry

A simple registry of tools invocable by name.

WebBrowserTool

The main infrastructure object for navigation and inspection.

It is built with:

IngestStorage()
WebBrowserToolSettings()
navigation_actions

Constructed as WebBrowserNavigationActionsAdapter(browser_tool).

live_inspection

Constructed as WebBrowserLiveInspectionAdapter(browser_tool).

What it registers in the registry
search_with_text
inspect_page
download_candidate
open_artifact
Result

It returns a ToolingBundle containing:

registry
browser_tool
navigation_actions
live_inspection
Architectural interpretation

build_tooling() is the assembly point of the tooling layer.

It does not contain navigation logic itself. It only wires the parts together and leaves them ready for the rest of the system.

4. ToolingBundle
Role

To group the main pieces of the tooling layer into a single structure that bootstrap can hand off.

Fields
registry: ToolRegistry
browser_tool: WebBrowserTool
navigation_actions: NavigationActionsPort
live_inspection: LiveInspectionPort
Why this matters

It allows runner.py to receive the tooling layer already assembled and use it without needing to know the internal details of Playwright, downloads, PDFs, or storage.

5. WebBrowserTool as the central core
File: adapters/web_browser/tool.py

WebBrowserTool is the central core of the tooling layer.

It is an infrastructure object that concentrates:

the browser driver,
storage,
settings,
inspection operations,
search,
download,
artifact opening,
content probing,
PDF and screenshot support,
auxiliary snapshots for search state changes.
What it receives when constructed
storage: IngestStorage | None
settings: WebBrowserToolSettings | None
projection_tool: Any | None
What it initializes internally
_storage
_settings
_driver = PlaywrightDriver(...)
optional _projection_tool
Main public methods
inspect_page(...)
search_with_text(...)
download_candidate(...)
open_artifact(...)
probe_content(...)
close()
Actual role

WebBrowserTool is the main façade of the web infrastructure.

The functional modules (search.py, downloads.py, and others) are not independent tools. They are internal components that receive tool and use its driver, settings, and storage.

6. Browser driver
File: adapters/tools/web_browser/driver.py

PlaywrightDriver is the infrastructure wrapper around Playwright.

Responsibilities
start the browser process,
close and clean up resources,
create new pages,
maintain a reusable persistent tab,
configure timeouts,
manage downloads through Playwright.
Settings

DriverSettings defines:

browser_name
headless
user_agent
default_timeout_ms
default_navigation_timeout_ms
slow_mo_ms
Key methods
start()

Starts Playwright and launches the browser.

stop()

Closes the persistent page, context, browser, and Playwright instance.

new_page()

Creates a new isolated page in the current context.

get_persistent_page()

Reuses a single visible tab for persistent navigation and inspection.

reset_persistent_page()

Forces the persistent tab to be closed and recreated later.

download_file()

Uses page.expect_download(...) and page.goto(...) to capture downloads managed by Playwright.

Architectural meaning

The driver encapsulates Playwright complexity and prevents the rest of the system from dealing directly with Browser, Page, Context, and related objects.

7. Tooling adapters to domain ports
WebBrowserNavigationActionsAdapter
File

adapters/tooling/web_browser_navigation_actions_adapter.py

Role

A bridge between WebBrowserTool and NavigationActionsPort.

Responsibility

Expose only the navigation actions the agent needs, without coupling the domain to ToolRegistry or the internal browser tool implementation.

Main methods
inspect_page(...)
search_with_text(...)
download_artifact(...)
open_artifact(...)
inspect_live(...)
probe_content(...)
Pattern used

Each method:

receives a typed domain request,
converts it into dict[str, object],
calls the corresponding WebBrowserTool method,
validates that the result is a dict.
Importance

This adapter protects the domain from the internal implementation details of the web tool.

WebBrowserLiveInspectionAdapter
File

adapters/tooling/web_browser_live_inspection_adapter.py

Role

A specific bridge between WebBrowserTool and LiveInspectionPort.

Main method
inspect_live(...)
Difference compared with navigation_actions

Although it uses the same base tool, it represents a different domain port. That allows the system to model a different intent:

navigation actions on one side,
live or contextual inspection on the other.
8. In-page search
File: adapters/web_browser/search.py

This module implements search logic inside an already loaded page.

Conceptual flow
search_with_text(...)
    -> parse params
    -> obtain persistent page
    -> goto(entry_url)
    -> detect whether it landed on a PDF
    -> take pre-search snapshot
    -> locate search targets
    -> resolve target
    -> execute search in frame
    -> wait for state delta
    -> rebuild inspection result
    -> attach search_metadata
Important decisions
Uses a persistent page

search_with_text(...) works on tool._driver.get_persistent_page() in order to preserve visual and navigation continuity.

Detects PDFs

If the final URL appears to be a PDF, it returns an inspection result with metadata indicating that search is not supported in that view.

Takes snapshots before and after

It captures state signatures to determine whether the search actually changed anything:

URL,
title,
text excerpt,
candidates,
result scope.
Executes search per frame

It uses helper JavaScript (search_submit.js) injected into the frame to submit the query to the correct target.

Returns rich metadata

It includes:

search target,
submit method,
frame URL,
confidence,
state delta,
whether results were detected,
post-search candidate count,
post-search text preview.
Interpretation

Search is not just a simple fill + enter. It is a traceable operation with delta verification and metadata that the agent can inspect.

9. Resource downloads
File: adapters/web_browser/downloads.py

This module downloads a remote resource and persists it in storage.

Conceptual flow
download_candidate(...)
    -> validate candidate_url
    -> decide download strategy
        -> direct HTTP if it looks like a PDF
        -> Playwright download otherwise
    -> read downloaded bytes
    -> calculate sha256
    -> save original bytes into storage
    -> remove temporary file
    -> return stored file metadata
Supported strategies
Direct PDF download over HTTP

If the URL appears to be a PDF, it uses urlopen(...) and writes the response to a temporary file.

Download through Playwright

If it is not a direct PDF, it delegates to the driver via download_file(...).

What it returns
download_url
final_url
filename
original_path
content_type
sha256
size_bytes
metadata.suggested_filename
Importance

This connects web navigation with evidence persistence in storage.

10. Opening artifacts
File: adapters/web_browser/artifacts.py

This module opens artifacts that were already downloaded or stored locally.

Conceptual flow
open_artifact(...)
    -> resolve local path
    -> verify existence
    -> if not PDF -> return non-PDF artifact
    -> if PDF -> attempt text extraction
        -> if enough text -> return pdf_text
        -> otherwise -> generate screenshot of the PDF
Main decisions
Only supports intelligent reading for PDFs
if the file is not a PDF, it returns non_pdf_file
if it is a PDF, it decides between text and screenshot
Text-first strategy

It reads the first page and measures whether there is enough text.

Visual fallback

If the text is insufficient, it generates a base64 screenshot.

Artifact types it may return
pdf_text
pdf_screenshot
non_pdf_file
unknown
Importance

It turns persisted files into usable content for the agent or for a visual route.

11. Content probing
File: adapters/web_browser/content_probe.py

This module classifies a remote resource without visually navigating to it or fully downloading it.

What it does
it does not visually navigate,
it does not decide action policy,
it does not fully download the file,
it only classifies the remote resource.
Strategy
HEAD first
if HEAD is inconclusive, short GET with Range
classification by content-type
fallback using magic bytes and HTML-like bytes
Supported resource kinds
pdf
html
json
image
binary
unknown
What it returns
original_url
final_url
status
content_type_raw
content_type
resource_kind
via_method
is_pdf_magic
looks_like_html
headers
metadata
Architectural value

This module allows later decisions to be made without spending on a full navigation or full download.

12. Specialized support for PDFs and screenshots
File: adapters/web_browser/pdf_support.py

This module contains the logic specific to PDF detection and screenshot handling.

Responsibilities
detect whether a URL looks like a PDF,
determine whether a screenshot should come from HTML or PDF,
render PDFs via PyMuPDF when appropriate,
fall back to browser screenshots,
detect blank screenshots,
apply HTML stability waits.
Conceptual flow
take_smart_screenshot(...)
    -> include_screenshot?
    -> is_pdf_url(final_url)?
        -> no: wait for HTML stability and take direct screenshot
        -> yes:
            -> try fitz if enabled
            -> if it fails: browser screenshot for PDF
Strategies for PDFs
try_fitz_screenshot(...)

Downloads the PDF to a temporary file and renders it with PyMuPDF.

take_pdf_browser_screenshot(...)

Takes a screenshot of the browser PDF viewer, with multiple attempts and blank detection.

Final fallback

If the browser screenshot is still blank, it tries PyMuPDF again if available.

Utility

The tooling layer does not treat PDFs as second-class content. It handles them as first-class resources.

13. How requests travel through the tooling layer
General pattern
domain port
    -> tooling adapter
    -> WebBrowserTool
    -> internal functional module
    -> driver / storage / PDF support
    -> dict[str, object]
Example: inspect page
InspectPageRequest
    -> WebBrowserNavigationActionsAdapter.inspect_page(...)
    -> WebBrowserTool.inspect_page(...)
    -> inspection.inspect_page(...)
    -> driver/page/screenshot/extraction
    -> result dict
Example: download artifact
DownloadArtifactRequest
    -> WebBrowserNavigationActionsAdapter.download_artifact(...)
    -> WebBrowserTool.download_candidate(...)
    -> downloads.download_candidate(...)
    -> driver/http + storage
    -> file metadata
14. Role of ToolRegistry
Role

A registry of functions invocable by name.

What is currently registered
search_with_text
inspect_page
download_candidate
open_artifact
What it is for

It exposes concrete tools without requiring the domain to know the internal implementation of the browser tool.

Important note

The main agent domain does not necessarily depend on ToolRegistry; it uses ports such as NavigationActionsPort and LiveInspectionPort. The registry is a useful bootstrap and invocation layer, but it is not the core contract of the domain.

15. How to add a new tool

Suppose you want to add a new action, for example capture_dom_snapshot.

Step 1 — Decide whether it is:
an action of WebBrowserTool,
a new internal functional module,
a function that should be registered in ToolRegistry,
a method that should enter NavigationActionsPort,
or a capability only for LiveInspectionPort.
Step 2 — Create the internal operation

Add the new functional module or corresponding method.

Conceptual example:

adapters/web_browser/dom_snapshot.py
    -> capture_dom_snapshot(tool, input_data)
Step 3 — Expose it in WebBrowserTool

Add a public method:

def capture_dom_snapshot(self, input_data: dict[str, Any]) -> dict[str, Any]:
    return capture_dom_snapshot(self, input_data)
Step 4 — Decide whether it belongs in a domain port

If the agent needs it as navigation or inspection capability, add the method to the port and to the corresponding adapter.

Step 5 — Register it if it must be invocable by name

In build_tooling():

registry.register("capture_dom_snapshot", browser_tool.capture_dom_snapshot)
Step 6 — Document it

Update this manual.

16. How to debug the tooling layer
If browser startup fails

Review:

driver.py
Playwright installation
browser, context, and page configuration
If in-page search fails

Review:

search.py
snapshot and delta logic
target resolution
search_submit.js
persistent page handling
If a download fails

Review:

downloads.py
driver.download_file(...)
direct PDF detection
storage
If artifact opening fails

Review:

artifacts.py
local path existence
PyMuPDF
text threshold
screenshot fallback
If remote pre-classification fails

Review:

content_probe.py
HEAD and GET fallback
content-type
magic bytes
If PDF screenshot generation fails

Review:

pdf_support.py
is_pdf_url(...)
fitz or PyMuPDF
blank detection
browser PDF screenshot
If integration with the agent fails

Review:

build_tooling()
tooling adapters
domain ports
runner.py
17. Maintenance rules
Rule 1

Do not mix in the same change:

driver infrastructure,
agent business logic,
and domain contracts,

unless it is strictly necessary.

Rule 2

WebBrowserTool should remain an infrastructure façade, not become a center of domain logic.

Rule 3

Tooling adapters should translate domain requests into tool payloads, not inject extra business policy.

Rule 4

Internal operations (downloads, probe, pdf_support, and others) should return controlled and traceable results.

Rule 5

Every new tool should explicitly decide:

whether it belongs in the registry,
whether it belongs in a port,
or whether it is only an internal helper.
18. Checklist for human contributors and AI agents

Before touching this layer, answer:

Am I changing bootstrap, tool façade, driver, adapter, functional module, or port?
Does the change affect navigation, search, download, artifacts, probing, or screenshots?
Do I need to change the domain, or only infrastructure?
Does the new tool need to be registered?
Does the new tool need to enter NavigationActionsPort or LiveInspectionPort?
Am I breaking persistent page continuity?
Do I need to update this manual?
19. Executive summary

The tooling layer of graph_mapper_agent is designed as a web infrastructure layer decoupled from both the domain and the LLM pipeline.

Its core is WebBrowserTool, which encapsulates the driver, storage, and functional operations such as inspection, search, download, artifact opening, content probing, and advanced PDF handling.

Bootstrap constructs this layer through build_tooling(), returning a ToolingBundle with:

registry,
browser tool,
navigation actions,
live inspection.

The domain consumes this tooling through ports and adapters, while the internal infrastructure relies on Playwright, storage, and specialized helpers.

The architecture is well understood when viewed like this:

bootstrap assembles,
the browser tool centralizes,
the driver executes,
adapters translate,
functional modules solve concrete tasks,
and the domain consumes only clean ports.
20. Ultra-short summary for AI agents
What this layer does

Provides web operational capabilities to the agent.

Core pieces
build_tooling()
ToolingBundle
WebBrowserTool
PlaywrightDriver
adapters to domain ports
Main capabilities
inspection
search
download
artifact opening
content probing
screenshots and PDF support
Golden rule

Do not confuse:

the registry,
the browser façade,
domain adapters,
the driver,
and internal functional modules.