---
name: api-interface-design
description: Use when designing public APIs, module boundaries, provider adapters, tool schemas, or data contracts.
---

# API Interface Design

Design the contract before the implementation.

## Use This For

- REST, GraphQL, or SDK interface design
- Tool parameter schemas
- Provider adapter boundaries
- Data exchanged between the agent loop, tools, and persistence

## Principles

- Prefer additive changes over breaking existing fields.
- Use one predictable error shape.
- Validate external input at the boundary.
- Keep internal call sites typed and boring.
- Treat every observable behavior as something users may depend on.

## Checklist

- Inputs and outputs are typed.
- Error semantics are consistent.
- Optional fields are truly optional.
- New behavior has at least one success test and one failure test.
- Docs show the smallest working example.
