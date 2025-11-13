# Using MCP Servers

Clear guidelines for effective use of Model Context Protocol (MCP) servers in this project.

## Memory Server

### When to Use
- **Task initiation**: Always read existing knowledge graph at start of any task
- **Major discoveries**: Create entities for significant findings, patterns, or implementations
- **Phase completion**: Store results, learnings, and context for future reference
- **Context preservation**: Before switching modes or ending complex conversations

### Frequency Guidelines
- **Simple tasks** (< 10 messages): Every 3-5 messages
- **Complex tasks** (10+ messages): Every 2-3 messages
- **Always** at task start and completion

### Entity Organization
- **Software Project**: High-level project information, architecture, goals
- **Development Task**: Specific work items, implementations, results
- **Code Component**: Classes, modules, APIs, validation logic, test suites
- **Technical Achievement**: Performance results, successful implementations
- **Performance Metrics**: Benchmarks, optimization results

### Practical Examples
```
# Task start - gather context
search_nodes("cfb-data college football API")

# During development - store new patterns
create_entities([{
  "name": "API Validation Pattern",
  "entityType": "Code Component",
  "observations": ["Uses Pydantic model_validator for complex logic"]
}])

# Phase completion - preserve results
add_observations([{
  "entityName": "Request Model Validation Enhancement Task",
  "contents": ["Completed all 135 test cases successfully"]
}])
```

## Context7 Server

### When to Use
- **External library research**: Before using unfamiliar APIs or methods
- **Version-specific information**: When working with specific library versions
- **Best practices lookup**: For implementation patterns in external libraries
- **API documentation**: When official docs are needed for accuracy

### Relevant Libraries for This Project
- **Pydantic**: Model validation, serialization patterns
- **pytest**: Testing frameworks, fixtures, parametrization
- **pandas**: DataFrame operations, data manipulation
- **httpx/aiohttp**: HTTP client patterns and best practices
- **FastAPI**: If extending to web APIs

### Fallback Strategy
1. Try Context7 first for up-to-date information
2. If Context7 lacks info, use browser to find official documentation
3. Store useful findings in memory server for future reference

### Practical Examples
```
# Before implementing new validation
use_mcp_tool("context7", "search", {"query": "Pydantic v2 model_validator"})

# When adding test patterns
use_mcp_tool("context7", "search", {"query": "pytest parametrize best practices"})

# For performance optimization
use_mcp_tool("context7", "search", {"query": "pandas DataFrame performance tips"})
```

## Best Practices

### Knowledge Graph Hygiene
- **Specific entities**: Focus on concrete components, not vague concepts
- **Meaningful relationships**: Link related entities with clear connection types
- **Regular cleanup**: Remove outdated observations, update completed tasks
- **Consistent naming**: Use clear, searchable entity names

### Efficiency Guidelines
- **Batch operations**: Group related memory operations when possible
- **Targeted searches**: Use specific queries rather than broad searches
- **Context building**: Start each session by reading relevant existing knowledge
- **Documentation**: Include enough detail for future reference without verbosity

### Error Handling
- If MCP operations fail, continue with task but note limitations
- Always have fallback strategies (browser research, documentation)
- Document any MCP server issues in observations for troubleshooting
