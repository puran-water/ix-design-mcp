---
allowed-tools: mcp__codex__codex, mcp__codex__codex-reply
description: Leverage the Codex MCP server to get a second opinion on the current problem with full project context, instructing it to use both DeepWiki and the GitHub CLI (gh) for repository review
argument-hint: <problem-description> <project-path> [repo1/name repo2/name ...]
thinking: true
---

# Get Second Opinion from Codex

Use the Codex MCP server to analyze the current problem with comprehensive context.

**CRITICAL WARNING**: When calling Codex tools (mcp__codex__codex or mcp__codex__codex-reply), you MUST wait for the complete response before performing ANY other action. Any tool use or command before Codex responds will terminate the Codex session immediately.

## Instructions

1. Take the user's problem description and expand it with:
   - Full explanation of what we're trying to achieve
   - What has been attempted so far
   - Any errors or challenges encountered
   - The specific question or area where a second opinion would help

2. Provide Codex with:
   - The absolute path to the project directory (from the argument)
   - List of all relevant files in the project that relate to the problem
   - Any configuration files, package.json, requirements.txt, etc.
   - The main dependencies/repos being used (from the arguments) so Codex can query them via DeepWiki and inspect them directly via GitHub CLI (gh)

3. Format the prompt for Codex to include:
   - Clear problem statement assuming no prior knowledge
   - Project structure and relevant file paths
   - Technology stack and dependencies
   - Specific areas where alternative approaches or validation would be valuable

4. Pass the comprehensive context to Codex using the mcp__codex__codex tool with appropriate parameters:
   - Set the working directory to the project path
   - Include instructions for Codex to use DeepWiki for dependency documentation
   - Also instruct Codex to leverage GitHub CLI (gh) to directly review repositories (e.g., repo metadata, issues, PRs, releases, files) when DeepWiki's response is incomplete or needs validation
   - Request detailed analysis and alternative solutions

## CRITICAL: WAITING FOR CODEX RESPONSES
**IMPORTANT**: After calling mcp__codex__codex or mcp__codex__codex-reply:
- **DO NOT** perform any other tool calls or actions
- **DO NOT** use Bash, Read, Write, or any other tools
- **DO NOT** try to check session files or logs
- **DO NOT** output ANY text to the user (not even "waiting for response" or similar messages)
- **DO NOT** make any statements about waiting or what you'll do next
- **WAIT SILENTLY** for Codex to complete its full response
- The Codex session will be terminated if you perform ANY action or output ANY text before it responds
- Only after receiving Codex's response should you proceed with finding the session ID or other actions

5. For multi-turn conversations (ONLY after Codex responds):
   a. After making the initial codex call, retrieve the session ID from the Codex sessions directory
   b. Navigate to: `/home/hvksh/.codex/sessions/YYYY/MM/DD/` (use today's date)
   c. Find the most recent file by modification time: `ls -lt /home/hvksh/.codex/sessions/YYYY/MM/DD/*.jsonl | head -1`
   d. Extract the session ID from the filename: The format is `rollout-YYYY-MM-DDTHH-MM-SS-[SESSION_ID].jsonl`
      - Example: `rollout-2025-09-10T12-35-31-670d90ae-4ff6-4a50-bcea-011d6ab64dbe.jsonl`
      - Session ID: `670d90ae-4ff6-4a50-bcea-011d6ab64dbe`
   e. Verify it's the correct session by reading the file and checking for your initial prompt
   f. Use `mcp__codex__codex-reply` with parameter `conversationId` (NOT `session_id`) set to the extracted UUID

Remember: For the INITIAL mcp__codex__codex call, Codex has no prior knowledge of our conversation or project, so be exhaustive in providing context. Once you have the conversationId, subsequent mcp__codex__codex-reply calls will maintain the conversation context automatically.
